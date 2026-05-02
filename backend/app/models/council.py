"""Council model — structured 3-round multi-agent debate with arbitrator."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class CouncilDebateMode(str, enum.Enum):
    role_based = "role_based"
    model_native = "model_native"


class CouncilStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    concluded = "concluded"
    failed = "failed"


class Council(Base, TimestampMixin):
    """A multi-advisor council debate with a non-participating arbitrator."""

    __tablename__ = "councils"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)

    # Free-form context: {background, constraints, non_negotiables, success_criteria}
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Advisor agents (>=2)
    advisor_agent_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Arbitrator agent — must differ from advisors; produces final report
    arbitrator_agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=False
    )

    # role_based | model_native
    debate_mode: Mapped[str] = mapped_column(
        String(20), default=CouncilDebateMode.model_native.value, nullable=False
    )

    # {agent_id: role_name} — populated only when debate_mode == role_based
    role_assignments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    num_rounds: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=CouncilStatus.pending.value, nullable=False
    )

    # Full transcript: {agent_id, agent_name, role, content, round, phase, timestamp}
    messages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Markdown text produced by the arbitrator
    final_report: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Council id={self.id} status={self.status} rounds={self.num_rounds}>"
