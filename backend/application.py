from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas, database, llm
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from load_dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file 

# Create the database tables
models.Base.metadata.create_all(bind=database.engine)


application = FastAPI()

application.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev
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

@application.post("/api/devices/", response_model=schemas.Device)
def create_device(device: schemas.DeviceCreate, db: Session = Depends(get_db)):
    db_device = models.Device(name=device.name, type=device.type)
    db.add(db_device)
    db.commit()
    db.refresh(db_device)
    
    # Add capabilities
    for cap in device.capabilities:
        db_cap = models.Capability(
            name=cap.name,
            url=cap.url,
            method=cap.method,
            input_schema=cap.input_schema,
            device_id=db_device.id
        )
        db.add(db_cap)
    
    db.commit()
    db.refresh(db_device)
    return db_device

@application.get("/api/devices/", response_model=List[schemas.Device])
def read_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    devices = db.query(models.Device).offset(skip).limit(limit).all()
    return devices

@application.delete("/api/devices/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    db.delete(device)
    db.commit()
    return {"detail": "Device deleted"}

@application.post("/api/policies/preview")
def preview_policy(policy: schemas.PolicyCreate, db: Session = Depends(get_db)):
    devices = db.query(models.Device).all()
    # Serialize devices with capabilities for LLM
    devices_data = []
    for d in devices:
        caps = []
        for c in d.capabilities:
            caps.append({
                "name": c.name,
                "url": c.url,
                "method": c.method,
                "input_schema": c.input_schema
            })
        devices_data.append({
            "name": d.name,
            "type": d.type,
            "capabilities": caps
        })
    
    try:
        parsed = llm.parse_policy_with_llm(policy.original_text, devices_data)
        return parsed
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@application.post("/api/policies/", response_model=schemas.Policy)
def create_policy(policy: schemas.PolicyCreate, db: Session = Depends(get_db)):
    # 1. Parse again or trust frontend? Let's parse again to be safe/consistent
    devices = db.query(models.Device).all()
    devices_data = []
    for d in devices:
        caps = []
        for c in d.capabilities:
            caps.append({
                "name": c.name,
                "url": c.url,
                "method": c.method,
                "input_schema": c.input_schema
            })
        devices_data.append({
            "name": d.name,
            "type": d.type,
            "capabilities": caps
        })

    parsed = llm.parse_policy_with_llm(policy.original_text, devices_data)
    
    # 2. Create Policy
    db_policy = models.Policy(
        name=policy.name,
        original_text=policy.original_text,
        start_time=parsed.time_window['from_time'],
        end_time=parsed.time_window['to_time'],
        execution_plan=parsed.execution_plan
    )
    
    # 3. Link Capabilities (Optional, for dependency tracking)
    # For now, we just rely on execution_plan JSON.
            
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

@application.post("/api/tasks/", response_model=schemas.Task)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    # 1. Create Task record
    db_task = models.Task(
        name=task.name,
        description=task.description,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    # 2. Break down task using LLM
    devices = db.query(models.Device).all()
    devices_data = []
    for d in devices:
        caps = []
        for c in d.capabilities:
            caps.append({
                "name": c.name,
                "url": c.url,
                "method": c.method,
                "input_schema": c.input_schema
            })
        devices_data.append({
            "name": d.name,
            "type": d.type,
            "capabilities": caps
        })
        
    policy_rules = llm.break_down_task(task.description, devices_data)

    # 3. Create Policies for each returned policy/rule
    for rule in policy_rules:
        try:
            # If LLM returned structured policies (dict with execution_plan), use them directly
            if isinstance(rule, dict) and rule.get("execution_plan") is not None:
                original_text = rule.get("original_text") or f"{task.name} - Policy"
                time_window = rule.get("time_window", {"from_time": "00:00", "to_time": "23:59"})
                execution_plan = rule.get("execution_plan", [])

                db_policy = models.Policy(
                    name=f"{task.name} - {original_text}",
                    original_text=original_text,
                    start_time=time_window.get("from_time", "00:00"),
                    end_time=time_window.get("to_time", "23:59"),
                    execution_plan=execution_plan,
                    task_id=db_task.id
                )
                db.add(db_policy)
            else:
                # Fallback: rule is a natural language string -> parse into execution plan
                parsed = llm.parse_policy_with_llm(rule, devices_data)

                db_policy = models.Policy(
                    name=f"{task.name} - Rule",
                    original_text=rule,
                    start_time=parsed.time_window['from_time'],
                    end_time=parsed.time_window['to_time'],
                    execution_plan=parsed.execution_plan,
                    task_id=db_task.id
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

@application.post("/api/cron/tick")
def trigger_scheduler(db: Session = Depends(get_db)):
    # Simple logic: check if current time is within any policy's window
    now = datetime.now()
    current_time_str = now.strftime("%H:%M")
    
    active_policies = db.query(models.Policy).filter(models.Policy.is_active == True).all()
    triggered = []
    
    for policy in active_policies:
        # Simplified time check
        if policy.start_time <= current_time_str <= policy.end_time:
            triggered.append(policy.name)
            print(f"EXECUTING POLICY: {policy.name}")
            for action in policy.execution_plan:
                device_name = action.get("device")
                cap_name = action.get("capability")
                args = action.get("args")
                print(f"  -> Device: {device_name}, Capability: {cap_name}, Args: {args}")
                
                # Here we would find the actual URL and execute it
                # device = db.query(models.Device).filter(models.Device.name == device_name).first()
                # cap = ...
                # requests.request(cap.method, cap.url, json=args)
            
    return {"status": "ok", "triggered_policies": triggered, "server_time": current_time_str}
