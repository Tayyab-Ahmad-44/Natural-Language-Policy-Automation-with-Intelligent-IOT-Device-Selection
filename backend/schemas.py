from pydantic import BaseModel
from typing import List, Optional, Dict, Any

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
    execution_plan: List[Dict[str, Any]] = [] # [{device: str, capability: str, args: dict}]
    task_id: Optional[int] = None
    
    class Config:
        orm_mode = True

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

class PolicyResponseLLM(BaseModel):
    execution_plan: List[Dict[str, Any]] # [{device: str, capability: str, args: dict}]
    time_window: dict # {from_time: str, to_time: str}
