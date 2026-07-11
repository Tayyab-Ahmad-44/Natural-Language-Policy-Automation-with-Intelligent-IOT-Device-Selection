from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
import json
import os
import tempfile
import asyncio
import httpx
import models, schemas, database, llm, dag_utils, executor, vision, conflicts
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from load_dotenv import load_dotenv

load_dotenv()

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)


def _migrate_db():
    """Add new columns to existing tables without dropping them."""
    with database.engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE policies
                ADD COLUMN IF NOT EXISTS repeat_interval_seconds INTEGER,
                ADD COLUMN IF NOT EXISTS last_executed_at VARCHAR,
                ADD COLUMN IF NOT EXISTS requires_confirmation BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS confirmed BOOLEAN DEFAULT FALSE
        """))
        conn.execute(text("""
            ALTER TABLE capabilities
                ADD COLUMN IF NOT EXISTS sensitive BOOLEAN DEFAULT FALSE
        """))
        conn.commit()

_migrate_db()


def _policy_has_sse_nodes(policy: models.Policy, db: Session) -> bool:
    """Returns True if any node in the policy's DAG maps to an SSE-method capability."""
    plan = policy.execution_plan
    if not plan or not isinstance(plan, dict):
        return False
    nodes = plan.get("nodes", [])
    if not nodes:
        return False

    # Build a (device_name, cap_name) → method lookup from the DB
    cap_method: dict = {}
    for device in db.query(models.Device).all():
        for cap in device.capabilities:
            cap_method[(device.name.lower(), cap.name.lower())] = cap.method.upper()

    return any(
        cap_method.get((n.get("device", "").lower(), n.get("capability", "").lower())) == "SSE"
        for n in nodes
    )


def _policy_has_sensitive_nodes(execution_plan, db: Session) -> bool:
    """Returns True if any node in the DAG maps to a capability flagged sensitive
    (destructive/security-relevant) in the device catalog."""
    plan = execution_plan
    if not plan or not isinstance(plan, dict):
        return False
    nodes = plan.get("nodes", [])
    if not nodes:
        return False

    cap_sensitive: dict = {}
    for device in db.query(models.Device).all():
        for cap in device.capabilities:
            cap_sensitive[(device.name.lower(), cap.name.lower())] = bool(cap.sensitive)

    return any(
        cap_sensitive.get((n.get("device", "").lower(), n.get("capability", "").lower()), False)
        for n in nodes
    )


async def _run_scheduler_tick(db: Session) -> tuple:
    """
    Core scheduler logic. For each active policy whose time window is current:
    - If repeat_interval_seconds is set: re-run every N seconds.
    - If the policy has only SSE nodes (no explicit interval): skip — driven by sensor events.
    - Otherwise: run once per window entry (resets each day at start_time).
    Skips policies that already have a run in 'running' state.
    """
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    triggered = []

    active_policies = db.query(models.Policy).filter(models.Policy.is_active == True).all()

    for policy in active_policies:
        if not (policy.start_time <= current_time_str <= policy.end_time):
            continue

        # Skip if an execution is already in progress
        running = db.query(models.ExecutionRun).filter(
            models.ExecutionRun.policy_id == policy.id,
            models.ExecutionRun.status == "running",
        ).first()
        if running:
            continue

        # SSE-driven policies without an explicit repeat interval are triggered by sensor
        # events via _trigger_sse_policies, not by the scheduler.
        if policy.repeat_interval_seconds is None and _policy_has_sse_nodes(policy, db):
            continue

        if not _should_execute(policy, now):
            continue

        try:
            run = await executor.execute_policy(policy.id, db, triggered_by="scheduler")
            db.query(models.Policy).filter(models.Policy.id == policy.id).update(
                {"last_executed_at": now.isoformat()}
            )
            db.commit()
            triggered.append({
                "policy_name": policy.name,
                "run_id": run.id,
                "status": run.status,
                "summary": run.summary,
            })
        except Exception as e:
            db.rollback()
            triggered.append({"policy_name": policy.name, "error": str(e)})

    return triggered, current_time_str


def _should_execute(policy: models.Policy, now: datetime) -> bool:
    if policy.last_executed_at is None:
        return True

    last_run = datetime.fromisoformat(policy.last_executed_at)

    if policy.repeat_interval_seconds is None:
        # Once per window entry — gate resets each day at start_time
        today_window_start = datetime.strptime(
            now.strftime("%Y-%m-%d") + " " + policy.start_time, "%Y-%m-%d %H:%M"
        )
        return last_run < today_window_start

    return (now - last_run).total_seconds() >= policy.repeat_interval_seconds


