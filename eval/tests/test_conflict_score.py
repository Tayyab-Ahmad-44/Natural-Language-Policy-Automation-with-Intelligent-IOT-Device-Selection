"""prefilter_holds() (against the real conflicts.windows_overlap -- pure,
offline, no network), and score_conflict_scenario/score_conflicts with an
injected detect_fn so the aggregation logic is tested independently of
conflicts.py's own classification behavior."""

from __future__ import annotations

from eval.scoring.conflict_score import prefilter_holds, score_conflict_scenario, score_conflicts


def _policy(name, from_time, to_time, device, capability="Lock"):
    return {
        "name": name,
        "text": "",
        "window": {"from_time": from_time, "to_time": to_time},
        "actions": [{"device": device, "capability": capability, "args": {}}],
    }


# ── prefilter_holds ───────────────────────────────────────────────────────

def test_prefilter_holds_when_time_and_device_both_overlap():
    new_policy = _policy("new", "18:00", "18:30", "Front Door Lock")
    candidate = _policy("cand", "18:00", "23:00", "Front Door Lock")

    assert prefilter_holds(new_policy, candidate) is True


def test_prefilter_drops_on_no_time_overlap():
    new_policy = _policy("new", "18:00", "18:30", "Front Door Lock")
    candidate = _policy("cand", "06:00", "08:00", "Front Door Lock")

    assert prefilter_holds(new_policy, candidate) is False


def test_prefilter_drops_on_no_shared_device():
    new_policy = _policy("new", "18:00", "18:30", "Front Door Lock")
    candidate = _policy("cand", "18:00", "18:30", "Garage Door")

    assert prefilter_holds(new_policy, candidate) is False


def test_prefilter_boundary_touching_windows_count_as_overlap():
    """windows_overlap() is documented as inclusive -- a window that only
    touches at a single boundary point still counts."""
    new_policy = _policy("new", "20:00", "23:00", "Living Room Light")
    candidate = _policy("cand", "23:00", "23:30", "Living Room Light")

    assert prefilter_holds(new_policy, candidate) is True


def test_prefilter_handles_midnight_wrap_true_overlap():
    new_policy = _policy("new", "21:00", "06:00", "IV Drip")  # wraps midnight
    candidate = _policy("cand", "22:00", "23:00", "IV Drip")  # inside the wrapped window

    assert prefilter_holds(new_policy, candidate) is True


def test_prefilter_handles_midnight_wrap_true_non_overlap():
    new_policy = _policy("new", "21:00", "06:00", "IV Drip")  # wraps midnight
    candidate = _policy("cand", "08:00", "20:00", "IV Drip")  # entirely outside, same device

    assert prefilter_holds(new_policy, candidate) is False


# ── score_conflict_scenario / score_conflicts (injected detect_fn) ────────

def _fake_detect(results_by_name):
    """Build a detect_fn stand-in for conflicts.detect_conflicts: returns
    canned {policy_name, type} dicts for exactly the candidates named in
    results_by_name; anything else is implicitly 'none' (absent)."""
    def detect_fn(new_policy, candidates, use_llm):
        return [
            {"policy_id": None, "policy_name": name, "type": ctype}
            for name, ctype in results_by_name.items()
        ]
    return detect_fn


def test_score_conflict_scenario_matches_predictions_by_name():
    scenario = {
        "id": "s1",
        "new_policy": _policy("new", "18:00", "19:00", "Front Door Lock", "Unlock"),
        "candidates": [
            {**_policy("Night Lockdown", "18:00", "23:00", "Front Door Lock", "Lock"), "expected_type": "contradiction"},
            {**_policy("Garage Auto Close", "18:00", "19:00", "Garage Door", "Close"), "expected_type": "none"},
        ],
    }
    detect_fn = _fake_detect({"Night Lockdown": "contradiction"})

    result = score_conflict_scenario(scenario, detect_fn=detect_fn)

    by_name = {c.name: c for c in result.candidates}
    assert by_name["Night Lockdown"].predicted_type == "contradiction"
    assert by_name["Night Lockdown"].expected_type == "contradiction"
    # Garage Auto Close never appears in detect_fn's output -> defaults to "none".
    assert by_name["Garage Auto Close"].predicted_type == "none"
    assert by_name["Garage Auto Close"].prefilter_passed is False  # different device


def test_score_conflicts_aggregates_class_metrics_and_confusion():
    scenarios = [{
        "id": "s1",
        "new_policy": _policy("new", "18:00", "19:00", "Front Door Lock", "Unlock"),
        "candidates": [
            {**_policy("cand-A", "18:00", "19:00", "Front Door Lock", "Lock"), "expected_type": "contradiction"},
            {**_policy("cand-B", "18:00", "19:00", "Front Door Lock", "Unlock"), "expected_type": "redundancy"},
        ],
    }]
    # Deliberately wrong prediction for cand-B (predicts contradiction, gold is redundancy),
    # and cand-A predicted correctly.
    detect_fn = _fake_detect({"cand-A": "contradiction", "cand-B": "contradiction"})

    report = score_conflicts(scenarios, detect_fn=detect_fn)

    assert report.total_candidates == 2
    assert report.confusion[("contradiction", "contradiction")] == 1
    assert report.confusion[("redundancy", "contradiction")] == 1

    p, r, f1 = report.class_metrics["contradiction"]
    assert p == 0.5  # 1 correct out of 2 predicted-as-contradiction
    assert r == 1.0  # the 1 true contradiction was found

    p, r, f1 = report.class_metrics["redundancy"]
    assert p == 0.0
    assert r == 0.0  # the 1 true redundancy was missed entirely


def test_prefilter_recall_in_isolation_reflects_true_conflicts_dropped():
    """A true conflict whose time window doesn't overlap never reaches the
    classifier -- prefilter_recall must reflect that miss regardless of
    what the (in this case irrelevant) detect_fn predicts."""
    scenarios = [{
        "id": "s1",
        "new_policy": _policy("new", "18:00", "19:00", "Front Door Lock", "Unlock"),
        "candidates": [
            {**_policy("caught", "18:00", "19:00", "Front Door Lock", "Lock"), "expected_type": "contradiction"},
            {**_policy("dropped", "06:00", "07:00", "Front Door Lock", "Lock"), "expected_type": "contradiction"},
            {**_policy("irrelevant", "18:00", "19:00", "Garage Door", "Close"), "expected_type": "none"},
        ],
    }]
    detect_fn = _fake_detect({})  # predictions don't matter for this assertion

    report = score_conflicts(scenarios, detect_fn=detect_fn)

    # 1 of 2 true-conflict candidates ("caught") passes the pre-filter; "dropped" doesn't overlap in time.
    assert report.prefilter_true_conflict_n == 2
    assert report.prefilter_recall == 0.5


def test_prefilter_recall_is_none_when_no_true_conflicts_exist():
    scenarios = [{
        "id": "s1",
        "new_policy": _policy("new", "18:00", "19:00", "Front Door Lock", "Unlock"),
        "candidates": [
            {**_policy("cand", "18:00", "19:00", "Front Door Lock", "Status"), "expected_type": "none"},
        ],
    }]
    detect_fn = _fake_detect({})

    report = score_conflicts(scenarios, detect_fn=detect_fn)

    assert report.prefilter_recall is None
    assert report.prefilter_true_conflict_n == 0
