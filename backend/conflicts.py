"""
Policy conflict detection.

Hybrid approach:
  1. A cheap deterministic pre-filter finds candidate policies whose daily time
     window overlaps the new policy's AND that command at least one shared device.
  2. The LLM judges each candidate — contradiction / redundancy / overlap / none —
     and writes a plain-English explanation plus a suggested resolution. If the LLM
     is unavailable, a rule-based fallback classifies using capability polarity.

A "conflict" means: during overlapping time windows, two policies command the same
device in contradictory (or redundant) ways.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import dag_utils
import llm
import models


# ──────────────────────────────────────────────────────────────────
# Time-window helpers (windows are daily HH:MM and may wrap midnight)
# ──────────────────────────────────────────────────────────────────

def _parse_hhmm(value: Optional[str]) -> Optional[int]:
    if not value or not isinstance(value, str):
        return None
    try:
        hours, minutes = value.strip().split(":")
        return int(hours) * 60 + int(minutes)
    except Exception:
        return None


def _intervals(start: Optional[int], end: Optional[int]) -> List[tuple]:
    """Return the window as one or two [start, end] intervals on a 0–1440 line.
    A missing time means 'unknown' → treat as all-day. start > end wraps midnight."""
    if start is None or end is None:
        return [(0, 1440)]
    if start <= end:
        return [(start, end)]
    return [(start, 1440), (0, end)]  # wraps past midnight


def windows_overlap(s1, e1, s2, e2) -> bool:
    """Inclusive overlap test, so boundary-touching and point windows (from==to) count."""
    for a_start, a_end in _intervals(s1, e1):
        for b_start, b_end in _intervals(s2, e2):
            if a_start <= b_end and b_start <= a_end:
                return True
    return False


# ──────────────────────────────────────────────────────────────────
# Action / device extraction
# ──────────────────────────────────────────────────────────────────

def extract_actions(execution_plan: Any) -> List[Dict[str, Any]]:
    """Flatten a DAG (or legacy plan) into [{device, capability, args}, ...]."""
    dag = dag_utils.ensure_dag(execution_plan)
    return [
        {"device": node.device, "capability": node.capability, "args": node.args}
        for node in dag.nodes
    ]


def _devices(actions: List[Dict[str, Any]]) -> set:
    return {a["device"] for a in actions if a.get("device")}


# Keyword groups for rule-based contradiction hints.
_ACTIVATE = {
    "turn on", "power on", "switch on", "enable", "activate", "start", "open",
    "unlock", "arm", "play", "resume", "raise", "increase", "brew",
}
_DEACTIVATE = {
    "turn off", "power off", "switch off", "disable", "deactivate", "stop",
    "close", "lock", "disarm", "pause", "mute", "lower", "decrease",
}


def _polarity(capability: str) -> Optional[str]:
    c = (capability or "").lower()
    for kw in _DEACTIVATE:
        if kw in c:
            return "deactivate"
    for kw in _ACTIVATE:
        if kw in c:
            return "activate"
    # bare on/off as whole tokens
    tokens = set(c.replace("_", " ").replace("-", " ").split())
    if "off" in tokens:
        return "deactivate"
    if "on" in tokens:
        return "activate"
    return None


# ──────────────────────────────────────────────────────────────────
# Candidate descriptors
# ──────────────────────────────────────────────────────────────────

def candidates_from_db(db, exclude_policy_id: Optional[int] = None,
                       exclude_task_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Build conflict-candidate descriptors from all stored policies."""
    cands: List[Dict[str, Any]] = []
    for p in db.query(models.Policy).all():
        if exclude_policy_id is not None and p.id == exclude_policy_id:
            continue
        if exclude_task_id is not None and p.task_id == exclude_task_id:
            continue
        cands.append({
            "id": p.id,
            "name": p.name,
            "text": p.original_text or "",
            "window": {"from_time": p.start_time, "to_time": p.end_time},
            "actions": extract_actions(p.execution_plan),
        })
    return cands


# ──────────────────────────────────────────────────────────────────
# Detection
# ──────────────────────────────────────────────────────────────────

def detect_conflicts(new_policy: Dict[str, Any],
                     candidates: List[Dict[str, Any]],
                     use_llm: bool = True) -> List[Dict[str, Any]]:
    """
    new_policy: {name, text, window:{from_time,to_time}, actions:[{device,capability,args}]}
    candidates: list of the same shape, each optionally with an "id".
    Returns a list of conflict dicts (see _build_conflict for shape).
    """
    new_devices = _devices(new_policy.get("actions", []))
    ns = _parse_hhmm(new_policy.get("window", {}).get("from_time"))
    ne = _parse_hhmm(new_policy.get("window", {}).get("to_time"))

    flagged: List[Dict[str, Any]] = []
    for cand in candidates:
        cs = _parse_hhmm(cand.get("window", {}).get("from_time"))
        ce = _parse_hhmm(cand.get("window", {}).get("to_time"))
        if not windows_overlap(ns, ne, cs, ce):
            continue
        shared = new_devices & _devices(cand.get("actions", []))
        if not shared:
            continue
        flagged.append({"candidate": cand, "shared_devices": sorted(shared)})

    if not flagged:
        return []

    if use_llm:
        try:
            return _analyze_with_llm(new_policy, flagged)
        except Exception as e:  # noqa: BLE001 — degrade gracefully to rules
            print(f"Conflict LLM analysis failed, using rule fallback: {e}")

    return [_rule_conflict(new_policy, f) for f in flagged]