async def _scheduler_loop():
    """Background loop: ticks the scheduler every 15 seconds."""
    while True:
        db = database.SessionLocal()
        try:
            await _run_scheduler_tick(db)
        except Exception as e:
            print(f"[scheduler] tick error: {e}")
        finally:
            db.close()
        await asyncio.sleep(15)


# ─── SSE Sensor Subscriber ────────────────────────────────────────

_sse_tasks: Dict[int, asyncio.Task] = {}


async def _trigger_sse_policies(cap_id: int, db: Session):
    """
    Called on every SSE event. Finds active policies that reference this capability
    and whose time window is currently active, then executes them immediately.
    """
    cap = db.query(models.Capability).filter(models.Capability.id == cap_id).first()
    if not cap:
        return
    device = db.query(models.Device).filter(models.Device.id == cap.device_id).first()
    if not device:
        return

    device_name = device.name.lower()
    cap_name = cap.name.lower()

    now = datetime.now()
    current_time_str = now.strftime("%H:%M")

    active_policies = db.query(models.Policy).filter(models.Policy.is_active == True).all()

    for policy in active_policies:
        if not (policy.start_time <= current_time_str <= policy.end_time):
            continue

        plan = policy.execution_plan
        if not plan or not isinstance(plan, dict):
            continue
        nodes = plan.get("nodes", [])
        if not any(
            n.get("device", "").lower() == device_name and n.get("capability", "").lower() == cap_name
            for n in nodes
        ):
            continue

        # Skip if already running
        running = db.query(models.ExecutionRun).filter(
            models.ExecutionRun.policy_id == policy.id,
            models.ExecutionRun.status == "running",
        ).first()
        if running:
            continue

        try:
            run = await executor.execute_policy(policy.id, db, triggered_by="sse_event")
            db.query(models.Policy).filter(models.Policy.id == policy.id).update(
                {"last_executed_at": now.isoformat()}
            )
            db.commit()
            print(f"[SSE trigger] policy '{policy.name}' run #{run.id} → {run.status}")
        except Exception as e:
            db.rollback()
            print(f"[SSE trigger] policy '{policy.name}' error: {e}")


async def _subscribe_to_sse(cap_id: int, url: str):
    """Long-running task: subscribes to one SSE endpoint, stores each event, and triggers policies."""
    while True:
        try:
            timeout = httpx.Timeout(connect=10.0, read=None, write=None, pool=None)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        # Store the reading
                        db = database.SessionLocal()
                        try:
                            cap = db.query(models.Capability).filter(
                                models.Capability.id == cap_id
                            ).first()
                            if cap:
                                reading = models.SensorReading(
                                    device_id=cap.device_id,
                                    capability_name=cap.name,
                                    data=data,
                                    received_at=datetime.now().isoformat(),
                                )
                                db.add(reading)
                                db.commit()
                        finally:
                            db.close()
                        # Trigger any policies waiting on this sensor
                        trigger_db = database.SessionLocal()
                        try:
                            await _trigger_sse_policies(cap_id, trigger_db)
                        finally:
                            trigger_db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[SSE:{cap_id}] {e} — reconnecting in 5s")
            await asyncio.sleep(5)


def _sse_cap_ids_needed(db: Session) -> set:
    """
    Returns the set of Capability IDs (method=SSE) that are actually
    referenced in at least one active policy's execution plan.
    Only these should have live SSE connections open.
    """
    active_policies = db.query(models.Policy).filter(models.Policy.is_active == True).all()

    # Collect (device_name, cap_name) pairs used across all active policy DAGs
    needed_pairs: set = set()
    for policy in active_policies:
        plan = policy.execution_plan
        if not plan or not isinstance(plan, dict):
            continue
        for node in plan.get("nodes", []):
            device = node.get("device", "").lower()
            cap = node.get("capability", "").lower()
            if device and cap:
                needed_pairs.add((device, cap))

    if not needed_pairs:
        return set()

    # Resolve those pairs to Capability IDs that have method=SSE
    sse_caps = db.query(models.Capability).filter(models.Capability.method == "SSE").all()
    needed_ids = set()
    for cap in sse_caps:
        device_row = db.query(models.Device).filter(models.Device.id == cap.device_id).first()
        if device_row:
            key = (device_row.name.lower(), cap.name.lower())
            if key in needed_pairs:
                needed_ids.add(cap.id)

    return needed_ids


