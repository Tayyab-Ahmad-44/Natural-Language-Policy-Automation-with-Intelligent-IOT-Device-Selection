"""canonicalize_dag(): the stability metric's building block. Two DAGs must
canonicalize identically iff they're the same DAG up to node-id renaming and
declaration order."""

from __future__ import annotations

from eval.scoring.canonical_form import canonicalize_dag
from eval.tests.helpers import dag, node


def test_identical_dag_different_ids_canonicalize_the_same():
    a = dag(
        node("a1", "Front Door Lock", "Lock", on_failure="halt_branch"),
        node("a2", "Security Camera", "Record", {"duration": 60}, deps=["a1"], condition={"type": "on_success"}),
    )
    b = dag(
        node("step_9", "Front Door Lock", "Lock", on_failure="halt_branch"),
        node("step_2", "Security Camera", "Record", {"duration": 60}, deps=["step_9"], condition={"type": "on_success"}),
    )

    assert canonicalize_dag(a) == canonicalize_dag(b)


def test_different_declaration_order_canonicalizes_the_same():
    a = dag(
        node("a1", "X", "y"),
        node("a2", "P", "q"),
    )
    b = dag(
        node("b1", "P", "q"),
        node("b2", "X", "y"),
    )

    assert canonicalize_dag(a) == canonicalize_dag(b)


def test_different_args_canonicalize_differently():
    a = dag(node("a1", "Thermostat", "Set Temp", {"temp": 21}))
    b = dag(node("b1", "Thermostat", "Set Temp", {"temp": 22}))

    assert canonicalize_dag(a) != canonicalize_dag(b)


def test_different_edge_structure_canonicalizes_differently():
    a = dag(
        node("a1", "A", "x"),
        node("a2", "B", "y", deps=["a1"], condition={"type": "on_success"}),
    )
    b = dag(
        node("b1", "A", "x"),
        node("b2", "B", "y"),  # same nodes, no dependency
    )

    assert canonicalize_dag(a) != canonicalize_dag(b)


def test_null_condition_and_on_success_canonicalize_the_same():
    a = dag(
        node("a1", "A", "x"),
        node("a2", "B", "y", deps=["a1"], condition=None),
    )
    b = dag(
        node("b1", "A", "x"),
        node("b2", "B", "y", deps=["b1"], condition={"type": "on_success"}),
    )

    assert canonicalize_dag(a) == canonicalize_dag(b)


def test_all_condition_children_order_does_not_affect_canonical_form():
    def make(order):
        conditions = [
            {"type": "on_value", "source_node_id": "n1", "field": "detected", "operator": "==", "value": True},
            {"type": "on_value", "source_node_id": "n1", "field": "confidence", "operator": ">=", "value": 0.7},
        ]
        if order == "swapped":
            conditions = list(reversed(conditions))
        return dag(
            node("n1", "Camera", "Analyze"),
            node("n2", "Light", "SetColor", deps=["n1"], condition={"type": "all", "conditions": conditions}),
        )

    assert canonicalize_dag(make("normal")) == canonicalize_dag(make("swapped"))


def test_wrong_condition_operator_canonicalizes_differently():
    a = dag(
        node("a1", "Sensor", "Read"),
        node("a2", "Fan", "SetSpeed", deps=["a1"], condition={
            "type": "on_value", "source_node_id": "a1", "field": "temp", "operator": ">", "value": 30,
        }),
    )
    b = dag(
        node("b1", "Sensor", "Read"),
        node("b2", "Fan", "SetSpeed", deps=["b1"], condition={
            "type": "on_value", "source_node_id": "b1", "field": "temp", "operator": "<", "value": 30,
        }),
    )

    assert canonicalize_dag(a) != canonicalize_dag(b)


def test_empty_dag_canonicalizes_without_crashing_and_matches_itself():
    assert canonicalize_dag(dag()) == canonicalize_dag(dag())
