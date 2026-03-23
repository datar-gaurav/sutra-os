import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON, ForeignKey
from app.models.base import Base


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    job_ids = Column(JSON, nullable=False, default=list)  # ordered list of Job IDs
    cron_expression = Column(String, nullable=False)       # e.g. "*/30 * * * *"
    timezone = Column(String, nullable=False, default="America/Los_Angeles")
    execution_mode = Column(String, nullable=False, default="parallel")  # "parallel" | "sequential"
    is_active = Column(Boolean, default=True)

    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True)  # running/success/partial/failed

    # Notifications
    notify_email = Column(String, nullable=True)
    notify_telegram_chat_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BatchJobRun(Base):
    __tablename__ = "batch_job_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_job_id = Column(String, ForeignKey("batch_jobs.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="running")  # running/success/partial/failed
    results = Column(JSON, default=dict)  # { job_id: { status, duration_ms, error } }
