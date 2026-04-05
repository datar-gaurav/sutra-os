"""Evolve models — self-improving platform agent tracking."""

from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class SuggestionCategory(str, Enum):
    platform_health = "platform_health"
    error_pattern = "error_pattern"
    performance = "performance"
    competitor_gap = "competitor_gap"
    feature_idea = "feature_idea"


class SuggestionSource(str, Enum):
    daily_analysis = "daily_analysis"
    competitor_monitor = "competitor_monitor"
    manual = "manual"


class SuggestionStatus(str, Enum):
    proposed = "proposed"
    pending_approval = "pending_approval"
    approved = "approved"
    in_progress = "in_progress"
    completed = "completed"
    rejected = "rejected"
    dismissed = "dismissed"


class SuggestionPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ActionType(str, Enum):
    forge_request = "forge_request"
    task = "task"
    goal = "goal"


class EvolveRunStatus(str, Enum):
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"


class EvolveSuggestion(Base, TimestampMixin):
    """Tracks each improvement suggestion from the Evolve agent."""

    __tablename__ = "evolve_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    evolve_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SuggestionCategory.feature_idea.value
    )
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SuggestionSource.manual.value
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SuggestionPriority.medium.value
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SuggestionStatus.proposed.value
    )

    approval_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )

    action_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    action_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    result_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evolve_runs.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<EvolveSuggestion(id={self.id}, title={self.title!r}, status={self.status})>"


class EvolveRun(Base, TimestampMixin):
    """Tracks each analysis run of the Evolve agent."""

    __tablename__ = "evolve_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    run_type: Mapped[str] = mapped_column(String(30), nullable=False)  # daily_analysis | competitor_monitor
    started_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EvolveRunStatus.running.value
    )
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
