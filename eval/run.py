"""
eval/run.py -- the harness's CLI entry point.

Runs every DAG scenario (optionally N times each, for structural-stability
measurement) through the real llm.parse_policy_with_llm, and every conflict
scenario through conflicts.detect_conflicts, aggregates metrics overall and
sliced by tag, prints a summary table, and writes a JSON report.

    python -m eval.run                  # real Groq calls, 1 repeat each
    python -m eval.run --repeats 5      # + structural-stability measurement
    python -m eval.run --mock           # no network: wiring smoke test only
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import eval as _eval_bootstrap  # noqa: F401  (side effect: backend/ on sys.path, placeholder API keys)
import llm
import llm_provider
import schemas
from eval import PLACEHOLDER_GROQ_API_KEY, PLACEHOLDER_OPENAI_API_KEY
from eval.loaders import DagScenario, load_all_conflict_scenarios, load_all_dag_scenarios
from eval.scoring import ConflictReport, ScenarioScore, canonicalize_dag, score_conflicts, score_dag

REPORT_DIR = pathlib.Path(__file__).resolve().parent / "reports"


# ── Mock DAG generation (wiring smoke test, no network) ─────────────────

def _remap_condition_ids(condition: Optional[Any], id_map: Dict[str, str]) -> None:
    if condition is None:
        return
    if condition.source_node_id:
        condition.source_node_id = id_map.get(condition.source_node_id, condition.source_node_id)
    for child in (condition.conditions or []):
        _remap_condition_ids(child, id_map)


def _mock_generate(scenario: DagScenario) -> schemas.ExecutionDAG:
    """Echo the expected DAG back with relabeled node ids, so --mock still
    exercises the full runner + scorer + id-independent alignment pipeline
    end to end without any network call. Always scores perfectly -- it's a
    wiring check, not a model-quality check.
    """
    dag = scenario.expected_dag.model_copy(deep=True)
    id_map = {n.id: f"mock_{i + 1}" for i, n in enumerate(dag.nodes)}
    for n in dag.nodes:
        n.dependencies = [id_map[d] for d in n.dependencies]
        _remap_condition_ids(n.condition, id_map)
        n.id = id_map[n.id]
    return dag


def _real_generate(scenario: DagScenario) -> schemas.ExecutionDAG:
    response = llm.parse_policy_with_llm(scenario.nl, scenario.devices_data)
    return response.execution_dag


# ── DAG scenario execution + aggregation ─────────────────────────────────

@dataclasses.dataclass
class DagRunResult:
    scenario_id: str
    tags: List[str]
    repeat_scores: List[ScenarioScore]
    stability: float
    repeats: int


def run_dag_scenario(scenario: DagScenario, repeats: int, mock: bool) -> DagRunResult:
    generated_dags = [
        _mock_generate(scenario) if mock else _real_generate(scenario)
        for _ in range(repeats)
    ]
    scores = [
        score_dag(scenario.expected_dag, dag, scenario_id=scenario.id, tags=scenario.tags)
        for dag in generated_dags
    ]

    canonical_forms = [canonicalize_dag(dag) for dag in generated_dags]
    mode_count = Counter(canonical_forms).most_common(1)[0][1]
    stability = mode_count / len(canonical_forms)

    return DagRunResult(
        scenario_id=scenario.id,
        tags=scenario.tags,
        repeat_scores=scores,
        stability=stability,
        repeats=repeats,
    )


def _mean(values: List[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    return (sum(present) / len(present)) if present else None


@dataclasses.dataclass
class AggregateMetrics:
    n_scenarios: int
    node_precision: Optional[float]
    node_recall: Optional[float]
    node_f1: Optional[float]
    edge_precision: Optional[float]
    edge_recall: Optional[float]
    edge_f1: Optional[float]
    condition_accuracy: Optional[float]
    condition_n_scenarios: int  # scenarios that had >=1 node with dependencies
    failure_mode_accuracy: Optional[float]
    exact_structural_match_rate: Optional[float]
    stability: Optional[float]


def aggregate_dag_results(results: List[DagRunResult]) -> AggregateMetrics:
    """Macro-average: mean across a scenario's repeats first, then mean
    across scenarios. A scenario run 5 times counts once in the final
    number, same as a scenario run once -- repeats reduce per-scenario
    noise, they don't add extra weight to that scenario in the aggregate.
    """
    def per_scenario(metric_fn) -> List[Optional[float]]:
        return [_mean([metric_fn(s) for s in r.repeat_scores]) for r in results]

    condition_means = per_scenario(lambda s: s.condition_accuracy)

    return AggregateMetrics(
        n_scenarios=len(results),
        node_precision=_mean(per_scenario(lambda s: s.node_precision)),
        node_recall=_mean(per_scenario(lambda s: s.node_recall)),
        node_f1=_mean(per_scenario(lambda s: s.node_f1)),
        edge_precision=_mean(per_scenario(lambda s: s.edge_precision)),
        edge_recall=_mean(per_scenario(lambda s: s.edge_recall)),
        edge_f1=_mean(per_scenario(lambda s: s.edge_f1)),
        condition_accuracy=_mean(condition_means),
        condition_n_scenarios=sum(1 for v in condition_means if v is not None),
        failure_mode_accuracy=_mean(per_scenario(lambda s: s.failure_mode_accuracy)),
        exact_structural_match_rate=_mean(per_scenario(lambda s: 1.0 if s.exact_structural_match else 0.0)),
        stability=_mean([r.stability for r in results]),
    )


# ── Reporting ─────────────────────────────────────────────────────────────

def _fmt(v: Optional[float]) -> str:
    return "  n/a" if v is None else f"{v:5.2f}"


def print_summary(
    dag_overall: AggregateMetrics,
    dag_by_tag: Dict[str, AggregateMetrics],
    conflict_report: ConflictReport,
    repeats: int,
    mock: bool,
) -> None:
    print("=" * 96)
    print(f"DAG GENERATION  (scenarios={dag_overall.n_scenarios}, repeats={repeats}, mock={mock})")
    print("=" * 96)
    print(f"{'slice':22s} {'nodeP':>6s} {'nodeR':>6s} {'nodeF1':>7s} {'edgeP':>6s} {'edgeR':>6s} "
          f"{'edgeF1':>7s} {'cond':>6s} {'fail':>6s} {'exact':>6s} {'stab':>6s}")

    def row(name: str, m: AggregateMetrics) -> None:
        print(f"{name:22s} {_fmt(m.node_precision):>6s} {_fmt(m.node_recall):>6s} {_fmt(m.node_f1):>7s} "
              f"{_fmt(m.edge_precision):>6s} {_fmt(m.edge_recall):>6s} {_fmt(m.edge_f1):>7s} "
              f"{_fmt(m.condition_accuracy):>6s} {_fmt(m.failure_mode_accuracy):>6s} "
              f"{_fmt(m.exact_structural_match_rate):>6s} {_fmt(m.stability):>6s}")

    row("overall", dag_overall)
    for tag in sorted(dag_by_tag):
        row(f"  tag:{tag}", dag_by_tag[tag])
    print(f"(cond = condition accuracy over the {dag_overall.condition_n_scenarios} scenario(s) "
          f"with a conditional node; exact = strict node-set+edge-set match rate; stab = mode-agreement "
          f"rate across repeats)")

    print()
    print("=" * 96)
    print(f"CONFLICT DETECTION  (candidates={conflict_report.total_candidates}, mock={mock})")
    print("=" * 96)
    print(f"{'class':16s} {'P':>6s} {'R':>6s} {'F1':>6s} {'support':>8s}")
    for cls in ("contradiction", "redundancy", "overlap", "none"):
        p, r, f1 = conflict_report.class_metrics[cls]
        print(f"{cls:16s} {p:6.2f} {r:6.2f} {f1:6.2f} {conflict_report.class_support[cls]:8d}")
    pf = conflict_report.prefilter_recall
    pf_str = "n/a" if pf is None else f"{pf:.2f}"
    print()
    print(f"pre-filter recall (over true-conflict candidates only): {pf_str} "
          f"(n={conflict_report.prefilter_true_conflict_n})")


def _conflict_report_json(report: ConflictReport) -> Dict[str, Any]:
    d = dataclasses.asdict(report)
    # dict keys must be strings for JSON; confusion is keyed by (expected, predicted) tuples.
    d["confusion"] = {f"{expected}->{predicted}": n for (expected, predicted), n in report.confusion.items()}
    return d


def _warn_if_placeholder_key(mock: bool) -> None:
    if mock:
        return
    # Check whichever provider LLM_PROVIDER actually selected, not just Groq --
    # llm_provider.client was already built against one specific key at import
    # time, so that's the one that matters for this run.
    active_var, placeholder = (
        ("OPENAI_API_KEY", PLACEHOLDER_OPENAI_API_KEY) if llm_provider.LLM_PROVIDER == "openai"
        else ("GROQ_API_KEY", PLACEHOLDER_GROQ_API_KEY)
    )
    if os.environ.get(active_var) == placeholder:
        print(f"WARNING: {active_var} is unset (eval's own no-op placeholder is active).", file=sys.stderr)
        print(f"         LLM_PROVIDER={llm_provider.LLM_PROVIDER!r}. DAG generation will silently fall back", file=sys.stderr)
        print("         to empty DAGs, and the conflict LLM judge will silently fall back to the", file=sys.stderr)
        print("         rule-based classifier -- both real codepaths already catch the resulting API", file=sys.stderr)
        print("         errors rather than crashing, so this run will complete but the numbers won't", file=sys.stderr)
        print(f"         reflect real model behavior. Set a real {active_var}, or pass --mock for an", file=sys.stderr)
        print("         offline wiring smoke test.", file=sys.stderr)
        print(file=sys.stderr)


# ── Entry point ───────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the NL->DAG + conflict-detector eval harness.")
    parser.add_argument("--repeats", type=int, default=1,
                         help="Run each DAG scenario N times for structural-stability measurement (default: 1).")
    parser.add_argument("--mock", action="store_true",
                         help="No network calls: DAG generation echoes the expected DAG (relabeled ids), "
                              "conflicts use the offline rule-based fallback. For wiring smoke tests.")
    parser.add_argument("--out", type=pathlib.Path, default=None,
                         help="JSON report output path (default: eval/reports/report_<timestamp>.json)")
    args = parser.parse_args(argv)

    _warn_if_placeholder_key(args.mock)

    dag_scenarios = load_all_dag_scenarios()
    conflict_scenarios = load_all_conflict_scenarios()

    dag_results = [run_dag_scenario(sc, repeats=args.repeats, mock=args.mock) for sc in dag_scenarios]
    dag_overall = aggregate_dag_results(dag_results)
    all_tags = sorted({tag for r in dag_results for tag in r.tags})
    dag_by_tag = {tag: aggregate_dag_results([r for r in dag_results if tag in r.tags]) for tag in all_tags}

    # In --mock mode, conflicts also stay fully offline via the rule-based
    # fallback (use_llm=False) -- it's already a network-free codepath, so
    # there's no need for a second mock mechanism just for conflicts.
    conflict_report = score_conflicts(conflict_scenarios, use_llm=not args.mock)

    print_summary(dag_overall, dag_by_tag, conflict_report, args.repeats, args.mock)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    out_path = args.out or (REPORT_DIR / f"report_{timestamp}.json")
    report_json = {
        "generated_at": timestamp,
        "repeats": args.repeats,
        "mock": args.mock,
        "dag": {
            "overall": dataclasses.asdict(dag_overall),
            "by_tag": {tag: dataclasses.asdict(agg) for tag, agg in dag_by_tag.items()},
            "scenarios": [
                {
                    "id": r.scenario_id,
                    "tags": r.tags,
                    "stability": r.stability,
                    "repeat_scores": [dataclasses.asdict(s) for s in r.repeat_scores],
                }
                for r in dag_results
            ],
        },
        "conflicts": _conflict_report_json(conflict_report),
    }
    out_path.write_text(json.dumps(report_json, indent=2))
    print()
    print(f"JSON report written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
