from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, JSON
from sqlalchemy.orm import relationship
from database import Base

# Association table for Policy <-> Capability (Many-to-Many)
policy_capability_association = Table(
    'policy_capability', Base.metadata,
    Column('policy_id', Integer, ForeignKey('policies.id')),
    Column('capability_id', Integer, ForeignKey('capabilities.id')),
    Column('arguments', JSON) # Store arguments for this specific invocation if needed, though simpler to store in Policy or separate Execution table. 
    # For this prototype, let's store the specific invocation details in the Policy itself as a JSON blob or similar, 
    # OR we can just link them here. 
    # Actually, a policy might use the SAME capability multiple times with different args? 
    # For simplicity, let's assume a policy is a list of "actions", where an action is (Capability, Args).
    # But to keep it relational, let's just link Policy to Capability. 
    # The "Action" logic might be better stored as a JSON column in Policy or a separate table "PolicyAction".
    # Let's stick to the plan: "Policy will have their relevant devices and capabilities associated with it".
    # We'll store the "plan" (which capability + what args) in a JSON column in Policy for now to keep it flexible,
    # AND maintain a relation for querying.
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
    
    # Store the execution plan: list of {device_name, capability_name, args}
    execution_plan = Column(JSON, default=[])

    # We can still keep a relation to capabilities if we want to know dependencies
    capabilities = relationship("Capability", secondary=policy_capability_association)
    
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    task = relationship("Task", back_populates="policies")
