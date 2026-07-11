"""
Conflict-detection scorer. Bypasses NL parsing and the DAG-generation LLM
entirely -- scenarios feed conflicts.detect_conflicts() directly with
{device, capability, args} action lists and time windows, the same shape
extract_actions()/candidates_from_db() produce internally. This isolates
conflict-detector accuracy from DAG-generation accuracy: a bad score here
can't be secretly caused by a bad DAG upstream.

Two things this scorer measures:
  1. Per-class precision/recall/F1 over every labelled candidate, pooled
     across all scenarios (this is a classification problem over discrete
     candidate instances, not a per-scenario structural score like the DAG
     scorer -- macro-averaging per scenario would be meaningless here since
     most scenarios don't contain all four classes).
  2. The deterministic pre-filter's recall in isolation: of the candidates
     that SHOULD be flagged (expected_type != "none"), what fraction pass
     the time-overlap + shared-device pre-filter and therefore even reach
     the classifier? A true conflict the pre-filter drops never gets a
     chance to be judged correctly, so this number matters independently of
     classifier accuracy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import conflicts  # backend module, via eval/__init__ bootstrap

from .metrics import prf_from_counts

CONFLICT_TYPES = ("contradiction", "redundancy", "overlap", "none")

DetectFn = Callable[[Dict[str, Any], List[Dict[str, Any]], bool], List[Dict[str, Any]]]


def _parse_hhmm(value: Optional[str]) -> Optional[int]:
    """Reimplementation of conflicts._parse_hhmm (private, not importable as
    a stable API). Pure and tiny; exercised against conflicts.py's own
    behavior in the pytest suite so drift would be caught."""
    if not value or not isinstance(value, str):
        return None
    try:
        hours, minutes = value.strip().split(":")
        return int(hours) * 60 + int(minutes)
    except Exception:
        return None


def prefilter_holds(new_policy: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    """Reimplementation of the inline pre-filter inside
    conflicts.detect_conflicts() (time-window overlap AND shared device).
    conflicts.py has no standalone pre-filter function -- the check is
    inlined and its result (the "flagged" list) never escapes that
    function -- so this is the only way to observe pre-filter behavior in
    isolation without modifying application code. Reuses the real, public
    conflicts.windows_overlap(); only the one-line shared-device check and
    HH:MM parsing (needed to call windows_overlap at all) are reimplemented.
    """
    ns = _parse_hhmm(new_policy.get("window", {}).get("from_time"))
    ne = _parse_hhmm(new_policy.get("window", {}).get("to_time"))
    cs = _parse_hhmm(candidate.get("window", {}).get("from_time"))
    ce = _parse_hhmm(candidate.get("window", {}).get("to_time"))
    if not conflicts.windows_overlap(ns, ne, cs, ce):
        return False
    new_devices = {a["device"] for a in new_policy.get("actions", []) if a.get("device")}
    cand_devices = {a["device"] for a in candidate.get("actions", []) if a.get("device")}
    return bool(new_devices & cand_devices)


@dataclass
class CandidateResult:
    scenario_id: str
    name: str
    expected_type: str
    predicted_type: str
    prefilter_passed: bool


@dataclass
class ConflictScenarioResult:
    scenario_id: str
    candidates: List[CandidateResult]


def score_conflict_scenario(
    scenario: Dict[str, Any],
    use_llm: bool = False,
    detect_fn: Optional[DetectFn] = None,
) -> ConflictScenarioResult:
    """Run one new_policy-vs-candidates scenario through the real
    conflicts.detect_conflicts() and diff its output against each
    candidate's expected_type.

    use_llm=False (default) exercises the deterministic rule-based fallback
    -- the path the pytest suite uses, since it needs zero network calls.
    use_llm=True hits the real Groq judge; the runner uses this for the
    actual conflict-detection accuracy numbers.
    """
    detect = detect_fn or conflicts.detect_conflicts
    new_policy = scenario["new_policy"]
    candidates = [
        {k: v for k, v in c.items() if k != "expected_type"}
        for c in scenario["candidates"]
    ]

    detected = detect(new_policy, candidates, use_llm)
    # Unsaved fixtures have no DB row / policy_id, so predictions are matched
    # back to candidates by name -- scenario authors must keep candidate
    # names unique within a scenario (enforced at load time).
    predicted_by_name = {d["policy_name"]: d["type"] for d in detected}

    results = []
    for cand in scenario["candidates"]:
        predicted = predicted_by_name.get(cand["name"], "none")
        clean_cand = {k: v for k, v in cand.items() if k != "expected_type"}
        results.append(CandidateResult(
            scenario_id=scenario["id"],
            name=cand["name"],
            expected_type=cand["expected_type"],
            predicted_type=predicted,
            prefilter_passed=prefilter_holds(new_policy, clean_cand),
        ))
    return ConflictScenarioResult(scenario_id=scenario["id"], candidates=results)


@dataclass
class ConflictReport:
    class_metrics: Dict[str, Tuple[float, float, float]]  # class -> (precision, recall, f1)
    class_support: Dict[str, int]                          # class -> # candidates with that expected_type
    confusion: Dict[Tuple[str, str], int]                   # (expected, predicted) -> count
    prefilter_recall: Optional[float]                       # None if no true-conflict candidates exist
    prefilter_true_conflict_n: int
    total_candidates: int
    per_scenario: List[ConflictScenarioResult] = field(repr=False)


def score_conflicts(
    scenarios: List[Dict[str, Any]],
    use_llm: bool = False,
    detect_fn: Optional[DetectFn] = None,
) -> ConflictReport:
    per_scenario = [score_conflict_scenario(sc, use_llm=use_llm, detect_fn=detect_fn) for sc in scenarios]
    all_candidates = [c for result in per_scenario for c in result.candidates]

    confusion: Counter = Counter()
    for c in all_candidates:
        confusion[(c.expected_type, c.predicted_type)] += 1

    class_metrics: Dict[str, Tuple[float, float, float]] = {}
    class_support: Dict[str, int] = {}
    for cls in CONFLICT_TYPES:
        tp = confusion[(cls, cls)]
        fp = sum(n for (expected, predicted), n in confusion.items() if predicted == cls and expected != cls)
        fn = sum(n for (expected, predicted), n in confusion.items() if expected == cls and predicted != cls)
        class_support[cls] = sum(n for (expected, _predicted), n in confusion.items() if expected == cls)
        class_metrics[cls] = prf_from_counts(tp, fp, fn)

    true_conflicts = [c for c in all_candidates if c.expected_type != "none"]
    prefilter_recall = (
        sum(1 for c in true_conflicts if c.prefilter_passed) / len(true_conflicts)
        if true_conflicts else None
    )

    return ConflictReport(
        class_metrics=class_metrics,
        class_support=class_support,
        confusion=dict(confusion),
        prefilter_recall=prefilter_recall,
        prefilter_true_conflict_n=len(true_conflicts),
        total_candidates=len(all_candidates),
        per_scenario=per_scenario,
    )
