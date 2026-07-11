"""
Node alignment: match generated DAG nodes to expected DAG nodes so the
scorer can compute set/pair-based metrics on top. Node ids are useless for
this -- the LLM mints fresh "step_N" ids every run -- so alignment happens
on canonical (device, capability) identity, disambiguated by arg similarity,
falling back to topological position when that's not enough to tell nodes
apart (e.g. two "Smart Speaker"/"Set Volume" calls in one DAG).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import dag_utils
import schemas

from .compare import arg_similarity


@dataclass(frozen=True)
class Alignment:
    expected_to_generated: Dict[str, str]  # expected node id -> generated node id (matched pairs only)
    generated_to_expected: Dict[str, str]
    unmatched_expected: List[str]          # expected nodes with no generated match (misses)
    unmatched_generated: List[str]         # generated nodes with no expected match (extras)


def canonical_key(node: schemas.ExecutionNode) -> Tuple[str, str]:
    """(device, capability) identity, case/whitespace-insensitive.

    executor.py's resolve_capabilities() looks devices and capabilities up by
    `.lower()`, so a casing difference from the LLM wouldn't actually break
    execution. Scoring node identity case-sensitively would penalize the
    model for something the real system doesn't treat as an error.
    """
    return (node.device.strip().lower(), node.capability.strip().lower())


def _topo_levels(dag: schemas.ExecutionDAG) -> Dict[str, int]:
    """node id -> BFS level (0 = root). Nodes that never reach in_degree 0
    (a cycle, or a dependency on a nonexistent id) don't appear in
    dag_utils.topological_levels' output at all; park them one level past
    every real level so alignment still has a deterministic, non-crashing
    tie-break value instead of a KeyError on malformed LLM output.
    """
    levels = dag_utils.topological_levels(dag)
    level_of: Dict[str, int] = {}
    for level_idx, node_ids in enumerate(levels):
        for nid in node_ids:
            level_of[nid] = level_idx
    fallback_level = len(levels)
    for node in dag.nodes:
        level_of.setdefault(node.id, fallback_level)
    return level_of


def align_nodes(expected: schemas.ExecutionDAG, generated: schemas.ExecutionDAG) -> Alignment:
    exp_level = _topo_levels(expected)
    gen_level = _topo_levels(generated)

    exp_groups: Dict[Tuple[str, str], List[int]] = {}
    for i, n in enumerate(expected.nodes):
        exp_groups.setdefault(canonical_key(n), []).append(i)
    gen_groups: Dict[Tuple[str, str], List[int]] = {}
    for i, n in enumerate(generated.nodes):
        gen_groups.setdefault(canonical_key(n), []).append(i)

    expected_to_generated: Dict[str, str] = {}
    generated_to_expected: Dict[str, str] = {}

    for key in set(exp_groups) | set(gen_groups):
        exp_idxs = exp_groups.get(key, [])
        gen_idxs = gen_groups.get(key, [])
        if not exp_idxs or not gen_idxs:
            continue  # whole group absent on one side -> handled by the unmatched sweep below

        # Rank every possible (expected, generated) pair within this
        # canonical-key group by (-similarity, level_diff, index_diff), then
        # greedily assign starting from the best pair. This is the "greedy
        # by arg-similarity, then topological position" algorithm: DAGs here
        # are small (typically 3-6 nodes total) so a full optimal-assignment
        # solver would not change outcomes and isn't worth the dependency.
        candidates = []
        for rank_e, ei in enumerate(exp_idxs):
            en = expected.nodes[ei]
            for rank_g, gi in enumerate(gen_idxs):
                gn = generated.nodes[gi]
                similarity = arg_similarity(en.args, gn.args)
                level_diff = abs(exp_level.get(en.id, 0) - gen_level.get(gn.id, 0))
                index_diff = abs(rank_e - rank_g)
                candidates.append((-similarity, level_diff, index_diff, ei, gi))
        candidates.sort()

        claimed_e, claimed_g = set(), set()
        for _, _, _, ei, gi in candidates:
            if ei in claimed_e or gi in claimed_g:
                continue
            en, gn = expected.nodes[ei], generated.nodes[gi]
            expected_to_generated[en.id] = gn.id
            generated_to_expected[gn.id] = en.id
            claimed_e.add(ei)
            claimed_g.add(gi)

    unmatched_expected = [n.id for n in expected.nodes if n.id not in expected_to_generated]
    unmatched_generated = [n.id for n in generated.nodes if n.id not in generated_to_expected]

    return Alignment(
        expected_to_generated=expected_to_generated,
        generated_to_expected=generated_to_expected,
        unmatched_expected=unmatched_expected,
        unmatched_generated=unmatched_generated,
    )
