"""Model rate limit configuration for smart routing."""

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class ModelRateLimit(Base, TimestampMixin):
    """Stores rate limit configuration for a specific provider+model combination."""

    __tablename__ = "model_rate_limits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Rate limits — null means unlimited
    requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requests_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # How often the daily counters reset (hours). Default 24.
    refresh_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_rate_limit_provider_model"),
    )

    def __repr__(self) -> str:
        return f"<ModelRateLimit(provider={self.provider}, model={self.model})>"
