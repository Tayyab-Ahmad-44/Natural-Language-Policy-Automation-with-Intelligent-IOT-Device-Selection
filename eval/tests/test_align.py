"""Node alignment edge cases: canonical-key grouping, duplicate-key
disambiguation (arg-similarity, then topological-position fallback), and
robustness against malformed generated DAGs (dangling deps, cycles)."""

from __future__ import annotations

from eval.scoring.align import align_nodes
from eval.tests.helpers import dag, node


def test_exact_one_to_one_match():
    expected = dag(node("e1", "Living Room Light", "Turn Off"))
    generated = dag(node("step_1", "Living Room Light", "Turn Off"))

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "step_1"}
    assert alignment.generated_to_expected == {"step_1": "e1"}
    assert alignment.unmatched_expected == []
    assert alignment.unmatched_generated == []


def test_canonical_key_is_case_and_whitespace_insensitive():
    expected = dag(node("e1", "Living Room Light", "Turn Off"))
    generated = dag(node("step_1", " living room light ", "TURN OFF"))

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "step_1"}


def test_missing_node_is_unmatched_expected():
    expected = dag(
        node("e1", "Front Door Lock", "Lock"),
        node("e2", "Garage Door", "Close"),
    )
    generated = dag(node("step_1", "Front Door Lock", "Lock"))

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "step_1"}
    assert alignment.unmatched_expected == ["e2"]
    assert alignment.unmatched_generated == []


def test_extra_node_is_unmatched_generated():
    expected = dag(node("e1", "Front Door Lock", "Lock"))
    generated = dag(
        node("step_1", "Front Door Lock", "Lock"),
        node("step_2", "Security Camera", "Pan"),
    )

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "step_1"}
    assert alignment.unmatched_generated == ["step_2"]


def test_disjoint_canonical_keys_leave_everything_unmatched():
    expected = dag(node("e1", "Front Door Lock", "Lock"))
    generated = dag(node("step_1", "Garage Door", "Close"))

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {}
    assert alignment.unmatched_expected == ["e1"]
    assert alignment.unmatched_generated == ["step_1"]


def test_duplicate_canonical_key_disambiguated_by_arg_similarity():
    """Two Smart Speaker/Set Volume nodes, generated in swapped declaration
    order but with distinguishable args -- alignment must follow the args,
    not positional order."""
    expected = dag(
        node("e1", "Smart Speaker", "Play Music", {"playlist": "Jazz"}),
        node("e2", "Smart Speaker", "Set Volume", {"level": 30}, deps=["e1"], condition={"type": "on_success"}),
        node("e3", "Smart Speaker", "Set Volume", {"level": 80}, deps=["e1"], condition={"type": "on_success"}),
    )
    generated = dag(
        node("g1", "Smart Speaker", "Play Music", {"playlist": "Jazz"}),
        node("g2", "Smart Speaker", "Set Volume", {"level": 80}, deps=["g1"], condition={"type": "on_success"}),
        node("g3", "Smart Speaker", "Set Volume", {"level": 30}, deps=["g1"], condition={"type": "on_success"}),
    )

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated["e2"] == "g3"  # level 30
    assert alignment.expected_to_generated["e3"] == "g2"  # level 80
    assert alignment.unmatched_expected == []
    assert alignment.unmatched_generated == []


def test_duplicate_canonical_key_falls_back_to_topological_position():
    """Two identical no-arg Security Camera/Snapshot nodes -- args carry no
    signal (empty expected_args -> similarity always 1.0), so alignment must
    fall back to topological level / declaration order."""
    expected = dag(
        node("e1", "Security Camera", "Snapshot"),
        node("e2", "Security Camera", "Snapshot", deps=["e1"], condition={"type": "on_success"}),
    )
    generated = dag(
        node("g1", "Security Camera", "Snapshot"),
        node("g2", "Security Camera", "Snapshot", deps=["g1"], condition={"type": "on_success"}),
    )

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "g1", "e2": "g2"}


def test_dangling_dependency_does_not_crash_alignment():
    """A generated node depends on a node id that doesn't exist in its own
    DAG -- malformed LLM output. topological_levels() silently ignores the
    dangling ref; alignment must still complete without a KeyError."""
    generated = dag(
        node("g1", "Front Door Lock", "Lock", deps=["nonexistent"]),
    )
    expected = dag(node("e1", "Front Door Lock", "Lock"))

    alignment = align_nodes(expected, generated)

    assert alignment.expected_to_generated == {"e1": "g1"}


def test_cyclic_generated_dag_does_not_crash_alignment():
    """A 2-node cycle in the generated DAG (A depends on B, B depends on A)
    -- neither node ever reaches in_degree 0, so dag_utils.topological_levels
    omits both entirely. The alignment's level fallback must still assign
    them a deterministic level instead of raising."""
    generated = dag(
        node("g1", "Front Door Lock", "Lock", deps=["g2"]),
        node("g2", "Front Door Lock", "Lock", deps=["g1"]),
    )
    expected = dag(
        node("e1", "Front Door Lock", "Lock"),
        node("e2", "Front Door Lock", "Lock"),
    )

    alignment = align_nodes(expected, generated)

    # Both sides have 2 identical-canonical-key nodes with no arg signal;
    # the important thing is it completes and produces a full 1:1 match,
    # not which specific id pairs with which.
    assert len(alignment.expected_to_generated) == 2
    assert alignment.unmatched_expected == []
    assert alignment.unmatched_generated == []


def test_empty_dags_produce_empty_alignment():
    alignment = align_nodes(dag(), dag())

    assert alignment.expected_to_generated == {}
    assert alignment.unmatched_expected == []
    assert alignment.unmatched_generated == []