async def _sse_manager_loop():
    """
    Syncs SSE subscriptions every 30s.
    Only connects to SSE capabilities that are referenced in active policies —
    never auto-connects just because a capability exists in the DB.
    """
    while True:
        db = database.SessionLocal()
        try:
            needed_ids = _sse_cap_ids_needed(db)

            # Start tasks for newly needed capabilities
            for cap_id in needed_ids:
                if cap_id not in _sse_tasks or _sse_tasks[cap_id].done():
                    cap = db.query(models.Capability).filter(models.Capability.id == cap_id).first()
                    if cap:
                        _sse_tasks[cap_id] = asyncio.create_task(
                            _subscribe_to_sse(cap_id, cap.url)
                        )
                        print(f"[SSE manager] subscribed to cap {cap_id} ({cap.url})")

            # Cancel tasks for capabilities no longer needed
            for cap_id in list(_sse_tasks.keys()):
                if cap_id not in needed_ids:
                    _sse_tasks[cap_id].cancel()
                    del _sse_tasks[cap_id]
                    print(f"[SSE manager] unsubscribed from cap {cap_id}")
        finally:
            db.close()
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    sched_task = asyncio.create_task(_scheduler_loop())
    sse_mgr_task = asyncio.create_task(_sse_manager_loop())
    yield
    sched_task.cancel()
    sse_mgr_task.cancel()
    for task in list(_sse_tasks.values()):
        task.cancel()
    for t in [sched_task, sse_mgr_task]:
        try:
            await t
        except asyncio.CancelledError:
            pass


application = FastAPI(lifespan=lifespan)

application.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Helper: serialize devices for LLM ────────────────────────────

def _serialize_devices(db: Session) -> list:
    """Serialize all devices with capabilities for LLM prompts."""
    devices = db.query(models.Device).all()
    devices_data = []
    for d in devices:
        caps = []
        for c in d.capabilities:
            caps.append({
                "name": c.name,
                "url": c.url,
                "method": c.method,
                "input_schema": c.input_schema,
                "sensitive": bool(c.sensitive),
            })
        devices_data.append({
            "name": d.name,
            "type": d.type,
            "capabilities": caps,
        })
    return devices_data


# ═══════════════════════════════════════════════════════════════════
# DEVICE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/devices/", response_model=schemas.Device)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    db_device = models.Device(name=device.name, type=device.type)
    db.add(db_device)
    db.commit()
    db.refresh(db_device)

    for cap in device.capabilities:
        db_cap = models.Capability(
            name=cap.name,
            url=cap.url,
            method=cap.method,
            input_schema=cap.input_schema,
            device_id=db_device.id,
        )
        db.add(db_cap)

    db.commit()
    db.refresh(db_device)
    return db_device

@application.get("/api/devices/", response_model=List[schemas.Device])
def read_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    devices = db.query(models.Device).offset(skip).limit(limit).all()
    return devices

