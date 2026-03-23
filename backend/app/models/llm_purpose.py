"""LLM Purpose model — defines priority-ordered model slots for a use case."""

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class LLMPurpose(Base, TimestampMixin):
    """A named purpose (e.g. Reasoning, Summarization) with up to 5 priority model slots."""

    __tablename__ = "llm_purposes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Each priority slot is a JSON dict: {"provider": str, "model": str} or null
    priority_1: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority_2: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority_3: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority_4: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority_5: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def get_slots(self) -> list[dict]:
        """Return non-null priority slots in order."""
        slots = []
        for i in range(1, 6):
            slot = getattr(self, f"priority_{i}")
            if slot and isinstance(slot, dict) and slot.get("provider") and slot.get("model"):
                slots.append(slot)
        return slots

    def __repr__(self) -> str:
        return f"<LLMPurpose(id={self.id}, name={self.name})>"
