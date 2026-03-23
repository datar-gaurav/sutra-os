"""Team model — groups of agents working together."""

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class Team(Base, TimestampMixin):
    """Represents a team of agents with a shared mission and context."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_context: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Additional system prompt injected into all team members."
    )
    lead_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    member_agent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
