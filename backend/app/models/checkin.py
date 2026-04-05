"""AgentCheckIn — periodic self-assessment record produced by an agent."""

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class AgentCheckIn(Base, TimestampMixin):
    """Records an agent's periodic self-assessment."""

    __tablename__ = "agent_checkins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    goals_reviewed: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
        doc="List of {goal_id, title, progress, status_update} dicts."
    )
    tasks_reviewed: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
        doc="List of {task_id, title, status, note} dicts."
    )
    blockers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    proposed_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    stuck_items: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
        doc="Tasks/goals flagged as stuck (no progress for too long)."
    )
    proposed_initiatives: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
        doc="New project/task ideas the agent proposed."
    )
    had_error: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
