"""Agent database model."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class AgentFolder(Base, TimestampMixin):
    """Represents a folder to organize AI agents."""

    __tablename__ = "agent_folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class Agent(Base, TimestampMixin):
    """Represents a configured AI agent."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    
    # Organization
    folder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_folders.id", ondelete="SET NULL"), nullable=True)

    # Personality / System Prompt
    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="You are a helpful AI assistant.",
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)

    # LLM Configuration — purpose-based routing
    purpose_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("llm_purposes.id", ondelete="SET NULL"), nullable=True
    )

    # Legacy LLM fields — kept for backward compat during migration
    llm_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ollama"
    )
    llm_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="llama3"
    )

    secondary_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    secondary_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    fallback_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fallback_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Tools — list of tool IDs enabled for this agent
    enabled_tools: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped"
    )  # stopped, starting, running, error

    # Slack
    slack_channel_id: Mapped[str] = mapped_column(String(50), nullable=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(50), nullable=True)

    # WhatsApp
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Organizational structure (Phase 1.4)
    role_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_roles.id", ondelete="SET NULL"), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    reports_to_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Template origin
    template_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_templates.id", ondelete="SET NULL"), nullable=True)

    # Archive / retirement (Phase 2.4)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Autonomy controls ──────────────────────────────────────────────────────
    # Online status notification: if true, send a Telegram message when the agent starts
    online_notification_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Auto-approve: actions at or below this risk level skip human approval
    # null = no auto-approval (everything requires human sign-off)
    auto_approve_below: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "low", "medium"

    # Execution budget per single invocation (0 = unlimited)
    max_tool_calls_per_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Daily token budget across all invocations (0 = unlimited)
    max_tokens_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Voice ──────────────────────────────────────────────────────────────────
    # Per-agent voice settings. When voice_enabled=True, the agent will reply
    # with synthesised audio on channels that opt in (telegram_voice_enabled,
    # web_voice_enabled). STT for inbound audio is always available regardless
    # of voice_enabled.
    voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_provider_tts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    voice_provider_stt: Mapped[str | None] = mapped_column(String(50), nullable=True)
    voice_speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Per-channel voice opt-in (D3 — configurable per agent + channel)
    telegram_voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    web_voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Metadata
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=True, default=dict)

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, name={self.name}, status={self.status})>"
