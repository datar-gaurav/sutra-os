"""GuardrailEvent — audit log for every guardrail verdict.

One row per Guardrail.check() result. Written by the composed-agent runner
at the end of each run, batched in a single INSERT. Indexed on
(composed_agent_id, created_at) and (run_id) for the trace viewer.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, generate_uuid


class GuardrailEvent(Base):
    """A single guardrail verdict — written once, never mutated."""

    __tablename__ = "guardrail_events"
    __table_args__ = (
        Index("ix_guardrail_events_agent_created", "composed_agent_id", "created_at"),
        Index("ix_guardrail_events_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    composed_agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("composed_agents.id", ondelete="CASCADE"), nullable=False
    )
    # uuid generated per run() invocation — groups events from the same call.
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # The agent-defined attachment id (not the underlying guardrail type) so the
    # trace points at the specific instance the user configured.
    guardrail_id: Mapped[str] = mapped_column(String(100), nullable=False)

    stage: Mapped[str] = mapped_column(String(10), nullable=False)         # input | output
    action: Mapped[str] = mapped_column(String(10), nullable=False)       # allow | mutate | reject | warn
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<GuardrailEvent(agent={self.composed_agent_id}, run={self.run_id}, "
            f"gid={self.guardrail_id}, action={self.action})>"
        )
