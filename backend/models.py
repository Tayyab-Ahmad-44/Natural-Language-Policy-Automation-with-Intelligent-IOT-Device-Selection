from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from database import Base

# Association table for Policy <-> Capability (Many-to-Many)
policy_capability_association = Table(
    'policy_capability', Base.metadata,
    Column('policy_id', Integer, ForeignKey('policies.id')),
    Column('capability_id', Integer, ForeignKey('capabilities.id')),
    Column('arguments', JSON)
)

class Capability(Base):
    __tablename__ = "capabilities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    url = Column(String)
    method = Column(String) # GET, POST, etc.
    input_schema = Column(JSON) # The expected JSON structure
    
    device_id = Column(Integer, ForeignKey('devices.id'))
    device = relationship("Device", back_populates="capabilities")

class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String)  # e.g., "camera", "alarm", "lock"

    capabilities = relationship("Capability", back_populates="device", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    created_at = Column(String) # Simple string timestamp for now
    
    policies = relationship("Policy", back_populates="task", cascade="all, delete-orphan")

class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    original_text = Column(String)
    start_time = Column(String)  # HH:MM
    end_time = Column(String)    # HH:MM
    is_active = Column(Boolean, default=True)
    
    # Store the execution plan as DAG JSON: {"nodes": [...]}
    # Also supports legacy flat list format (auto-migrated at runtime)
    execution_plan = Column(JSON, default=[])

    capabilities = relationship("Capability", secondary=policy_capability_association)
    
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    task = relationship("Task", back_populates="policies")
    
    runs = relationship("ExecutionRun", back_populates="policy", cascade="all, delete-orphan")


# ─── Execution Tracking ───────────────────────────────────────────

class ExecutionRun(Base):
    __tablename__ = "execution_runs"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey('policies.id'))
    status = Column(String, default="pending")  # pending / running / completed / partial_failure / failed
    triggered_by = Column(String, default="manual")  # scheduler / manual
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)
    summary = Column(JSON, nullable=True)  # {total, success, failed, skipped, condition_not_met}

    policy = relationship("Policy", back_populates="runs")
    steps = relationship("ExecutionStep", back_populates="run", cascade="all, delete-orphan")


class ExecutionStep(Base):
    __tablename__ = "execution_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey('execution_runs.id'))
    node_id = Column(String)         # matches DAG node id, e.g. "step_1"
    device_name = Column(String)
    capability_name = Column(String)
    args = Column(JSON, default={})
    status = Column(String, default="pending")  # pending / running / success / failed / skipped / condition_not_met
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)
    response_data = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    http_status_code = Column(Integer, nullable=True)

    run = relationship("ExecutionRun", back_populates="steps")
