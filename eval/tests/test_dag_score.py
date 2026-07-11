"""score_dag() end to end: P/R/F1 conventions (including the zero-denominator
edge cases), condition/failure-mode accuracy and their None-vs-0.0 handling,
and the strict exact_structural_match headline."""

from __future__ import annotations

from eval.scoring.dag_score import score_dag
from eval.tests.helpers import dag, node


def test_perfect_self_match_scores_everything_at_one():
    d = dag(
        node("e1", "Front Door Lock", "Lock", on_failure="halt_branch"),
        node("e2", "Security Camera", "Record", {"duration": 60}, deps=["e1"], condition={"type": "on_success"}),
    )

    score = score_dag(d, d)

    assert (score.node_precision, score.node_recall, score.node_f1) == (1.0, 1.0, 1.0)
    assert (score.edge_precision, score.edge_recall, score.edge_f1) == (1.0, 1.0, 1.0)
    assert score.condition_accuracy == 1.0
    assert score.failure_mode_accuracy == 1.0
    assert score.exact_structural_match is True


def test_both_empty_dags_are_vacuously_perfect():
    """Nothing expected, nothing generated: a correct prediction (of
    nothing), not an undefined non-answer."""
    score = score_dag(dag(), dag())

    assert (score.node_precision, score.node_recall, score.node_f1) == (1.0, 1.0, 1.0)
    assert (score.edge_precision, score.edge_recall, score.edge_f1) == (1.0, 1.0, 1.0)
    assert score.exact_structural_match is True


def test_generated_empty_when_nodes_expected_is_a_full_miss():
    expected = dag(node("e1", "Front Door Lock", "Lock"))

    score = score_dag(expected, dag())

    assert score.node_precision == 0.0
    assert score.node_recall == 0.0
    assert score.exact_structural_match is False


def test_generated_extra_when_nothing_expected_scores_zero_both_ways():
    """Documents the actual (sklearn zero_division=0-style) convention: each
    of precision/recall is independently zeroed against its own zero
    denominator, rather than treating 'nothing expected' as a vacuous
    perfect recall."""
    generated = dag(node("g1", "Front Door Lock", "Lock"))

    score = score_dag(dag(), generated)

    assert score.node_precision == 0.0
    assert score.node_recall == 0.0


def test_missing_node_and_extra_node_and_wrong_edge_and_wrong_failure_mode():
    expected = dag(
        node("e1", "Front Door Lock", "Lock", on_failure="halt_branch"),
        node("e2", "Garage Door", "Close", on_failure="skip_dependents"),
        node("e3", "Living Room Light", "Turn Off", on_failure="ignore"),
        node("e4", "Security Camera", "Record", {"duration": 60}, deps=["e1"], condition={"type": "on_success"}),
    )
    generated = dag(
        node("g1", "Front Door Lock", "Lock", on_failure="ignore"),  # wrong on_failure
        node("g2", "Garage Door", "Close", on_failure="skip_dependents"),
        # Living Room Light/Turn Off MISSING
        node("g3", "Security Camera", "Record", {"duration": 60}, on_failure="ignore"),  # edge dropped
        node("g4", "Security Camera", "Pan", {"angle": 90}, on_failure="ignore"),  # EXTRA node
    )

    score = score_dag(expected, generated, scenario_id="s", tags=["t"])

    assert score.node_precision == 3 / 4
    assert score.node_recall == 3 / 4
    assert score.edge_recall == 0.0  # the one real edge (Lock -> Record) was dropped
    assert score.failure_mode_accuracy == 2 / 3  # 3 matched nodes, 1 wrong (Lock)
    assert score.exact_structural_match is False
    assert score.scenario_id == "s"
    assert score.tags == ["t"]


def test_condition_accuracy_is_none_when_no_node_has_dependencies():
    d = dag(
        node("e1", "Front Door Lock", "Lock"),
        node("e2", "Garage Door", "Close"),
    )

    score = score_dag(d, d)

    assert score.condition_accuracy is None
    assert score.condition_n == 0


def test_condition_accuracy_null_vs_on_success_counts_as_correct():
    expected = dag(
        node("e1", "A", "read"),
        node("e2", "B", "act", deps=["e1"], condition=None),
    )
    generated = dag(
        node("g1", "A", "read"),
        node("g2", "B", "act", deps=["g1"], condition={"type": "on_success"}),
    )

    score = score_dag(expected, generated)

    assert score.condition_accuracy == 1.0
    assert score.condition_n == 1


def test_condition_accuracy_wrong_condition_type():
    expected = dag(
        node("e1", "A", "read"),
        node("e2", "B", "act", deps=["e1"], condition={"type": "on_success"}),
    )
    generated = dag(
        node("g1", "A", "read"),
        node("g2", "B", "act", deps=["g1"], condition={"type": "on_failure"}),
    )

    score = score_dag(expected, generated)

    assert score.condition_accuracy == 0.0


def test_edges_only_counted_between_matched_nodes_not_double_penalized():
    """A dependency edge whose source node was never matched (a miss) is
    excluded from the edge P/R/F1 computation entirely -- it was already
    penalized once at the node level."""
    expected = dag(
        node("e1", "Sensor", "Read"),  # this node will be missing from generated
        node("e2", "Fan", "SetSpeed", deps=["e1"], condition={"type": "on_success"}),
        node("e3", "Light", "TurnOn"),  # unrelated, independent, correctly generated
    )
    generated = dag(
        node("g2", "Fan", "SetSpeed"),  # Sensor/Read never generated -> its edge can't exist
        node("g3", "Light", "TurnOn"),
    )

    score = score_dag(expected, generated)

    # 2 of 3 nodes matched (Fan, Light); Sensor is a miss.
    assert score.node_recall == 2 / 3
    # The only expected edge (e1->e2) touches the missed node, so it's
    # excluded from the edge comparison rather than counted as an edge FN
    # on top of the node-level miss -- comparable sets are both empty here,
    # which is the vacuous-perfect convention.
    assert (score.edge_precision, score.edge_recall, score.edge_f1) == (1.0, 1.0, 1.0)


def test_exact_structural_match_false_on_wrong_edge_even_with_perfect_nodes():
    expected = dag(
        node("e1", "A", "x"),
        node("e2", "B", "y", deps=["e1"], condition={"type": "on_success"}),
    )
    generated = dag(
        node("g1", "A", "x"),
        node("g2", "B", "y"),  # same nodes, but missing the dependency edge
    )

    score = score_dag(expected, generated)

    assert score.node_f1 == 1.0
    assert score.exact_structural_match is False
