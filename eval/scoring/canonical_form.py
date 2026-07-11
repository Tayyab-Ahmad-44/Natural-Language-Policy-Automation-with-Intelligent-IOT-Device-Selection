"""
Self-contained DAG canonicalization, used only for the --repeats stability
metric: "how often does the pipeline produce the identical DAG twice", where
"identical" has to survive the LLM minting fresh step_N ids every run.

This is different from alignment (align.py), which matches nodes ACROSS two
DAGs (expected vs. generated). Here there is no "expected" -- we're comparing
N generated DAGs from repeated runs of the same scenario against each other
-- so each DAG is independently reduced to a hashable value: node identity,
args, on_failure and conditions all in canonical form, edges rewritten
against a deterministic local relabeling. Two DAGs canonicalize to the same
value iff score_dag() would call them an exact structural + condition +
failure-mode match.

KNOWN LIMITATION: when a DAG has two or more nodes with the exact same
canonical (device, capability) key AND identical args, but different
downstream edges/conditions, the deterministic sort used to assign local ids
can't distinguish them -- this is graph isomorphism under relabeling, which
is expensive to solve in general. At the DAG sizes this system produces
(3-6 nodes, such duplicates are rare), this hasn't been worth solving
exactly; two genuinely-isomorphic DAGs could theoretically canonicalize
differently in this edge case. Covered by a pytest case documenting the
limitation rather than silently hiding it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import schemas

from .align import canonical_key


def _canonical_value(value: Any) -> Any:
    """Recursively convert JSON-ish values (which may contain lists/dicts,
    unhashable) into nested tuples so they can sit inside a hashable,
    sortable canonical form."""
    if isinstance(value, list):
        return tuple(_canonical_value(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted(((k, _canonical_value(v)) for k, v in value.items()), key=repr))
    return value


def _args_key(args: Dict[str, Any]) -> Tuple:
    return tuple(sorted(((k, _canonical_value(v)) for k, v in args.items()), key=repr))


def _canonical_condition(condition: Optional[Any], local_id_of: Dict[str, str]) -> Tuple:
    """Same normalization semantics as compare.conditions_equivalent (null
    == on_success, all/any children order-independent), but producing a
    hashable canonical value instead of comparing two conditions."""
    c_type = "on_success" if condition is None else condition.type

    if c_type in ("on_success", "on_failure"):
        return (c_type,)

    if c_type == "on_value":
        local_source = local_id_of.get(condition.source_node_id or "")
        return (c_type, local_source, condition.field, condition.operator, _canonical_value(condition.value))

    if c_type in ("all", "any"):
        children = tuple(
            sorted(
                (_canonical_condition(child, local_id_of) for child in (condition.conditions or [])),
                key=repr,
            )
        )
        return (c_type, children)

    return (c_type,)


def canonicalize_dag(dag: schemas.ExecutionDAG) -> Tuple:
    """Reduce a DAG to a hashable value such that two DAGs produce the same
    value iff they're identical up to node-id renaming and declaration
    order: same nodes (device/capability/args/on_failure), same conditions,
    same dependency edges.
    """
    def sort_key(node: schemas.ExecutionNode) -> Tuple:
        return (canonical_key(node), repr(_args_key(node.args)))

    ordered = sorted(dag.nodes, key=sort_key)
    local_id_of = {n.id: f"L{i}" for i, n in enumerate(ordered)}

    node_tuples = tuple(
        (canonical_key(n), _args_key(n.args), n.on_failure)
        for n in ordered
    )
    condition_tuples = tuple(_canonical_condition(n.condition, local_id_of) for n in ordered)
    edges = tuple(sorted(
        (local_id_of[dep], local_id_of[n.id])
        for n in dag.nodes
        for dep in n.dependencies
        if dep in local_id_of and n.id in local_id_of
    ))

    return (node_tuples, condition_tuples, edges)
