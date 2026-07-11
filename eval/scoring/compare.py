"""
Value-, arg-, and condition-comparison primitives used by the aligner and
the scorer. No LLM calls, no I/O -- pure functions over plain values and
schemas.ExecutionCondition objects.
"""

from __future__ import annotations

import itertools
import math
from typing import Any, Dict, Optional


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def values_equal(expected: Any, generated: Any) -> bool:
    """Typed-tolerant equality for arg values and on_value condition values.

    Numbers compare with a relative tolerance (an LLM might decode 21 vs
    21.0, or 0.7 vs 0.700001 after JSON round-tripping). Bools tolerate the
    "true"/"false" string form some LLMs emit. Everything else -- strings,
    hex colors, playlist names -- is exact and case-sensitive: those ARE
    meaningful correctness signals, not formatting noise.
    """
    if _is_number(expected) and _is_number(generated):
        return math.isclose(float(expected), float(generated), rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(expected, bool) or isinstance(generated, bool):
        def as_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() == "true"
            return bool(v)
        return as_bool(expected) == as_bool(generated)
    return expected == generated


def arg_similarity(expected_args: Dict[str, Any], generated_args: Dict[str, Any]) -> float:
    """Fraction of expected_args keys whose value matches in generated_args.

    expected_args IS the allowlist: only keys the scenario author declared as
    meaningful are checked, and unlisted generated keys are ignored entirely.
    Empty expected_args (e.g. a VLM node's free-text prompt) returns 1.0 --
    no signal either way -- so node alignment falls through to the
    topological-position tie-break instead of guessing on unscored fields.
    """
    if not expected_args:
        return 1.0
    matched = sum(
        1
        for k, v in expected_args.items()
        if k in generated_args and values_equal(v, generated_args[k])
    )
    return matched / len(expected_args)


def conditions_equivalent(
    expected_cond: Optional[Any],
    generated_cond: Optional[Any],
    expected_to_generated_id: Dict[str, str],
) -> bool:
    """Semantic (not structural) condition equality, matching what
    executor.py's evaluate_condition() actually treats as identical:
    null and {type: on_success} are the same thing, and 'all'/'any' children
    have no inherent order. source_node_id references are translated through
    the node alignment map before comparison, since expected/generated node
    ids are never the same strings.
    """
    e_type = "on_success" if expected_cond is None else expected_cond.type
    g_type = "on_success" if generated_cond is None else generated_cond.type
    if e_type != g_type:
        return False

    if e_type in ("on_success", "on_failure"):
        return True

    if e_type == "on_value":
        if expected_cond.operator != generated_cond.operator:
            return False
        if expected_cond.field != generated_cond.field:
            return False
        if not values_equal(expected_cond.value, generated_cond.value):
            return False
        mapped_source = expected_to_generated_id.get(expected_cond.source_node_id or "")
        return mapped_source is not None and mapped_source == generated_cond.source_node_id

    if e_type in ("all", "any"):
        e_children = expected_cond.conditions or []
        g_children = generated_cond.conditions or []
        if len(e_children) != len(g_children):
            return False
        # Brute-force permutation matching rather than greedy: with the
        # small child counts these conditions actually have (2-4), an exact
        # multiset match is cheap and avoids greedy false negatives where a
        # locally-plausible-but-wrong pairing blocks the true match.
        for perm in itertools.permutations(g_children):
            if all(
                conditions_equivalent(ec, gc, expected_to_generated_id)
                for ec, gc in zip(e_children, perm)
            ):
                return True
        return False

    return False
