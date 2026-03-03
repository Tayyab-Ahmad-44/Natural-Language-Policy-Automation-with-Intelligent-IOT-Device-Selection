from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Literal


# ─── Device / Capability ──────────────────────────────────────────

class CapabilityBase(BaseModel):
    name: str
    url: str
    method: str
    input_schema: Dict[str, Any]

class CapabilityCreate(CapabilityBase):
    pass

class Capability(CapabilityBase):
    id: int
    device_id: int

    class Config:
        orm_mode = True

class DeviceBase(BaseModel):
    name: str
    type: str

class DeviceCreate(DeviceBase):
    capabilities: List[CapabilityCreate] = []

class Device(DeviceBase):
    id: int
    capabilities: List[Capability] = []

    class Config:
        orm_mode = True


# ─── DAG Schema (new) ─────────────────────────────────────────────

class ExecutionCondition(BaseModel):
    """Condition that gates whether a DAG node should execute."""
    type: Literal["on_success", "on_failure", "on_value"]
    # Fields below only apply when type == "on_value"
    source_node_id: Optional[str] = None
    field: Optional[str] = None          # dot-path into the source node's response JSON
    operator: Optional[Literal[">", "<", "==", "!=", ">=", "<=", "contains"]] = None
    value: Optional[Any] = None

class ExecutionNode(BaseModel):
    """A single action node in the execution DAG."""
    id: str                                       # unique within the DAG, e.g. "step_1"
    device: str                                    # device name
    capability: str                                # capability name
    args: Dict[str, Any] = {}                      # arguments to send
    dependencies: List[str] = []                   # node IDs that must complete first
    condition: Optional[ExecutionCondition] = None # when to execute (default: on_success of all deps)
    on_failure: Literal["halt_branch", "skip_dependents", "ignore"] = "skip_dependents"

class ExecutionDAG(BaseModel):
    """The complete execution graph for a policy."""
    nodes: List[ExecutionNode]


# ─── Policy ────────────────────────────────────────────────────────

class PolicyBase(BaseModel):
    name: str
    original_text: str

class PolicyCreate(PolicyBase):
    pass

class Policy(PolicyBase):
    id: int
    start_time: str
    end_time: str
    is_active: bool
    execution_plan: Any = None   # stores ExecutionDAG dict or legacy flat list
    task_id: Optional[int] = None

    class Config:
        orm_mode = True


# ─── Task ──────────────────────────────────────────────────────────

class TaskBase(BaseModel):
    name: str
    description: str

class TaskCreate(TaskBase):
    pass

class Task(TaskBase):
    id: int
    created_at: str
    policies: List[Policy] = []

    class Config:
        orm_mode = True


# ─── LLM Response ─────────────────────────────────────────────────

class PolicyResponseLLM(BaseModel):
    execution_dag: ExecutionDAG
    time_window: dict  # {from_time: str, to_time: str}


# ─── DAG Preview Response ─────────────────────────────────────────

class DAGValidation(BaseModel):
    valid: bool
    errors: List[str] = []

class PolicyPreviewResponse(BaseModel):
    execution_dag: ExecutionDAG
    time_window: dict
    validation: DAGValidation
    levels: List[List[str]] = []  # topological levels for frontend layout


# ─── Execution Tracking ───────────────────────────────────────────

class ExecutionStepResponse(BaseModel):
    id: int
    run_id: int
    node_id: str
    device_name: str
    capability_name: str
    args: Dict[str, Any] = {}
    status: str          # pending / running / success / failed / skipped / condition_not_met
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    http_status_code: Optional[int] = None

    class Config:
        orm_mode = True

class ExecutionRunResponse(BaseModel):
    id: int
    policy_id: int
    policy_name: str = ""
    status: str          # pending / running / completed / partial_failure / failed
    triggered_by: str    # scheduler / manual
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True

class ExecutionRunDetail(ExecutionRunResponse):
    steps: List[ExecutionStepResponse] = []
    execution_dag: Optional[ExecutionDAG] = None  # the DAG that was executed
