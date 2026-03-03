from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import asyncio
import models, schemas, database, llm, dag_utils, executor
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from load_dotenv import load_dotenv

load_dotenv()

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)


application = FastAPI()

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

        return schemas.PolicyPreviewResponse(
            execution_dag=parsed.execution_dag,
            time_window=parsed.time_window,
            validation=validation,
            levels=levels,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@application.post("/api/policies/", response_model=schemas.Policy)
def create_policy(policy: schemas.PolicyCreate, db: Session = Depends(get_db)):
    """Parse natural language policy via LLM and save with DAG execution plan."""
    devices_data = _serialize_devices(db)
    parsed = llm.parse_policy_with_llm(policy.original_text, devices_data)

    db_policy = models.Policy(
        name=policy.name,
        original_text=policy.original_text,
        start_time=parsed.time_window["from_time"],
        end_time=parsed.time_window["to_time"],
        execution_plan=dag_utils.dag_to_dict(parsed.execution_dag),
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


# ═══════════════════════════════════════════════════════════════════
# TASK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/tasks/", response_model=schemas.Task)
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

    for rule in policy_rules:
        try:
            if isinstance(rule, dict) and rule.get("execution_dag") is not None:
                # New DAG format from LLM
                original_text = rule.get("original_text") or f"{task.name} - Policy"
                time_window = rule.get("time_window", {"from_time": "00:00", "to_time": "23:59"})
                execution_dag = rule.get("execution_dag", {"nodes": []})

                db_policy = models.Policy(
                    name=f"{task.name} - {original_text}",
                    original_text=original_text,
                    start_time=time_window.get("from_time", "00:00"),
                    end_time=time_window.get("to_time", "23:59"),
                    execution_plan=execution_dag,
                    task_id=db_task.id,
                )
                db.add(db_policy)
            elif isinstance(rule, dict) and rule.get("execution_plan") is not None:
                # Legacy flat format — convert to DAG
                original_text = rule.get("original_text") or f"{task.name} - Policy"
                time_window = rule.get("time_window", {"from_time": "00:00", "to_time": "23:59"})
                execution_plan = rule.get("execution_plan", [])
                dag = dag_utils.migrate_flat_to_dag(execution_plan)

                db_policy = models.Policy(
                    name=f"{task.name} - {original_text}",
                    original_text=original_text,
                    start_time=time_window.get("from_time", "00:00"),
                    end_time=time_window.get("to_time", "23:59"),
                    execution_plan=dag_utils.dag_to_dict(dag),
                    task_id=db_task.id,
                )
                db.add(db_policy)
            else:
                # Fallback: rule is a string -> parse via LLM
                parsed = llm.parse_policy_with_llm(rule, devices_data)
                db_policy = models.Policy(
                    name=f"{task.name} - Rule",
                    original_text=rule,
                    start_time=parsed.time_window["from_time"],
                    end_time=parsed.time_window["to_time"],
                    execution_plan=dag_utils.dag_to_dict(parsed.execution_dag),
                    task_id=db_task.id,
                )
                db.add(db_policy)
        except Exception as e:
            print(f"Failed to create policy for rule '{rule}': {e}")

    db.commit()
    db.refresh(db_task)
    return db_task

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
# SCHEDULER (CRON TICK)
# ═══════════════════════════════════════════════════════════════════

@application.post("/api/cron/tick")
async def trigger_scheduler(db: Session = Depends(get_db)):
    """
    Scheduler tick: checks current time against active policy windows.
    For each matching policy, executes its DAG via the LangGraph executor.
    """
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")

    active_policies = db.query(models.Policy).filter(models.Policy.is_active == True).all()
    triggered = []

    for policy in active_policies:
        if policy.start_time <= current_time_str <= policy.end_time:
            try:
                run = await executor.execute_policy(policy.id, db, triggered_by="scheduler")
                triggered.append({
                    "policy_name": policy.name,
                    "run_id": run.id,
                    "status": run.status,
                    "summary": run.summary,
                })
            except Exception as e:
                triggered.append({
                    "policy_name": policy.name,
                    "error": str(e),
                })

    return {"status": "ok", "triggered_policies": triggered, "server_time": current_time_str}
