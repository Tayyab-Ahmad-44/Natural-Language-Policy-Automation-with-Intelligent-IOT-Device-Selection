"""
LangGraph-based DAG executor for IoT policy orchestration.

Dynamically constructs a LangGraph StateGraph from the LLM-generated DAG JSON.
Each device action becomes a graph node that makes an async HTTP call.
Dependencies become edges; conditions become conditional routing.
"""

from __future__ import annotations

import asyncio
import json
import operator as op_module
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict, Annotated
from collections import defaultdict

import httpx
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, START, END

import models
import schemas
import dag_utils
import vision


# ──────────────────────────────────────────────────────────────────
# Graph state
# ──────────────────────────────────────────────────────────────────

def _merge_dicts(a: Dict, b: Dict) -> Dict:
    """Reducer that merges two dicts (used for node_results accumulation)."""
    merged = {**a, **b}
    return merged


class GraphState(TypedDict):
    """Shared state flowing through the LangGraph."""
    node_results: Annotated[Dict[str, Any], _merge_dicts]
    # Maps node_id -> {"status": str, "response_data": dict|None, "error": str|None, "http_status_code": int|None}
    failed_nodes: Annotated[list, op_module.add]
    skipped_nodes: Annotated[list, op_module.add]


# ──────────────────────────────────────────────────────────────────
# Condition evaluation
# ──────────────────────────────────────────────────────────────────

def _get_nested_field(data: Any, field_path: str) -> Any:
    """Get a value from nested dict using dot-path, e.g. 'temp' or 'data.readings.temp'."""
    if data is None:
        return None
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def evaluate_condition(
    condition: Optional[schemas.ExecutionCondition],
    dependencies: List[str],
    node_results: Dict[str, Any],
) -> bool:
    """
    Evaluate whether a node's condition is met based on dependency results.
    Returns True if the node should execute, False if it should be skipped.
    """
    # No condition = execute when all deps succeed (default)
    if condition is None:
        for dep_id in dependencies:
            result = node_results.get(dep_id, {})
            if result.get("status") != "success":
                return False
        return True

    if condition.type == "on_success":
        for dep_id in dependencies:
            result = node_results.get(dep_id, {})
            if result.get("status") != "success":
                return False
        return True

    if condition.type == "on_failure":
        # Execute if ANY dependency failed
        for dep_id in dependencies:
            result = node_results.get(dep_id, {})
            if result.get("status") == "failed":
                return True
        return False

    if condition.type == "all":
        nested = condition.conditions or []
        return all(evaluate_condition(child, dependencies, node_results) for child in nested)

    if condition.type == "any":
        nested = condition.conditions or []
        return any(evaluate_condition(child, dependencies, node_results) for child in nested)

    if condition.type == "on_value":
        src_id = condition.source_node_id
        if not src_id:
            return True
        result = node_results.get(src_id, {})
        if result.get("status") != "success":
            return False

        response_data = result.get("response_data")
        actual_value = _get_nested_field(response_data, condition.field or "")
        if actual_value is None:
            return False

        expected = condition.value
        cond_op = condition.operator

        try:
            # Try numeric comparison
            actual_num = float(actual_value) if not isinstance(actual_value, (int, float)) else actual_value
            expected_num = float(expected) if not isinstance(expected, (int, float)) else expected

            if cond_op == ">":
                return actual_num > expected_num
            elif cond_op == "<":
                return actual_num < expected_num
            elif cond_op == ">=":
                return actual_num >= expected_num
            elif cond_op == "<=":
                return actual_num <= expected_num
            elif cond_op == "==":
                return actual_num == expected_num
            elif cond_op == "!=":
                return actual_num != expected_num
        except (ValueError, TypeError):
            pass

        # String-based comparison fallback
        actual_str = str(actual_value)
        expected_str = str(expected)

        if cond_op == "==":
            return actual_str == expected_str
        elif cond_op == "!=":
            return actual_str != expected_str
        elif cond_op == "contains":
            return expected_str in actual_str

        return True

    return True


# ──────────────────────────────────────────────────────────────────
# Transitive dependents (for halt_branch)
# ──────────────────────────────────────────────────────────────────

def _get_all_dependents(node_id: str, adj: Dict[str, List[str]]) -> set:
    """BFS to find all transitive dependents of a node."""
    visited = set()
    queue = [node_id]
    while queue:
        nid = queue.pop(0)
        for child in adj.get(nid, []):
            if child not in visited:
                visited.add(child)
                queue.append(child)
    return visited


