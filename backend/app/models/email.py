"""Email configuration and whitelist models."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class EmailConfig(Base, TimestampMixin):
    """Per-agent SMTP/IMAP email configuration. agent_id=None means the system default."""

    __tablename__ = "email_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # If null this is the system/default config; otherwise scoped to one agent
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, unique=True, index=True
    )

    label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Provider type: SMTP or GMAIL
    provider: Mapped[str] = mapped_column(String(50), default="SMTP", nullable=False)

    # Google OAuth (GMAIL)
    google_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted via vault

    # SMTP (outbound)
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted via vault
    smtp_from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    smtp_use_ssl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # IMAP (inbound — optional)
    imap_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    imap_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imap_password: Mapped[str | None] = mapped_column(Text, nullable=True)  # encrypted
    imap_use_ssl: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    imap_folder: Mapped[str] = mapped_column(String(100), default="INBOX", nullable=False)

    def __repr__(self) -> str:
        if self.provider == "GMAIL":
            return f"<EmailConfig id={self.id} agent_id={self.agent_id} provider={self.provider} email={self.google_email}>"
        return f"<EmailConfig id={self.id} agent_id={self.agent_id} provider={self.provider} host={self.smtp_host}>"


class EmailWhitelist(Base, TimestampMixin):
    """Per-agent list of allowed email recipients. An agent may only send to whitelisted addresses."""

    __tablename__ = "email_whitelist"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Which agent this whitelist entry belongs to. Null = system-wide allowance.
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )

    email_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<EmailWhitelist id={self.id} agent_id={self.agent_id} email={self.email_address}>"
