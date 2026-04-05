"""Conversation and message models for agent chat history."""

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, generate_uuid


class Conversation(Base, TimestampMixin):
    """A conversation thread with an agent."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ui"
    )  # ui, slack, api
    source_id: Mapped[str] = mapped_column(String(100), nullable=True)  # e.g. Slack thread_ts
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, agent_id={self.agent_id})>"


class Message(Base, TimestampMixin):
    """A single message in a conversation."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token usage
    token_count: Mapped[int | None] = mapped_column(nullable=True)

    # Tool call metadata (if role == tool)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"
