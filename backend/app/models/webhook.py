"""Outbound webhook subscriptions and delivery log."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid

# All event types the platform can emit
WEBHOOK_EVENTS = [
    "task.created",
    "task.updated",
    "task.completed",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "agent.started",
    "agent.stopped",
    "agent.error",
    "trigger.fired",
    "discussion.concluded",
    "goal.completed",
    "alert.fired",
    "alert.resolved",
]


class DeliveryStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"


class WebhookSubscription(Base, TimestampMixin):
    """An outbound webhook — fires an HTTP POST to a URL when specified events occur."""

    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # HMAC signing secret (encrypted via vault); null = unsigned
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of event types to subscribe to; ["*"] means all events
    events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Optional: only fire for events from a specific agent
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Custom headers to include in every request (JSON dict)
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Stats
    delivery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<WebhookSubscription id={self.id} name={self.name!r} url={self.url!r}>"


class WebhookDelivery(Base, TimestampMixin):
    """A single outbound webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    subscription_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DeliveryStatus.pending.value
    )
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<WebhookDelivery id={self.id} event={self.event_type} status={self.status}>"
