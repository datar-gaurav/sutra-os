"""Agent memory model — three-tier self-editing memory with decay.

Tiers:
  - core:     Always injected into agent context (like RAM). Agent's identity, key facts.
  - recall:   Searchable conversation history + extracted facts. Default tier.
  - archival: Long-term compressed storage. Infrequently accessed.
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class MemoryType(str, PyEnum):
    fact = "fact"          # General knowledge / preferences
    episode = "episode"    # Past events / conversation outcomes
    procedure = "procedure"  # How-to / process knowledge


class MemoryTier(str, PyEnum):
    core = "core"          # Always in context — identity, key facts, active goals
    recall = "recall"      # Searchable history — default tier for new memories
    archival = "archival"  # Long-term storage — compressed, infrequently accessed


class Memory(Base, TimestampMixin):
    """Persistent memory for agents. agent_id=None means shared org-wide memory."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType, name="memorytype"), default=MemoryType.fact, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON-encoded list[float] — stored as text; upgraded to pgvector column later
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Three-tier memory fields (Phase 5.1) ─────────────────────────────────
    tier: Mapped[str] = mapped_column(
        String(10), default=MemoryTier.recall.value, nullable=False, index=True
    )
    decay_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default="auto", nullable=False
    )  # auto, agent, user, consolidation
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    consolidated_from: Mapped[list | None] = mapped_column(JSON, nullable=True)  # List of memory IDs
    ttl_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = never expires

    # ── Project-scoped memory (Phase: Project Memory) ─────────────────────────
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
