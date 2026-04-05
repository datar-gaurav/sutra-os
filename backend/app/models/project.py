"""Project model for task management and project memory isolation."""

import enum
import re

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class ProjectStatus(str, enum.Enum):
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    archived = "archived"


def slugify(name: str) -> str:
    """Generate a URL-safe slug from a project name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:100] or "project"


class Project(Base, TimestampMixin):
    """A project groups related tasks together with isolated memory context."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.active.value, nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    default_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    files_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Denormalized counts
    memory_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Activity tracking
    last_active_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compaction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} slug={self.slug} status={self.status}>"
