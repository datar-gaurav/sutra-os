"""Skill DB models — thin pointers to filesystem-backed manifests.

The source of truth for skill content (body, tools, config_schema, icon,
category) lives on disk under `backend/skills/<slug>/SKILL.md` and is loaded
by app.skills.registry. The DB stores only:

  - a stable surrogate `id` (used as FK target for AgentSkill / RoleSkill joins)
  - the `slug` (matches the directory name on disk)
  - cached `name` and `description` for UI list/search without disk reads
  - `trigger_embedding` + `trigger_hash` + `trigger_embed_model` for the router
  - `routing_threshold` per-skill override
  - `is_active` (set False when the folder is removed but attachments still exist)
"""

from sqlalchemy import Boolean, CHAR, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Skill(Base, TimestampMixin):
    """Thin DB pointer to a filesystem-backed skill manifest."""

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Routing
    trigger_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # json.dumps(list[float])
    trigger_hash: Mapped[str | None] = mapped_column(CHAR(16), nullable=True)
    trigger_embed_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    routing_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)


class AgentSkill(Base, TimestampMixin):
    """Many-to-many join: agent ↔ skill, with per-attachment config and pinning."""

    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Pin: when True, the skill loads every turn regardless of the router.
    always_load: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    skill: Mapped["Skill"] = relationship("Skill", lazy="noload")


class RoleSkill(Base, TimestampMixin):
    """Many-to-many join: agent_role ↔ skill — default skills applied via a role."""

    __tablename__ = "role_skills"
    __table_args__ = (UniqueConstraint("role_id", "skill_id", name="uq_role_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    always_load: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    skill: Mapped["Skill"] = relationship("Skill", lazy="noload")