# ──────────────────────────────────────────────────────────────────
# Capability resolution
# ──────────────────────────────────────────────────────────────────

def resolve_capabilities(dag: schemas.ExecutionDAG, db: Session) -> Dict[str, Dict]:
    """
    For each node in the DAG, look up the actual Capability URL and method
    from the database by matching device name + capability name.
    Returns: {node_id: {"url": str, "method": str}} or None if not found.
    """
    # Pre-fetch all devices with capabilities
    devices = db.query(models.Device).all()
    lookup: Dict[str, Dict[str, models.Capability]] = {}
    for device in devices:
        cap_map = {}
        for cap in device.capabilities:
            cap_map[cap.name.lower()] = cap
        lookup[device.name.lower()] = cap_map

    result = {}
    for node in dag.nodes:
        device_caps = lookup.get(node.device.lower(), {})
        cap = device_caps.get(node.capability.lower())
        if cap:
            result[node.id] = {
                "url": cap.url,
                "method": cap.method.upper(),
                "device_id": device.id,
                "cap_name": cap.name,
            }
        else:
            result[node.id] = None  # Device/capability not found
    return result


# ──────────────────────────────────────────────────────────────────
# Node function factory
# ──────────────────────────────────────────────────────────────────

def make_node_fn(
    node: schemas.ExecutionNode,
    cap_info: Optional[Dict],
    all_nodes: Dict[str, schemas.ExecutionNode],
    adj: Dict[str, List[str]],
    db: Session,
    run_id: int,
):
    """
    Create the async function that LangGraph will execute for this node.
    It checks conditions, makes the HTTP call, updates state and DB.
    """

    async def node_fn(state: GraphState) -> dict:
        node_results = state.get("node_results", {})
        failed_nodes = state.get("failed_nodes", [])
        skipped_nodes = state.get("skipped_nodes", [])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if this node was marked for skipping by an upstream halt_branch
        if node.id in skipped_nodes:
            _update_step_status(db, run_id, node.id, "skipped", now, now)
            return {
                "node_results": {
                    node.id: {"status": "skipped", "response_data": None, "error": "Skipped due to upstream failure", "http_status_code": None}
                },
                "failed_nodes": [],
                "skipped_nodes": [],
            }

        # Evaluate condition
        should_execute = evaluate_condition(node.condition, node.dependencies, node_results)
        if not should_execute:
            _update_step_status(db, run_id, node.id, "condition_not_met", now, now)
            return {
                "node_results": {
                    node.id: {"status": "condition_not_met", "response_data": None, "error": None, "http_status_code": None}
                },
                "failed_nodes": [],
                "skipped_nodes": [],
            }

        # Mark as running
        _update_step_status(db, run_id, node.id, "running", now, None)

        # If capability not found in DB, fail the node
        if cap_info is None:
            error_msg = f"Device '{node.device}' or capability '{node.capability}' not found in registry"
            completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _update_step_status(db, run_id, node.id, "failed", now, completed, error_msg=error_msg)

            new_skipped = []
            if node.on_failure == "halt_branch":
                new_skipped = list(_get_all_dependents(node.id, adj))
            elif node.on_failure == "skip_dependents":
                new_skipped = adj.get(node.id, [])

            return {
                "node_results": {
                    node.id: {"status": "failed", "response_data": None, "error": error_msg, "http_status_code": None}
                },
                "failed_nodes": [node.id],
                "skipped_nodes": new_skipped,
            }

        # SSE capability — read latest sensor reading from DB instead of making HTTP call
        url = cap_info["url"]
        method = cap_info["method"]
        if method == "SSE":
            reading = db.query(models.SensorReading).filter(
                models.SensorReading.device_id == cap_info["device_id"],
                models.SensorReading.capability_name == cap_info["cap_name"],
            ).order_by(models.SensorReading.id.desc()).first()

            completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if reading:
                _update_step_status(db, run_id, node.id, "success", now, completed,
                                    response_data=reading.data, http_status_code=200)
                return {
                    "node_results": {
                        node.id: {"status": "success", "response_data": reading.data, "error": None, "http_status_code": 200}
                    },
                    "failed_nodes": [],
                    "skipped_nodes": [],
                }
            else:
                error_msg = f"No sensor reading available yet for {node.device}/{node.capability}"
                _update_step_status(db, run_id, node.id, "failed", now, completed, error_msg=error_msg)
                new_skipped = []
                if node.on_failure == "halt_branch":
                    new_skipped = list(_get_all_dependents(node.id, adj))
                elif node.on_failure == "skip_dependents":
                    new_skipped = adj.get(node.id, [])
                return {
                    "node_results": {
                        node.id: {"status": "failed", "response_data": None, "error": error_msg, "http_status_code": None}
                    },
                    "failed_nodes": [node.id],
                    "skipped_nodes": new_skipped,
                }

        # VLM capability - capture or load a camera image, then analyze it with a vision model.
        # The normalized result is ordinary JSON, so downstream on_value conditions can use it.
        if method == "VLM":
            try:
                response_data = await vision.analyze_camera_image(url, node.args)
                completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _update_step_status(
                    db, run_id, node.id, "success", now, completed,
                    response_data=response_data, http_status_code=200
                )
                return {
                    "node_results": {
                        node.id: {"status": "success", "response_data": response_data, "error": None, "http_status_code": 200}
                    },
                    "failed_nodes": [],
                    "skipped_nodes": [],
                }
            except Exception as e:
                completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                error_msg = f"VLM analysis failed: {str(e)[:200]}"
                _update_step_status(db, run_id, node.id, "failed", now, completed, error_msg=error_msg)

                new_skipped = []
                if node.on_failure == "halt_branch":
                    new_skipped = list(_get_all_dependents(node.id, adj))
                elif node.on_failure == "skip_dependents":
                    new_skipped = adj.get(node.id, [])

                return {
                    "node_results": {
                        node.id: {"status": "failed", "response_data": None, "error": error_msg, "http_status_code": None}
                    },
                    "failed_nodes": [node.id],
                    "skipped_nodes": new_skipped,
                }

        # Make the HTTP call
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method in ("POST", "PUT", "PATCH"):
                    resp = await client.request(method, url, json=node.args)
                else:
                    resp = await client.request(method, url, params=node.args if node.args else None)

                completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if resp.status_code < 400:
                    # Success
                    try:
                        response_data = resp.json()
                    except Exception:
                        response_data = {"raw": resp.text}

                    _update_step_status(
                        db, run_id, node.id, "success", now, completed,
                        response_data=response_data, http_status_code=resp.status_code
                    )
                    return {
                        "node_results": {
                            node.id: {"status": "success", "response_data": response_data, "error": None, "http_status_code": resp.status_code}
                        },
                        "failed_nodes": [],
                        "skipped_nodes": [],
                    }
                else:
                    # HTTP error
                    error_msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    _update_step_status(
                        db, run_id, node.id, "failed", now, completed,
                        error_msg=error_msg, http_status_code=resp.status_code
                    )

                    new_skipped = []
                    if node.on_failure == "halt_branch":
                        new_skipped = list(_get_all_dependents(node.id, adj))
                    elif node.on_failure == "skip_dependents":
                        new_skipped = adj.get(node.id, [])
                    # "ignore" → treat as success for dependency evaluation
                    status_for_deps = "failed"
                    if node.on_failure == "ignore":
                        status_for_deps = "success"

                    return {
                        "node_results": {
                            node.id: {"status": status_for_deps, "response_data": None, "error": error_msg, "http_status_code": resp.status_code}
                        },
                        "failed_nodes": [node.id],
                        "skipped_nodes": new_skipped,
                    }

        except httpx.TimeoutException:
            completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_msg = f"Timeout after 30s calling {method} {url}"
            _update_step_status(db, run_id, node.id, "failed", now, completed, error_msg=error_msg)

            new_skipped = []
            if node.on_failure == "halt_branch":
                new_skipped = list(_get_all_dependents(node.id, adj))
            elif node.on_failure == "skip_dependents":
                new_skipped = adj.get(node.id, [])

            return {
                "node_results": {
                    node.id: {"status": "failed", "response_data": None, "error": error_msg, "http_status_code": None}
                },
                "failed_nodes": [node.id],
                "skipped_nodes": new_skipped,
            }

        except Exception as e:
            completed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_msg = f"Exception: {str(e)[:200]}"
            _update_step_status(db, run_id, node.id, "failed", now, completed, error_msg=error_msg)

            new_skipped = []
            if node.on_failure == "halt_branch":
                new_skipped = list(_get_all_dependents(node.id, adj))
            elif node.on_failure == "skip_dependents":
                new_skipped = adj.get(node.id, [])

            return {
                "node_results": {
                    node.id: {"status": "failed", "response_data": None, "error": error_msg, "http_status_code": None}
                },
                "failed_nodes": [node.id],
                "skipped_nodes": new_skipped,
            }

    return node_fn


