"""ApprovalRequest model — human-in-the-loop gate for workflow execution."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class ApprovalCategory(str, enum.Enum):
    financial = "financial"
    external = "external"
    destructive = "destructive"
    strategic = "strategic"
    general = "general"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ApprovalRequest(Base, TimestampMixin):
    """A human approval gate — created by agents or workflow engine for high-stakes actions."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # What triggered this approval
    workflow_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True
    )
    node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Agent that requested approval
    requester_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Display info
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Categorization
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Full context for the reviewer (reasoning, alternatives, risk assessment, etc.)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # What to execute if approved (e.g. {"type": "run_prompt", "agent_id": "...", "prompt": "..."})
    action_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=ApprovalStatus.pending.value, nullable=False
    )

    # Who reviewed it
    reviewer_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Expiry
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.id} status={self.status} title={self.title!r}>"
