"""
Top-level deterministic DAG scorer. score_dag() is the only entry point:
give it an expected ExecutionDAG and a generated one, get back every metric
the harness reports. No LLM is used to judge structure anywhere in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

import schemas

from .align import Alignment, align_nodes
from .compare import conditions_equivalent
from .metrics import prf_from_counts


@dataclass
class ScenarioScore:
    scenario_id: str
    tags: List[str]

    node_precision: float
    node_recall: float
    node_f1: float

    edge_precision: float
    edge_recall: float
    edge_f1: float

    # None means "not applicable to this scenario" (e.g. no node had
    # dependencies) -- distinct from 0.0, which means "applicable and wrong".
    # Aggregation must exclude None, not treat it as a zero or a one.
    condition_accuracy: Optional[float]
    condition_n: int
    failure_mode_accuracy: Optional[float]
    failure_mode_n: int

    exact_structural_match: bool

    alignment: Alignment


def _edge_set(dag: schemas.ExecutionDAG) -> Set[Tuple[str, str]]:
    return {(dep, n.id) for n in dag.nodes for dep in n.dependencies}


def score_dag(
    expected: schemas.ExecutionDAG,
    generated: schemas.ExecutionDAG,
    scenario_id: str = "",
    tags: Optional[List[str]] = None,
) -> ScenarioScore:
    alignment = align_nodes(expected, generated)

    # ── Node-selection P/R/F1 (set comparison) ──────────────────────────
    node_tp = len(alignment.expected_to_generated)
    node_fp = len(alignment.unmatched_generated)
    node_fn = len(alignment.unmatched_expected)
    node_p, node_r, node_f1 = prf_from_counts(node_tp, node_fp, node_fn)

    # ── Dependency-structure P/R/F1 ──────────────────────────────────────
    # Edges are compared only between nodes that were successfully matched
    # on both sides. An edge touching an unmatched (missed/extra) node is
    # excluded here rather than double-counted as an edge-level error -- the
    # missing/extra node already cost precision/recall once, at the node
    # metric above.
    expected_edges = _edge_set(expected)
    generated_edges = _edge_set(generated)

    projected_expected_edges = {
        (alignment.expected_to_generated[src], alignment.expected_to_generated[tgt])
        for src, tgt in expected_edges
        if src in alignment.expected_to_generated and tgt in alignment.expected_to_generated
    }
    matched_generated_ids = set(alignment.generated_to_expected)
    comparable_generated_edges = {
        (src, tgt) for src, tgt in generated_edges
        if src in matched_generated_ids and tgt in matched_generated_ids
    }

    edge_tp = len(projected_expected_edges & comparable_generated_edges)
    edge_fp = len(comparable_generated_edges - projected_expected_edges)
    edge_fn = len(projected_expected_edges - comparable_generated_edges)
    edge_p, edge_r, edge_f1 = prf_from_counts(edge_tp, edge_fp, edge_fn)

    # ── Strict headline: exact structural match ─────────────────────────
    # Computed from exact set equality, not from precision/recall == 1.0, to
    # avoid float-equality flakiness on the boundary.
    exact_node_match = not alignment.unmatched_expected and not alignment.unmatched_generated
    exact_edge_match = projected_expected_edges == comparable_generated_edges
    exact_structural_match = exact_node_match and exact_edge_match

    # ── Condition accuracy (matched nodes that have dependencies) ───────
    # ── Failure-mode accuracy (all matched nodes) ────────────────────────
    expected_by_id = {n.id: n for n in expected.nodes}
    generated_by_id = {n.id: n for n in generated.nodes}

    condition_matches = condition_total = 0
    failure_matches = failure_total = 0
    for exp_id, gen_id in alignment.expected_to_generated.items():
        exp_node = expected_by_id[exp_id]
        gen_node = generated_by_id[gen_id]

        failure_total += 1
        if exp_node.on_failure == gen_node.on_failure:
            failure_matches += 1

        if exp_node.dependencies:
            condition_total += 1
            if conditions_equivalent(exp_node.condition, gen_node.condition, alignment.expected_to_generated):
                condition_matches += 1

    condition_accuracy = (condition_matches / condition_total) if condition_total else None
    failure_mode_accuracy = (failure_matches / failure_total) if failure_total else None

    return ScenarioScore(
        scenario_id=scenario_id,
        tags=tags or [],
        node_precision=node_p,
        node_recall=node_r,
        node_f1=node_f1,
        edge_precision=edge_p,
        edge_recall=edge_r,
        edge_f1=edge_f1,
        condition_accuracy=condition_accuracy,
        condition_n=condition_total,
        failure_mode_accuracy=failure_mode_accuracy,
        failure_mode_n=failure_total,
        exact_structural_match=exact_structural_match,
        alignment=alignment,
    )
