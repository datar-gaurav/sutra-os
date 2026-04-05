"""AgentTrigger — event-driven action triggers (webhook / schedule / manual)."""

import secrets
from enum import Enum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class TriggerType(str, Enum):
    webhook = "webhook"
    schedule = "schedule"
    manual = "manual"


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class AgentTrigger(Base, TimestampMixin):
    """A configured trigger that fires an agent when conditions are met."""

    __tablename__ = "agent_triggers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False, default=TriggerType.manual.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # For schedule triggers
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # For webhook triggers — unique token for public endpoint
    webhook_token: Mapped[str] = mapped_column(
        String(64), nullable=False, default=generate_token, unique=True, index=True
    )

    # The prompt sent to the agent when fired (supports {payload} placeholder)
    prompt_template: Mapped[str] = mapped_column(
        Text, nullable=False, default="You have been triggered. Please review your goals and report status."
    )

    # Execution history
    last_fired_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fire_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
