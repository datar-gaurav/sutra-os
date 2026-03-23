"""AgentGoal — persistent goals agents work toward between sessions."""

from enum import Enum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class GoalStatus(str, Enum):
    active = "active"
    paused = "paused"
    completed = "completed"
    abandoned = "abandoned"


class GoalPriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class AgentGoal(Base, TimestampMixin):
    """A persistent goal assigned to an agent."""

    __tablename__ = "agent_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GoalStatus.active.value)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default=GoalPriority.medium.value)
    deadline: Mapped[str | None] = mapped_column(String(30), nullable=True)  # ISO date string
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_notes: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list,
        doc="List of {note: str, timestamp: str} entries."
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