# ──────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────

def _update_step_status(
    db: Session,
    run_id: int,
    node_id: str,
    status: str,
    started_at: str,
    completed_at: Optional[str],
    response_data: Optional[Dict] = None,
    error_msg: Optional[str] = None,
    http_status_code: Optional[int] = None,
):
    """Update an ExecutionStep record in the database."""
    step = db.query(models.ExecutionStep).filter(
        models.ExecutionStep.run_id == run_id,
        models.ExecutionStep.node_id == node_id,
    ).first()
    if step:
        step.status = status
        step.started_at = started_at
        step.completed_at = completed_at
        step.response_data = response_data
        step.error_message = error_msg
        step.http_status_code = http_status_code
        db.commit()


# ──────────────────────────────────────────────────────────────────
# Graph builder
# ──────────────────────────────────────────────────────────────────

def build_execution_graph(
    dag: schemas.ExecutionDAG,
    db: Session,
    run_id: int,
) -> Any:
    """
    Dynamically construct a LangGraph StateGraph from the DAG structure.
    Returns a compiled graph ready to invoke.
    """
    nodes_by_id: Dict[str, schemas.ExecutionNode] = {n.id: n for n in dag.nodes}

    # Build adjacency list (parent -> children)
    adj: Dict[str, List[str]] = defaultdict(list)
    for node in dag.nodes:
        for dep_id in node.dependencies:
            if dep_id in nodes_by_id:
                adj[dep_id].append(node.id)

    # Resolve capability URLs from DB
    cap_map = resolve_capabilities(dag, db)

    # Build the StateGraph
    graph = StateGraph(GraphState)

    # Add all nodes
    for node in dag.nodes:
        fn = make_node_fn(
            node=node,
            cap_info=cap_map.get(node.id),
            all_nodes=nodes_by_id,
            adj=dict(adj),
            db=db,
            run_id=run_id,
        )
        graph.add_node(node.id, fn)

    # Add edges
    # Root nodes: connect START → node
    root_nodes = [n for n in dag.nodes if not n.dependencies]
    for root in root_nodes:
        graph.add_edge(START, root.id)

    # Dependency edges: dep → node
    # We need to handle fan-in: if a node has multiple deps, each dep gets an edge to it.
    # LangGraph will wait for all incoming edges before executing the node.
    for node in dag.nodes:
        for dep_id in node.dependencies:
            if dep_id in nodes_by_id:
                graph.add_edge(dep_id, node.id)

    # Terminal nodes: connect node → END
    # A terminal node is one that has no children (no one depends on it)
    nodes_with_children = set()
    for node in dag.nodes:
        for dep_id in node.dependencies:
            nodes_with_children.add(dep_id)

    terminal_nodes = [n for n in dag.nodes if n.id not in nodes_with_children]
    for term in terminal_nodes:
        graph.add_edge(term.id, END)

    # Handle edge case: empty DAG
    if not dag.nodes:
        graph.add_edge(START, END)

    return graph.compile()


