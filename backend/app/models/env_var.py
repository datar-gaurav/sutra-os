"""EnvVar model — stores .env settings editable from the UI.

Secret values (API keys, tokens, passwords) are stored encrypted via
the Fernet vault. Non-secret values (URLs, cron expressions, etc.) are
stored as plaintext.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class EnvVar(Base, TimestampMixin):
    """Single row per env-var key, value stored encrypted if is_secret=True."""

    __tablename__ = "env_vars"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    # Encrypted ciphertext (is_secret=True) or plaintext (is_secret=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<EnvVar(key={self.key!r}, secret={self.is_secret})>"
