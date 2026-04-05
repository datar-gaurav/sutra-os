"""Usage tracking and provider limits models."""

from sqlalchemy import Integer, String, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class ModelUsage(Base, TimestampMixin):
    """Tracks the number of requests sent to a specific provider/model per day."""

    __tablename__ = "model_usages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_date: Mapped[Date] = mapped_column(Date, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("provider", "model", "usage_date", name="uq_provider_model_date"),
    )

    def __repr__(self) -> str:
        return f"<ModelUsage(provider={self.provider}, model={self.model}, date={self.usage_date}, count={self.request_count})>"


class ModelLimit(Base, TimestampMixin):
    """Stores the maximum daily request limit for a specific provider and model."""

    __tablename__ = "model_limits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="*")
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_provider_model_limit"),
    )

    def __repr__(self) -> str:
        return f"<ModelLimit(provider={self.provider}, model={self.model}, limit={self.daily_limit})>"
