"""ErrorLog model — persists non-agent platform errors to the database."""

import enum

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class ErrorSeverity(str, enum.Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class ErrorLog(Base, TimestampMixin):
    """Persistent record of platform errors visible to the Evolve agent."""

    __tablename__ = "error_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Where did the error originate?
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # e.g. "route", "background_task", "startup", "tool", "scheduler", "websocket"
    error_type: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        Enum(ErrorSeverity, name="errorseverity"),
        nullable=False,
        default=ErrorSeverity.error.value,
        index=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional context — request path, agent_id, task name, etc.
    request_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