# ──────────────────────────────────────────────────────────────────
# Main execution functions
# ──────────────────────────────────────────────────────────────────

async def execute_policy(
    policy_id: int,
    db: Session,
    triggered_by: str = "manual",
) -> models.ExecutionRun:
    """
    Execute a policy's DAG. Creates an ExecutionRun, builds the LangGraph,
    invokes it, and returns the completed run.
    """
    # Load policy
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise ValueError(f"Policy {policy_id} not found")

    # Convert execution_plan to DAG (handles both old and new format)
    dag = dag_utils.ensure_dag(policy.execution_plan)

    if not dag.nodes:
        raise ValueError(f"Policy {policy_id} has an empty execution plan")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create ExecutionRun
    run = models.ExecutionRun(
        policy_id=policy_id,
        status="running",
        triggered_by=triggered_by,
        started_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Create ExecutionStep records for each node (initial status: pending)
    for node in dag.nodes:
        step = models.ExecutionStep(
            run_id=run.id,
            node_id=node.id,
            device_name=node.device,
            capability_name=node.capability,
            args=node.args,
            status="pending",
        )
        db.add(step)
    db.commit()

    # Build and invoke the LangGraph
    try:
        compiled_graph = build_execution_graph(dag, db, run.id)

        initial_state: GraphState = {
            "node_results": {},
            "failed_nodes": [],
            "skipped_nodes": [],
        }

        # Run the graph
        final_state = await compiled_graph.ainvoke(initial_state)

        # Tally results
        node_results = final_state.get("node_results", {})
        total = len(dag.nodes)
        success = sum(1 for r in node_results.values() if r.get("status") == "success")
        failed = sum(1 for r in node_results.values() if r.get("status") == "failed")
        skipped = sum(1 for r in node_results.values() if r.get("status") == "skipped")
        condition_not_met = sum(1 for r in node_results.values() if r.get("status") == "condition_not_met")

        # Determine overall run status
        if failed == 0 and skipped == 0:
            run_status = "completed"
        elif success == 0 and failed > 0:
            run_status = "failed"
        else:
            run_status = "partial_failure"

        run.status = run_status
        run.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run.summary = {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "condition_not_met": condition_not_met,
        }
        db.commit()
        db.refresh(run)

    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run.summary = {"error": str(e)[:500]}
        db.commit()
        db.refresh(run)

    return run


async def execute_policy_streaming(
    policy_id: int,
    db: Session,
    triggered_by: str = "manual",
):
    """
    Generator that yields step-by-step execution events for SSE streaming.
    Each yielded item is a dict: {node_id, status, response_data, error}
    """
    # Load policy
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        yield {"type": "error", "message": f"Policy {policy_id} not found"}
        return

    dag = dag_utils.ensure_dag(policy.execution_plan)
    if not dag.nodes:
        yield {"type": "error", "message": f"Policy {policy_id} has an empty execution plan"}
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create ExecutionRun
    run = models.ExecutionRun(
        policy_id=policy_id,
        status="running",
        triggered_by=triggered_by,
        started_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Create ExecutionStep records
    for node in dag.nodes:
        step = models.ExecutionStep(
            run_id=run.id,
            node_id=node.id,
            device_name=node.device,
            capability_name=node.capability,
            args=node.args,
            status="pending",
        )
        db.add(step)
    db.commit()

    yield {"type": "run_started", "run_id": run.id, "total_nodes": len(dag.nodes)}

    try:
        compiled_graph = build_execution_graph(dag, db, run.id)

        initial_state: GraphState = {
            "node_results": {},
            "failed_nodes": [],
            "skipped_nodes": [],
        }

        # Stream events from the graph
        async for event in compiled_graph.astream_events(initial_state, version="v2"):
            kind = event.get("event", "")

            # When a node finishes, emit its result
            if kind == "on_chain_end" and event.get("name") in {n.id for n in dag.nodes}:
                node_id = event["name"]
                output = event.get("data", {}).get("output", {})
                node_result = output.get("node_results", {}).get(node_id, {})

                yield {
                    "type": "node_completed",
                    "node_id": node_id,
                    "status": node_result.get("status", "unknown"),
                    "response_data": node_result.get("response_data"),
                    "error": node_result.get("error"),
                    "http_status_code": node_result.get("http_status_code"),
                }

        # Finalize the run
        db.refresh(run)
        node_results = {}
        for step in run.steps:
            node_results[step.node_id] = step.status

        total = len(dag.nodes)
        success = sum(1 for s in node_results.values() if s == "success")
        failed = sum(1 for s in node_results.values() if s == "failed")
        skipped = sum(1 for s in node_results.values() if s == "skipped")
        condition_not_met = sum(1 for s in node_results.values() if s == "condition_not_met")

        if failed == 0 and skipped == 0:
            run_status = "completed"
        elif success == 0 and failed > 0:
            run_status = "failed"
        else:
            run_status = "partial_failure"

        run.status = run_status
        run.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run.summary = {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "condition_not_met": condition_not_met,
        }
        db.commit()

        yield {"type": "run_completed", "run_id": run.id, "status": run_status, "summary": run.summary}

    except Exception as e:
        run.status = "failed"
        run.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run.summary = {"error": str(e)[:500]}
        db.commit()

        yield {"type": "run_failed", "run_id": run.id, "error": str(e)[:500]}
