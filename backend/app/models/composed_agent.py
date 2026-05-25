"""Composed Agent database model.

Composed agents are the "advanced" agent kind: their behavior is defined by a
typed directed graph (LLM nodes, guardrails, tools, routers) instead of a single
ReAct loop. They live in their own table to keep the legacy monolithic agent
path (`models.agent.Agent`) untouched.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class ComposedAgent(Base, TimestampMixin):
    """An agent whose execution is defined by a graph_spec rather than a ReAct loop."""

    __tablename__ = "composed_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    folder_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_folders.id", ondelete="SET NULL"), nullable=True
    )

    # The graph: {nodes: [...], edges: [...], entry: nodeId}
    # Validated by app.composed_agents.schemas.GraphSpec before save.
    graph_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Declared scratchpad keys the graph reads/writes — used by the inspector UI
    # and the eval probe system. Optional.
    state_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Draft vs. published. Runtime always uses published_version; edits bump version.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # FK to a future eval_suites table — nullable until evals ship.
    eval_suite_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Lifecycle — mirror agents.is_active / status semantics for parity in the UI
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="stopped")

    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=True, default=dict)

    def __repr__(self) -> str:
        return f"<ComposedAgent(id={self.id}, name={self.name}, v={self.version})>"
