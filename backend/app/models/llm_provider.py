"""LLM Provider model for managing API keys and connection details."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class LLMProvider(Base, TimestampMixin):
    """Stores LLM provider configuration and API keys."""

    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)  # Display name
    provider_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # ollama, openai, anthropic, google, custom
    base_url: Mapped[str] = mapped_column(String(500), nullable=True)  # For Ollama or custom
    api_key_encrypted: Mapped[str] = mapped_column(
        Text, nullable=True
    )  # Encrypted API key
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_tool_calling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<LLMProvider(id={self.id}, name={self.name}, type={self.provider_type})>"
