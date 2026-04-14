"""Job application tracking — captured from LinkedIn via Chrome extension."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


# Ordered for kanban columns; keep in sync with frontend.
JOB_STATUSES = [
    "captured",
    "resume_generated",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "archived",
]


class JobApplication(Base, TimestampMixin):
    """A single job posting captured from LinkedIn (or elsewhere) for tracking."""

    __tablename__ = "job_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Captured from the posting
    job_title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="linkedin", nullable=False)

    # Tracking
    status: Mapped[str] = mapped_column(String(32), default="captured", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    # Resume Builder outputs
    resume_drive_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_drive_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analysis_drive_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timeline
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Review loop: how many builder/critic rounds to run (0 = no review).
    review_rounds: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Per-round transcript: [{round, role, agent, content, ts}, ...]
    review_log: Mapped[list | None] = mapped_column(JSON, default=list)

    # Hiring manager / reachable connections scraped from the posting
    # Each entry: {name, title, profile_url, role: "hiring_manager"|"poster"|"connection"}
    people: Mapped[list | None] = mapped_column(JSON, default=list)

    # Raw payload from extension — kept for debugging / future fields
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_job_applications_status", "status"),
        Index("ix_job_applications_company", "company"),
        Index("ix_job_applications_created_at", "created_at"),
    )
