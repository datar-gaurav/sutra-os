import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, JSON
from app.models.base import Base

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    definition = Column(JSON, nullable=False, default=dict)
    
    # Scheduling
    schedule_interval = Column(Integer, nullable=True)  # Minutes
    schedule_start_time = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True) # 'running', 'success', 'failed'
    last_run_logs = Column(JSON, nullable=True) # Array of log dicts
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
