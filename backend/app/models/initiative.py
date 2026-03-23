"""AgentInitiative — a proposal from an agent queued for human review."""

from enum import Enum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class InitiativeStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    implemented = "implemented"


class AgentInitiative(Base, TimestampMixin):
    """An agent-proposed initiative awaiting human review."""

    __tablename__ = "agent_initiatives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checkin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_checkins.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    estimated_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InitiativeStatus.pending.value, index=True
    )
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
