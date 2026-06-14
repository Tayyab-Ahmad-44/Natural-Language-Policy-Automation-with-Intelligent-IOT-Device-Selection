"""
DAG validation and migration utilities.

- validate_dag(): checks for cycles, missing refs, orphans
- migrate_flat_to_dag(): converts old flat execution_plan to DAG format
- topological_levels(): returns nodes grouped by execution level
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple
from collections import defaultdict, deque
import schemas


# ──────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────

def validate_dag(dag: schemas.ExecutionDAG) -> schemas.DAGValidation:
    """
    Validate the DAG structure:
      1. No duplicate node IDs
      2. All dependency refs point to existing nodes
      3. All condition.source_node_id refs point to existing nodes
      4. No cycles (via Kahn's algorithm)
      5. No orphaned nodes (every non-root node is reachable from a root)
    Returns a DAGValidation with valid=True/False and error messages.
    """
    errors: List[str] = []
    node_ids = set()
    nodes_by_id: Dict[str, schemas.ExecutionNode] = {}

    # 1. Check duplicate IDs
    for node in dag.nodes:
        if node.id in node_ids:
            errors.append(f"Duplicate node ID: '{node.id}'")
        node_ids.add(node.id)
        nodes_by_id[node.id] = node

    if not dag.nodes:
        errors.append("DAG has no nodes")
        return schemas.DAGValidation(valid=False, errors=errors)

    # 2. Check dependency references
    for node in dag.nodes:
        for dep_id in node.dependencies:
            if dep_id not in node_ids:
                errors.append(
                    f"Node '{node.id}' depends on non-existent node '{dep_id}'"
                )

    # 3. Check condition source references
    for node in dag.nodes:
        _validate_condition_references(node, node.condition, node_ids, errors)

    # 4. Cycle detection via Kahn's algorithm
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    adj: Dict[str, List[str]] = defaultdict(list)
    for node in dag.nodes:
        for dep_id in node.dependencies:
            if dep_id in node_ids:
                adj[dep_id].append(node.id)
                in_degree[node.id] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    visited_count = 0
    while queue:
        nid = queue.popleft()
        visited_count += 1
        for child in adj[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if visited_count != len(node_ids):
        errors.append("DAG contains a cycle")

    return schemas.DAGValidation(valid=len(errors) == 0, errors=errors)


def _validate_condition_references(
    node: schemas.ExecutionNode,
    condition: schemas.ExecutionCondition | None,
    node_ids: set,
    errors: List[str],
) -> None:
    """Validate condition source refs, including nested all/any conditions."""
    if condition is None:
        return

    if condition.type == "on_value":
        src = condition.source_node_id
        if src and src not in node_ids:
            errors.append(
                f"Node '{node.id}' condition references non-existent "
                f"source node '{src}'"
            )
        if src and src not in node.dependencies:
            errors.append(
                f"Node '{node.id}' condition source '{src}' is not in "
                f"its dependencies list"
            )
        return

    if condition.type in ("all", "any"):
        nested = condition.conditions or []
        if not nested:
            errors.append(f"Node '{node.id}' has empty '{condition.type}' condition group")
        for child in nested:
            _validate_condition_references(node, child, node_ids, errors)


# ──────────────────────────────────────────────────────────────────
# Topological levels
# ──────────────────────────────────────────────────────────────────

def topological_levels(dag: schemas.ExecutionDAG) -> List[List[str]]:
    """
    Return nodes grouped by execution level (BFS layers).
    Level 0 = root nodes (no deps), Level 1 = nodes depending only on level-0, etc.
    Useful for frontend DAG layout.
    """
    node_ids = {n.id for n in dag.nodes}
    in_degree: Dict[str, int] = {n.id: 0 for n in dag.nodes}
    adj: Dict[str, List[str]] = defaultdict(list)

    for node in dag.nodes:
        for dep_id in node.dependencies:
            if dep_id in node_ids:
                adj[dep_id].append(node.id)
                in_degree[node.id] += 1

    levels: List[List[str]] = []
    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)

    while queue:
        level = list(queue)
        levels.append(level)
        next_queue: deque[str] = deque()
        for nid in level:
            for child in adj[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        queue = next_queue

    return levels


# ──────────────────────────────────────────────────────────────────
# Migration from old flat format
# ──────────────────────────────────────────────────────────────────

def migrate_flat_to_dag(execution_plan: Any) -> schemas.ExecutionDAG:
    """
    Convert a legacy flat execution_plan (list of dicts) to a DAG.
    All actions become parallel root nodes with no dependencies.
    """
    if isinstance(execution_plan, dict) and "nodes" in execution_plan:
        # Already DAG format
        return schemas.ExecutionDAG(**execution_plan)

    if not isinstance(execution_plan, list):
        return schemas.ExecutionDAG(nodes=[])

    nodes: List[schemas.ExecutionNode] = []
    for i, action in enumerate(execution_plan):
        if not isinstance(action, dict):
            continue
        nodes.append(schemas.ExecutionNode(
            id=f"step_{i + 1}",
            device=action.get("device", "Unknown"),
            capability=action.get("capability", "Unknown"),
            args=action.get("args", {}),
            dependencies=[],
            condition=None,
            on_failure="ignore",
        ))

    return schemas.ExecutionDAG(nodes=nodes)


def dag_to_dict(dag: schemas.ExecutionDAG) -> Dict[str, Any]:
    """Serialize an ExecutionDAG to a plain dict for JSON storage."""
    return dag.model_dump()


def ensure_dag(execution_plan: Any) -> schemas.ExecutionDAG:
    """
    Given raw execution_plan data (from DB JSON column),
    return a proper ExecutionDAG — handling both old and new formats.
    """
    if execution_plan is None:
        return schemas.ExecutionDAG(nodes=[])
    return migrate_flat_to_dag(execution_plan)