def _build_conflict(candidate, shared_devices, ctype, severity, explanation, suggestion):
    return {
        "policy_id": candidate.get("id"),
        "policy_name": candidate.get("name", ""),
        "existing_text": candidate.get("text", ""),
        "existing_window": candidate.get("window", {}),
        "shared_devices": shared_devices,
        "type": ctype,
        "severity": severity,
        "explanation": explanation,
        "suggestion": suggestion,
    }


def _rule_conflict(new_policy, flagged) -> Dict[str, Any]:
    cand = flagged["candidate"]
    shared = flagged["shared_devices"]
    new_pol = {a["device"]: _polarity(a["capability"]) for a in new_policy.get("actions", [])}
    old_pol = {a["device"]: _polarity(a["capability"]) for a in cand.get("actions", [])}

    ctype, severity = "overlap", "medium"
    explanation = f"Overlaps in time and both command: {', '.join(shared)}."
    for d in shared:
        np_, op_ = new_pol.get(d), old_pol.get(d)
        if np_ and op_ and np_ != op_:
            ctype, severity = "contradiction", "high"
            explanation = (
                f"On '{d}', the new policy will {np_} it while '{cand.get('name')}' "
                f"will {op_} it during the same time window."
            )
            break

    return _build_conflict(
        cand, shared, ctype, severity, explanation,
        "Review both policies — consider narrowing one time window or removing the redundant action.",
    )


def _analyze_with_llm(new_policy, flagged_list) -> List[Dict[str, Any]]:
    items = []
    for i, f in enumerate(flagged_list):
        c = f["candidate"]
        items.append({
            "index": i,
            "name": c.get("name"),
            "rule": c.get("text"),
            "time_window": c.get("window"),
            "shared_devices": f["shared_devices"],
            "actions": c.get("actions"),
        })

    prompt = f"""You are a policy conflict analyzer for an IoT automation system.
A NEW policy is about to be saved. Decide whether it conflicts with each EXISTING candidate policy below.

Definitions:
- "contradiction": during overlapping time windows they command the SAME device in opposing ways
  (e.g. one turns a light on while the other turns it off, lock vs unlock, open vs close, or both set
  the same property to DIFFERENT values). severity usually high.
- "redundancy": they command the same device to do the SAME thing in overlapping windows. severity low/medium.
- "none": they touch the same device in overlapping windows but the actions are independent and compatible.
- "overlap": ambiguous same-device/time situation you cannot confidently resolve. severity medium.

NEW policy:
  name: {new_policy.get('name')}
  rule: {new_policy.get('text')}
  time_window: {json.dumps(new_policy.get('window'))}
  actions: {json.dumps(new_policy.get('actions'))}

EXISTING candidate policies:
{json.dumps(items, indent=2)}

For EACH candidate, return an object:
{{"index": <int>, "type": "contradiction"|"redundancy"|"overlap"|"none",
  "severity": "high"|"medium"|"low",
  "explanation": "<one sentence naming the device and the clash>",
  "suggestion": "<a concrete better resolution, e.g. narrow a time window, or merge the two policies into one>"}}

Return ONLY JSON of the form {{"results": [ ... ]}}. No markdown, no prose.
"""

    response = llm.groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2048,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content or "{}")
    by_index = {r.get("index"): r for r in data.get("results", []) if isinstance(r, dict)}

    conflicts: List[Dict[str, Any]] = []
    for i, f in enumerate(flagged_list):
        r = by_index.get(i, {})
        ctype = r.get("type", "overlap")
        if ctype == "none":
            continue  # LLM cleared this false positive
        conflicts.append(_build_conflict(
            f["candidate"],
            f["shared_devices"],
            ctype,
            r.get("severity", "medium"),
            r.get("explanation", ""),
            r.get("suggestion", ""),
        ))
    return conflicts


# ──────────────────────────────────────────────────────────────────
# Endpoint-facing convenience
# ──────────────────────────────────────────────────────────────────

def check_against_existing(new_name: str, new_text: str, execution_dag,
                           time_window: Dict[str, str], db,
                           exclude_policy_id: Optional[int] = None,
                           use_llm: bool = True) -> List[Dict[str, Any]]:
    """Check a freshly-parsed (unsaved) policy against everything already stored."""
    new_policy = {
        "name": new_name,
        "text": new_text,
        "window": {
            "from_time": time_window.get("from_time"),
            "to_time": time_window.get("to_time"),
        },
        "actions": [
            {"device": n.device, "capability": n.capability, "args": n.args}
            for n in execution_dag.nodes
        ],
    }
    candidates = candidates_from_db(db, exclude_policy_id=exclude_policy_id)
    return detect_conflicts(new_policy, candidates, use_llm=use_llm)
