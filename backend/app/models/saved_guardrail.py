"""SavedGuardrail — a configured guardrail saved by name for reuse across agents.

Attaching a saved guardrail to an agent SNAPSHOTS its config into the
attachment (so library edits don't silently change every agent's behavior),
but the attachment records source_id + source_version so the UI can offer
"Sync from library" when the library has a newer version.
"""

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class SavedGuardrail(Base, TimestampMixin):
    """A named, reusable guardrail configuration."""

    __tablename__ = "saved_guardrails"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The built-in guardrail type this saved entry wraps (pii_redactor,
    # schema_validator, prompt_judge, injection_detector, or group).
    type: Mapped[str] = mapped_column(String(60), nullable=False)

    # The configured config dict — same shape the attachment carries.
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Bumped on every update — used by the "sync from library" check.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"<SavedGuardrail(id={self.id}, name={self.name}, type={self.type}, v={self.version})>"
