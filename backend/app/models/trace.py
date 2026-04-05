"""Execution trace model — per-request record of agent invocations."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class ExecutionTrace(Base):
    """
    Stores one record per agent invocation (sync or streaming).
    Captures input, output, tool calls, token counts, and latency.
    """

    __tablename__ = "execution_traces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    input_message: Mapped[str] = mapped_column(Text, nullable=False)
    output_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded list of {name, input, output} dicts
    tool_calls: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    had_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
