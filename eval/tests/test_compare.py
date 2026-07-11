"""values_equal, arg_similarity, and conditions_equivalent."""

from __future__ import annotations

import pytest

from eval.scoring.compare import arg_similarity, conditions_equivalent, values_equal
from eval.tests.helpers import node


# ── values_equal ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("a, b", [
    (21, 21.0),
    (0.7, 0.7000001),
    (30, 30),
])
def test_values_equal_numeric_tolerance(a, b):
    assert values_equal(a, b) is True


def test_values_equal_numeric_mismatch():
    assert values_equal(21, 22) is False


@pytest.mark.parametrize("a, b", [
    (True, "true"),
    (True, "TRUE"),
    (False, "false"),
    (False, "False"),
])
def test_values_equal_bool_string_tolerance(a, b):
    assert values_equal(a, b) is True


def test_values_equal_string_is_case_sensitive():
    """Unlike numbers/bools, strings are exact -- a hex color or playlist
    name that differs in case is a real correctness signal, not noise."""
    assert values_equal("Regular", "regular") is False
    assert values_equal("#FF0000", "#ff0000") is False


# ── arg_similarity ────────────────────────────────────────────────────────

def test_arg_similarity_empty_expected_is_always_perfect():
    """No signal either way -- lets alignment fall through to the
    topological tie-break instead of guessing on unscored fields."""
    assert arg_similarity({}, {"anything": "goes"}) == 1.0
    assert arg_similarity({}, {}) == 1.0


def test_arg_similarity_partial_match():
    assert arg_similarity({"a": 1, "b": 2}, {"a": 1, "b": 3}) == 0.5


def test_arg_similarity_full_match():
    assert arg_similarity({"a": 1, "b": 2}, {"a": 1, "b": 2}) == 1.0


def test_arg_similarity_no_match():
    assert arg_similarity({"a": 1}, {"a": 2}) == 0.0


def test_arg_similarity_ignores_unlisted_generated_keys():
    """expected_args IS the allowlist -- extra generated keys the scenario
    author didn't declare as meaningful don't affect the score."""
    assert arg_similarity({"a": 1}, {"a": 1, "extra": "ignored"}) == 1.0


def test_arg_similarity_missing_key_counts_as_mismatch():
    assert arg_similarity({"a": 1, "b": 2}, {"a": 1}) == 0.5


# ── conditions_equivalent ─────────────────────────────────────────────────

def test_null_condition_equals_on_success():
    on_success = node("x", "d", "c", condition={"type": "on_success"}).condition
    id_map: dict = {}
    assert conditions_equivalent(None, on_success, id_map) is True
    assert conditions_equivalent(on_success, None, id_map) is True
    assert conditions_equivalent(None, None, id_map) is True


def test_condition_type_mismatch():
    n = node("x", "d", "c", condition={"type": "on_failure"})
    m = node("y", "d", "c", condition={"type": "on_success"})
    assert conditions_equivalent(n.condition, m.condition, {}) is False


def test_on_value_condition_translates_source_id_through_alignment():
    id_map = {"e1": "g1"}
    expected_cond = node("x", "d", "c", condition={
        "type": "on_value", "source_node_id": "e1", "field": "temp", "operator": ">", "value": 30,
    }).condition
    matching_generated_cond = node("y", "d", "c", condition={
        "type": "on_value", "source_node_id": "g1", "field": "temp", "operator": ">", "value": 30,
    }).condition

    assert conditions_equivalent(expected_cond, matching_generated_cond, id_map) is True


def test_on_value_condition_wrong_source_after_translation():
    id_map = {"e1": "g1"}
    expected_cond = node("x", "d", "c", condition={
        "type": "on_value", "source_node_id": "e1", "field": "temp", "operator": ">", "value": 30,
    }).condition
    wrong_source_cond = node("y", "d", "c", condition={
        "type": "on_value", "source_node_id": "g2", "field": "temp", "operator": ">", "value": 30,
    }).condition

    assert conditions_equivalent(expected_cond, wrong_source_cond, id_map) is False


def test_on_value_condition_unaligned_source_is_a_mismatch():
    """The expected condition's source node was never matched to anything
    (e.g. it was a missed node) -- can't verify the reference, so treat as
    a mismatch rather than silently passing."""
    id_map: dict = {}  # "e1" not present
    expected_cond = node("x", "d", "c", condition={
        "type": "on_value", "source_node_id": "e1", "field": "temp", "operator": ">", "value": 30,
    }).condition
    generated_cond = node("y", "d", "c", condition={
        "type": "on_value", "source_node_id": "g1", "field": "temp", "operator": ">", "value": 30,
    }).condition

    assert conditions_equivalent(expected_cond, generated_cond, id_map) is False


def test_all_condition_children_are_order_independent():
    id_map = {"n1": "n1"}
    expected_cond = node("x", "d", "c", condition={
        "type": "all",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "detected", "operator": "==", "value": True},
            {"type": "on_value", "source_node_id": "n1", "field": "confidence", "operator": ">=", "value": 0.7},
        ],
    }).condition
    generated_cond_swapped = node("y", "d", "c", condition={
        "type": "all",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "confidence", "operator": ">=", "value": 0.7},
            {"type": "on_value", "source_node_id": "n1", "field": "detected", "operator": "==", "value": True},
        ],
    }).condition

    assert conditions_equivalent(expected_cond, generated_cond_swapped, id_map) is True


def test_all_condition_mismatched_child_count():
    id_map = {"n1": "n1"}
    expected_cond = node("x", "d", "c", condition={
        "type": "all",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "detected", "operator": "==", "value": True},
            {"type": "on_value", "source_node_id": "n1", "field": "confidence", "operator": ">=", "value": 0.7},
        ],
    }).condition
    generated_cond = node("y", "d", "c", condition={
        "type": "all",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "detected", "operator": "==", "value": True},
        ],
    }).condition

    assert conditions_equivalent(expected_cond, generated_cond, id_map) is False


def test_any_condition_with_no_valid_pairing_is_false():
    """Each child in 'any' must pair with a distinct, matching child on the
    other side (an exact multiset match) -- not just 'some child matches
    some child' with reuse."""
    id_map = {"n1": "n1"}
    expected_cond = node("x", "d", "c", condition={
        "type": "any",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "a", "operator": "==", "value": 1},
            {"type": "on_value", "source_node_id": "n1", "field": "b", "operator": "==", "value": 2},
        ],
    }).condition
    generated_cond = node("y", "d", "c", condition={
        "type": "any",
        "conditions": [
            {"type": "on_value", "source_node_id": "n1", "field": "a", "operator": "==", "value": 1},
            {"type": "on_value", "source_node_id": "n1", "field": "a", "operator": "==", "value": 1},
        ],
    }).condition

    assert conditions_equivalent(expected_cond, generated_cond, id_map) is False
