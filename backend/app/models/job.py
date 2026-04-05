import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, Enum
from app.models.base import Base
import enum

class ExecutionType(str, enum.Enum):
    prompt = "prompt"
    workflow = "workflow"
    n8n_workflow = "n8n_workflow"
    docker_script = "docker_script"

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    execution_type = Column(String, nullable=False) # 'prompt', 'workflow', 'n8n_workflow', 'docker_script'
    
    # Target execution parameters
    target_id = Column(String, nullable=True) # Agent ID, Workflow ID, etc.
    prompt_text = Column(Text, nullable=True) # If prompt type
    n8n_webhook_url = Column(String, nullable=True) # If n8n_workflow type
    script_name = Column(String, nullable=True) # If docker_script type
    
    # Scheduling
    cron_expression = Column(String, nullable=False) # e.g., "0 11 * * 1,2"
    timezone = Column(String, nullable=False, default="America/Los_Angeles")
    is_active = Column(Boolean, default=True)
    
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True) # 'running', 'success', 'failed'
    
    # Notifications
    notify_email = Column(String, nullable=True)  # If set, email output after completion
    notify_telegram_chat_id = Column(String, nullable=True)  # If set, telegram job output on completion
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