@application.put("/api/devices/{device_id}", response_model=schemas.Device)
def update_device(device_id: int, device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    db_device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not db_device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db_device.name = device.name
    db_device.type = device.type
    
    # Clear existing capabilities and add the updated ones
    db.query(models.Capability).filter(models.Capability.device_id == device_id).delete()
    
    for cap in device.capabilities:
        db_cap = models.Capability(
            name=cap.name,
            url=cap.url,
            method=cap.method,
            input_schema=cap.input_schema,
            device_id=db_device.id,
        )
        db.add(db_cap)

    db.commit()
    db.refresh(db_device)
    return db_device

@application.delete("/api/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()
    return {"detail": "Device deleted"}


@application.post("/api/devices/discover", response_model=schemas.DeviceDiscoverResponse)
async def discover_devices(req: schemas.DeviceDiscoverRequest):
    """Fetch a device catalog from an external endpoint via GET and use the LLM
    to map the (arbitrary) response into our Device/Capability schema.

    This only returns a PREVIEW — nothing is persisted until the client confirms
    via POST /api/devices/bulk.
    """
    endpoint = (req.endpoint or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="An endpoint URL is required.")

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(endpoint, headers=req.headers or {})
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach endpoint: {e}")

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Endpoint returned HTTP {resp.status_code}: {resp.text[:300]}",
        )

    raw_text = resp.text
    devices = llm.map_devices_from_response(raw_text, endpoint)

    warning = None
    if not devices:
        warning = "The LLM could not derive any devices from this endpoint's response."

    return schemas.DeviceDiscoverResponse(
        devices=devices,
        raw_sample=raw_text[:2000],
        warning=warning,
    )


@application.post("/api/devices/bulk", response_model=schemas.DeviceBulkCreateResponse)
def bulk_create_devices(payload: schemas.DeviceBulkCreate, db: Session = Depends(get_db)):
    """Create many devices at once (used by auto-discovery import).
    Devices whose name already exists are skipped rather than erroring."""
    created = []
    skipped = []
    for device in payload.devices:
        existing = db.query(models.Device).filter(models.Device.name == device.name).first()
        if existing:
            skipped.append(device.name)
            continue

        db_device = models.Device(name=device.name, type=device.type)
        db.add(db_device)
        db.commit()
        db.refresh(db_device)

        for cap in device.capabilities:
            db.add(models.Capability(
                name=cap.name,
                url=cap.url,
                method=cap.method,
                input_schema=cap.input_schema,
                device_id=db_device.id,
            ))
        db.commit()
        db.refresh(db_device)
        created.append(db_device)

    return {"created": created, "skipped": skipped}


@application.post("/api/devices/bulk-delete")
def bulk_delete_devices(payload: schemas.DeviceBulkDeleteRequest, db: Session = Depends(get_db)):
    """Delete many devices at once by id. Unknown ids are ignored."""
    if not payload.ids:
        return {"deleted": []}
    devices = db.query(models.Device).filter(models.Device.id.in_(payload.ids)).all()
    deleted = [d.id for d in devices]
    for d in devices:
        db.delete(d)
    db.commit()
    return {"deleted": deleted}


# ═══════════════════════════════════════════════════════════════════
# POLICY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/policies/preview", response_model=schemas.PolicyPreviewResponse)
def preview_policy(policy: schemas.PolicyCreate, db: Session = Depends(get_db)):
    """
    Parse natural language policy via LLM and return the execution DAG
    for visualization — without saving.
    """
    devices_data = _serialize_devices(db)

    try:
        parsed = llm.parse_policy_with_llm(policy.original_text, devices_data)

        # Validate the DAG
        validation = dag_utils.validate_dag(parsed.execution_dag)
        levels = dag_utils.topological_levels(parsed.execution_dag)

        # Check for conflicts against already-stored policies.
        conflict_list = conflicts.check_against_existing(
            policy.name, policy.original_text,
            parsed.execution_dag, parsed.time_window, db,
        )

        requires_confirmation = _policy_has_sensitive_nodes(
            dag_utils.dag_to_dict(parsed.execution_dag), db
        )

        return schemas.PolicyPreviewResponse(
            execution_dag=parsed.execution_dag,
            time_window=parsed.time_window,
            validation=validation,
            levels=levels,
            conflicts=conflict_list,
            requires_confirmation=requires_confirmation,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@application.post("/api/policies/", response_model=schemas.Policy)
def create_policy(policy: schemas.PolicyCreate, db: Session = Depends(get_db)):
    """Parse natural language policy via LLM and save with DAG execution plan."""
    devices_data = _serialize_devices(db)
    parsed = llm.parse_policy_with_llm(policy.original_text, devices_data)

    # Conflict resolution: "replace old with new" deletes the chosen existing
    # policies before saving this one.
    for pid in policy.replace_policy_ids or []:
        existing = db.query(models.Policy).filter(models.Policy.id == pid).first()
        if existing:
            db.delete(existing)
    if policy.replace_policy_ids:
        db.commit()

    execution_plan = dag_utils.dag_to_dict(parsed.execution_dag)
    db_policy = models.Policy(
        name=policy.name,
        original_text=policy.original_text,
        start_time=parsed.time_window["from_time"],
        end_time=parsed.time_window["to_time"],
        execution_plan=execution_plan,
        repeat_interval_seconds=policy.repeat_interval_seconds,
        requires_confirmation=_policy_has_sensitive_nodes(execution_plan, db),
    )

    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy

@application.get("/api/policies/", response_model=List[schemas.Policy])
def read_policies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    policies = db.query(models.Policy).offset(skip).limit(limit).all()
    return policies

@application.delete("/api/policies/{policy_id}")
def delete_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return {"detail": "Policy deleted"}

@application.post("/api/policies/{policy_id}/confirm", response_model=schemas.Policy)
def confirm_policy(policy_id: int, db: Session = Depends(get_db)):
    """
    Arm a policy that contains sensitive (destructive/security-relevant) actions.
    Required once before the policy can execute via scheduler, SSE trigger, or
    manual run -- after this it fires unattended like any other policy.
    """
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.confirmed = True
    db.commit()
    db.refresh(policy)
    return policy


# ═══════════════════════════════════════════════════════════════════
# TASK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/tasks/", response_model=schemas.TaskCreateResponse)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    db_task = models.Task(
        name=task.name,
        description=task.description,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    devices_data = _serialize_devices(db)
    policy_rules = llm.break_down_task(task.description, devices_data)

    # Build the policy models WITHOUT committing yet, so conflict detection can
    # run against the pre-existing policies (and the task's own siblings).
    new_policies: List[models.Policy] = []
    for rule in policy_rules:
        try:
            if isinstance(rule, dict) and rule.get("execution_dag") is not None:
                original_text = rule.get("original_text") or f"{task.name} - Policy"
                time_window = rule.get("time_window", {"from_time": "00:00", "to_time": "23:59"})
                execution_plan = rule.get("execution_dag", {"nodes": []})
            elif isinstance(rule, dict) and rule.get("execution_plan") is not None:
                original_text = rule.get("original_text") or f"{task.name} - Policy"
                time_window = rule.get("time_window", {"from_time": "00:00", "to_time": "23:59"})
                dag = dag_utils.migrate_flat_to_dag(rule.get("execution_plan", []))
                execution_plan = dag_utils.dag_to_dict(dag)
            else:
                # Fallback: rule is a string -> parse via LLM
                parsed = llm.parse_policy_with_llm(rule, devices_data)
                original_text = rule if isinstance(rule, str) else f"{task.name} - Rule"
                time_window = parsed.time_window
                execution_plan = dag_utils.dag_to_dict(parsed.execution_dag)

            new_policies.append(models.Policy(
                name=f"{task.name} - {original_text}",
                original_text=original_text,
                start_time=time_window.get("from_time", "00:00"),
                end_time=time_window.get("to_time", "23:59"),
                execution_plan=execution_plan,
                task_id=db_task.id,
                requires_confirmation=_policy_has_sensitive_nodes(execution_plan, db),
            ))
        except Exception as e:
            print(f"Failed to create policy for rule '{rule}': {e}")

    # Conflict detection: each new policy vs already-stored policies plus the
    # task's earlier siblings (so each intra-task pair is reported once).
    existing_cands = conflicts.candidates_from_db(db)
    sibling_descriptors: List[dict] = []
    all_conflicts: List[dict] = []
    for p in new_policies:
        descriptor = {
            "name": p.name,
            "text": p.original_text,
            "window": {"from_time": p.start_time, "to_time": p.end_time},
            "actions": conflicts.extract_actions(p.execution_plan),
        }
        found = conflicts.detect_conflicts(descriptor, existing_cands + sibling_descriptors)
        for c in found:
            c["new_policy_name"] = p.name
        all_conflicts.extend(found)
        sibling_descriptors.append(descriptor)

    for p in new_policies:
        db.add(p)
    db.commit()
    db.refresh(db_task)

    return {"task": db_task, "conflicts": all_conflicts}

@application.get("/api/tasks/", response_model=List[schemas.Task])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tasks = db.query(models.Task).offset(skip).limit(limit).all()
    return tasks

@application.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"detail": "Task deleted"}


# ═══════════════════════════════════════════════════════════════════
# EXECUTION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/policies/{policy_id}/execute", response_model=schemas.ExecutionRunDetail)
async def execute_policy_endpoint(policy_id: int, db: Session = Depends(get_db)):
    """Manually trigger execution of a policy's DAG. Returns the completed run."""
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    try:
        run = await executor.execute_policy(policy_id, db, triggered_by="manual")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Build the response
    dag = dag_utils.ensure_dag(policy.execution_plan)
    steps = [
        schemas.ExecutionStepResponse(
            id=s.id,
            run_id=s.run_id,
            node_id=s.node_id,
            device_name=s.device_name,
            capability_name=s.capability_name,
            args=s.args or {},
            status=s.status,
            started_at=s.started_at,
            completed_at=s.completed_at,
            response_data=s.response_data,
            error_message=s.error_message,
            http_status_code=s.http_status_code,
        )
        for s in run.steps
    ]

    return schemas.ExecutionRunDetail(
        id=run.id,
        policy_id=run.policy_id,
        policy_name=policy.name,
        status=run.status,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary,
        steps=steps,
        execution_dag=dag,
    )


@application.get("/api/executions/", response_model=List[schemas.ExecutionRunResponse])
def list_executions(
    policy_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all execution runs, optionally filtered by policy_id."""
    query = db.query(models.ExecutionRun)
    if policy_id is not None:
        query = query.filter(models.ExecutionRun.policy_id == policy_id)
    runs = query.order_by(models.ExecutionRun.id.desc()).offset(skip).limit(limit).all()

    result = []
    for run in runs:
        policy = db.query(models.Policy).filter(models.Policy.id == run.policy_id).first()
        result.append(schemas.ExecutionRunResponse(
            id=run.id,
            policy_id=run.policy_id,
            policy_name=policy.name if policy else "Unknown",
            status=run.status,
            triggered_by=run.triggered_by,
            started_at=run.started_at,
            completed_at=run.completed_at,
            summary=run.summary,
        ))
    return result


@application.get("/api/executions/{run_id}", response_model=schemas.ExecutionRunDetail)
def get_execution_detail(run_id: int, db: Session = Depends(get_db)):
    """Get a specific execution run with all its steps and the source DAG."""
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")

    policy = db.query(models.Policy).filter(models.Policy.id == run.policy_id).first()
    dag = dag_utils.ensure_dag(policy.execution_plan) if policy else schemas.ExecutionDAG(nodes=[])

    steps = [
        schemas.ExecutionStepResponse(
            id=s.id,
            run_id=s.run_id,
            node_id=s.node_id,
            device_name=s.device_name,
            capability_name=s.capability_name,
            args=s.args or {},
            status=s.status,
            started_at=s.started_at,
            completed_at=s.completed_at,
            response_data=s.response_data,
            error_message=s.error_message,
            http_status_code=s.http_status_code,
        )
        for s in run.steps
    ]

    return schemas.ExecutionRunDetail(
        id=run.id,
        policy_id=run.policy_id,
        policy_name=policy.name if policy else "Unknown",
        status=run.status,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
        summary=run.summary,
        steps=steps,
        execution_dag=dag,
    )


@application.get("/api/executions/{run_id}/stream")
async def stream_execution(run_id: int, db: Session = Depends(get_db)):
    """
    SSE endpoint that streams execution events in real-time.
    Note: This endpoint re-executes the policy associated with the run.
    For live streaming of a new execution, use POST /api/policies/{id}/execute/stream instead.
    """
    run = db.query(models.ExecutionRun).filter(models.ExecutionRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Execution run not found")

    # Return the existing steps as SSE events (replay mode)
    async def event_generator():
        for step in run.steps:
            event_data = json.dumps({
                "type": "node_completed",
                "node_id": step.node_id,
                "status": step.status,
                "response_data": step.response_data,
                "error": step.error_message,
                "http_status_code": step.http_status_code,
            })
            yield f"data: {event_data}\n\n"
        yield f"data: {json.dumps({'type': 'stream_end', 'run_id': run.id})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@application.post("/api/policies/{policy_id}/execute/stream")
async def execute_policy_stream(policy_id: int, db: Session = Depends(get_db)):
    """
    SSE endpoint: execute a policy and stream step-by-step events in real-time.
    """
    policy = db.query(models.Policy).filter(models.Policy.id == policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    async def event_generator():
        async for event in executor.execute_policy_streaming(policy_id, db, triggered_by="manual"):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════
# SENSOR READINGS
# ═══════════════════════════════════════════════════════════════════

@application.get("/api/sensor-readings/", response_model=List[schemas.SensorReadingResponse])
def get_latest_sensor_readings(db: Session = Depends(get_db)):
    """Latest reading for each (device, capability) SSE pair."""
    subq = db.query(
        models.SensorReading.device_id,
        models.SensorReading.capability_name,
        func.max(models.SensorReading.id).label("max_id"),
    ).group_by(
        models.SensorReading.device_id,
        models.SensorReading.capability_name,
    ).subquery()

    readings = db.query(models.SensorReading).join(
        subq, models.SensorReading.id == subq.c.max_id
    ).all()

    return [
        schemas.SensorReadingResponse(
            id=r.id,
            device_id=r.device_id,
            device_name=r.device.name if r.device else "Unknown",
            capability_name=r.capability_name,
            data=r.data,
            received_at=r.received_at,
        )
        for r in readings
    ]


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER (CRON TICK)
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# VOICE TRANSCRIPTION
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio using Groq Whisper."""
    audio_data = await file.read()
    try:
        transcription = llm.groq_client.audio.transcriptions.create(
            file=(file.filename or "recording.webm", audio_data),
            model="whisper-large-v3-turbo",
        )
        return {"text": transcription.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
# VLM / CAMERA TEST PLAYGROUND
# ═══════════════════════════════════════════════════════════════════
#
# Lets the frontend exercise the camera VLM pipeline directly: upload an image
# or video (or pick a bundled test_media sample / paste a URL), give a prompt,
# and get back the same normalized JSON that VLM DAG nodes produce.

_TEST_MEDIA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_media"
)
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def _classify_media(filename: str, content_type: Optional[str]) -> Optional[str]:
    """Return 'video', 'image', or None based on content type / extension."""
    ct = (content_type or "").lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("image/"):
        return "image"
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _IMAGE_EXTS:
        return "image"
    return None


@application.get("/api/vlm/samples")
def list_vlm_samples():
    """List media files bundled in test_media that can be used to test the VLM."""
    samples = []
    if os.path.isdir(_TEST_MEDIA_DIR):
        for name in sorted(os.listdir(_TEST_MEDIA_DIR)):
            kind = _classify_media(name, None)
            if kind:
                samples.append({"name": name, "type": kind})
    return {"samples": samples}


@application.post("/api/vlm/test")
async def test_vlm(
    file: Optional[UploadFile] = File(None),
    sample: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    video_url: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    labels: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    video_frame_count: Optional[int] = Form(None),
):
    """Run a one-off VLM analysis on an uploaded file, a bundled sample, or a URL."""
    args: Dict = {}
    if prompt and prompt.strip():
        args["prompt"] = prompt.strip()
    if labels and labels.strip():
        args["labels"] = [s.strip() for s in labels.split(",") if s.strip()]
    if provider and provider.strip():
        args["provider"] = provider.strip()
    if model and model.strip():
        args["model"] = model.strip()
    if video_frame_count:
        args["video_frame_count"] = video_frame_count

    temp_path: Optional[str] = None
    try:
        # 1) Uploaded file takes priority.
        if file is not None and file.filename:
            kind = _classify_media(file.filename, file.content_type)
            if kind is None:
                raise HTTPException(
                    status_code=400,
                    detail="Unsupported file type. Upload an image or a video.",
                )
            data = await file.read()
            suffix = os.path.splitext(file.filename)[1] or (".mp4" if kind == "video" else ".jpg")
            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix="vlm_test_")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            args["video_path" if kind == "video" else "image_path"] = temp_path

        # 2) Bundled sample from test_media.
        elif sample and sample.strip():
            safe_name = os.path.basename(sample.strip())  # prevent path traversal
            sample_path = os.path.join(_TEST_MEDIA_DIR, safe_name)
            if not os.path.isfile(sample_path):
                raise HTTPException(status_code=404, detail=f"Sample not found: {safe_name}")
            kind = _classify_media(safe_name, None)
            if kind is None:
                raise HTTPException(status_code=400, detail="Sample is not an image or video.")
            args["video_path" if kind == "video" else "image_path"] = sample_path

        # 3) Remote URL.
        elif video_url and video_url.strip():
            args["video_url"] = video_url.strip()
        elif image_url and image_url.strip():
            args["image_url"] = image_url.strip()
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide a file upload, a sample name, an image_url, or a video_url.",
            )

        result = await vision.analyze_camera_image("", args)
        return result

    except vision.VisionAnalysisError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VLM test failed: {str(e)[:300]}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════
# SCHEDULER (CRON TICK)
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/cron/tick")
async def trigger_scheduler(db: Session = Depends(get_db)):
    """Manual scheduler tick — same logic as the background loop."""
    triggered, current_time_str = await _run_scheduler_tick(db)
    return {"status": "ok", "triggered_policies": triggered, "server_time": current_time_str}
