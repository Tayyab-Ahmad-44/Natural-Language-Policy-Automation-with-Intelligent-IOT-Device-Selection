from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any, Literal


# ─── Device / Capability ──────────────────────────────────────────

class CapabilityBase(BaseModel):
    name: str
    url: str
    method: str
    input_schema: Dict[str, Any]
    sensitive: bool = False

class CapabilityCreate(CapabilityBase):
    pass

class Capability(CapabilityBase):
    id: int
    device_id: int

    model_config = ConfigDict(from_attributes=True)

class DeviceBase(BaseModel):
    name: str
    type: str

class DeviceCreate(DeviceBase):
    capabilities: List[CapabilityCreate] = []

class Device(DeviceBase):
    id: int
    capabilities: List[Capability] = []

    model_config = ConfigDict(from_attributes=True)


# ─── Device Auto-Discovery ────────────────────────────────────────

class DeviceDiscoverRequest(BaseModel):
    """Ask the system to fetch a device catalog from an external endpoint and
    map it into our schema via the LLM."""
    endpoint: str
    headers: Optional[Dict[str, str]] = None

class DeviceDiscoverResponse(BaseModel):
    devices: List[DeviceCreate] = []
    raw_sample: Optional[str] = None   # truncated raw response, for transparency
    warning: Optional[str] = None

class DeviceBulkCreate(BaseModel):
    devices: List[DeviceCreate] = []

class DeviceBulkCreateResponse(BaseModel):
    created: List[Device] = []
    skipped: List[str] = []   # names skipped because they already exist

class DeviceBulkDeleteRequest(BaseModel):
    ids: List[int] = []


# ─── DAG Schema (new) ─────────────────────────────────────────────

class ExecutionCondition(BaseModel):
    """Condition that gates whether a DAG node should execute."""
    type: Literal["on_success", "on_failure", "on_value", "all", "any"]
    # Fields below only apply when type == "on_value"
    source_node_id: Optional[str] = None
    field: Optional[str] = None          # dot-path into the source node's response JSON
    operator: Optional[Literal[">", "<", "==", "!=", ">=", "<=", "contains"]] = None
    value: Optional[Any] = None
    # Nested conditions only apply when type == "all" or "any"
    conditions: Optional[List["ExecutionCondition"]] = None

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
    repeat_interval_seconds: Optional[int] = None
    # When resolving a conflict by "replace old with new", the IDs of the
    # existing policies to delete before saving this one.
    replace_policy_ids: List[int] = []

class Policy(PolicyBase):
    id: int
    start_time: str
    end_time: str
    is_active: bool
    repeat_interval_seconds: Optional[int] = None
    last_executed_at: Optional[str] = None
    execution_plan: Any = None   # stores ExecutionDAG dict or legacy flat list
    task_id: Optional[int] = None
    requires_confirmation: bool = False
    confirmed: bool = False

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)

# Forward reference resolved at the bottom of the module (PolicyConflict is
# defined further down). create_task returns the task plus any conflicts found
# among its generated policies / against existing ones.
class TaskCreateResponse(BaseModel):
    task: Task
    conflicts: List["PolicyConflict"] = []


# ─── LLM Response ─────────────────────────────────────────────────

class PolicyResponseLLM(BaseModel):
    execution_dag: ExecutionDAG
    time_window: dict  # {from_time: str, to_time: str}


# ─── DAG Preview Response ─────────────────────────────────────────

class DAGValidation(BaseModel):
    valid: bool
    errors: List[str] = []

class PolicyConflict(BaseModel):
    policy_id: Optional[int] = None       # existing policy's id (None if an unsaved sibling)
    policy_name: str = ""
    existing_text: str = ""
    existing_window: Dict[str, Any] = {}
    shared_devices: List[str] = []
    type: str = "overlap"                 # contradiction | redundancy | overlap
    severity: str = "medium"              # high | medium | low
    explanation: str = ""
    suggestion: str = ""
    new_policy_name: Optional[str] = None  # which new policy triggered it (task flow)

class PolicyPreviewResponse(BaseModel):
    execution_dag: ExecutionDAG
    time_window: dict
    validation: DAGValidation
    levels: List[List[str]] = []  # topological levels for frontend layout
    conflicts: List[PolicyConflict] = []
    requires_confirmation: bool = False  # True if any node's capability is flagged sensitive


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

    model_config = ConfigDict(from_attributes=True)

class ExecutionRunResponse(BaseModel):
    id: int
    policy_id: int
    policy_name: str = ""
    status: str          # pending / running / completed / partial_failure / failed
    triggered_by: str    # scheduler / manual
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class ExecutionRunDetail(ExecutionRunResponse):
    steps: List[ExecutionStepResponse] = []
    execution_dag: Optional[ExecutionDAG] = None  # the DAG that was executed


# ─── Sensor Readings ──────────────────────────────────────────────

class SensorReadingResponse(BaseModel):
    id: int
    device_id: int
    device_name: str
    capability_name: str
    data: Any
    received_at: str


# Resolve forward reference (PolicyConflict is defined after TaskCreateResponse).
TaskCreateResponse.model_rebuild()
