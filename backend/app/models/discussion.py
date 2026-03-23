"""Discussion model for multi-agent group discussions."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class DiscussionType(str, enum.Enum):
    brainstorm = "brainstorm"
    debate = "debate"
    review = "review"
    standup = "standup"
    retrospective = "retrospective"


class DiscussionStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    concluded = "concluded"
    failed = "failed"


class Discussion(Base, TimestampMixin):
    """A structured multi-agent discussion session."""

    __tablename__ = "discussions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(30), default=DiscussionType.brainstorm.value, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=DiscussionStatus.pending.value, nullable=False)

    # Participants stored as JSON list of agent IDs
    participant_agent_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Optional moderator agent
    moderator_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    # Messages: list of {agent_id, agent_name, content, round, timestamp}
    messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Auto-generated after discussion concludes
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list | None] = mapped_column(JSON, nullable=True)

    max_rounds: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Optional link to a task that spawned this discussion
    task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    # Creator
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_by_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )

    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Discussion id={self.id} type={self.type} status={self.status}>"
