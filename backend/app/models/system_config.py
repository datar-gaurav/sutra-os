"""System configuration — single-row DB table for runtime setting overrides."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SystemConfig(Base, TimestampMixin):
    """
    Single-row key-value store for runtime system configuration.
    Overrides values from config.py / environment variables.
    Only one row exists (id='default').
    """

    __tablename__ = "system_config"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
