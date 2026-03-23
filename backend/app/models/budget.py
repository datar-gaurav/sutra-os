"""Budget model — spending limits per agent, team, or org-wide."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class BudgetScope(str, enum.Enum):
    agent = "agent"
    team = "team"
    org = "org"


class BudgetPeriod(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class Budget(Base, TimestampMixin):
    """A spending limit for an agent, team, or the whole org."""

    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Who this budget applies to
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default=BudgetScope.agent.value)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    team_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Label shown in UI
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Budget period
    period: Mapped[str] = mapped_column(String(20), nullable=False, default=BudgetPeriod.monthly.value)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Limits and thresholds
    limit_usd: Mapped[float] = mapped_column(Float, nullable=False)
    alert_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)

    # Created by
    created_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<Budget {self.name!r} scope={self.scope} limit=${self.limit_usd}>"
