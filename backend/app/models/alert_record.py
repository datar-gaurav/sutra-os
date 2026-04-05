"""Alert models — configurable rules and persistent alert records."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertStatus(str, enum.Enum):
    firing = "firing"
    acknowledged = "acknowledged"
    resolved = "resolved"
    expired = "expired"


class AlertRuleType(str, enum.Enum):
    error_rate = "error_rate"
    latency_p95 = "latency_p95"
    agent_failure_streak = "agent_failure_streak"
    quota_usage = "quota_usage"
    agent_down = "agent_down"


class AlertRule(Base, TimestampMixin):
    """A configurable alert rule with threshold, window, and notification settings."""

    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    # null = applies to all agents
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Notification channels
    notify_webhook: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_websocket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"<AlertRule id={self.id} name={self.name!r} type={self.rule_type}>"


class AlertRecord(Base, TimestampMixin):
    """A fired alert instance with lifecycle: firing → acknowledged → resolved."""

    __tablename__ = "alert_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="firing", index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    # Dedup key: hash of (rule_type + agent_id + optional context key)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Extra context: threshold, actual_value, window_minutes, etc.
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<AlertRecord id={self.id} type={self.rule_type} status={self.status}>"


# Default rules seeded on startup
DEFAULT_ALERT_RULES = [
    {
        "name": "Error Rate > 1%",
        "rule_type": "error_rate",
        "severity": "warning",
        "threshold": 0.01,
        "window_minutes": 10,
        "cooldown_minutes": 30,
    },
    {
        "name": "Error Rate > 10%",
        "rule_type": "error_rate",
        "severity": "critical",
        "threshold": 0.10,
        "window_minutes": 10,
        "cooldown_minutes": 30,
    },
    {
        "name": "Agent Failure Streak >= 3",
        "rule_type": "agent_failure_streak",
        "severity": "critical",
        "threshold": 3,
        "window_minutes": 30,
        "cooldown_minutes": 60,
    },
    {
        "name": "P95 Latency > 10s",
        "rule_type": "latency_p95",
        "severity": "warning",
        "threshold": 10000,
        "window_minutes": 10,
        "cooldown_minutes": 30,
    },
    {
        "name": "Quota Usage > 80%",
        "rule_type": "quota_usage",
        "severity": "warning",
        "threshold": 0.80,
        "window_minutes": 1440,
        "cooldown_minutes": 60,
    },
    {
        "name": "Quota Exhausted (100%)",
        "rule_type": "quota_usage",
        "severity": "critical",
        "threshold": 1.0,
        "window_minutes": 1440,
        "cooldown_minutes": 60,
    },
]
