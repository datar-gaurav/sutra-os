"""Project decision tracking model — captures decisions with reasoning and data points."""

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class ProjectDecision(Base, TimestampMixin):
    """A tracked decision within a project, with reasoning and data points."""

    __tablename__ = "project_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives_considered: Mapped[list | None] = mapped_column(JSON, nullable=True)
    importance: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    data_points: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_decisions.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<ProjectDecision id={self.id} title={self.title!r} importance={self.importance}>"
