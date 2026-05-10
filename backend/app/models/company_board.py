"""DB-editable seed list of companies and their ATS board tokens.

The Discovery service iterates these on every run for adapters that need a
per-company token (Greenhouse, Lever, Ashby, SmartRecruiters). The CSE
discovery adapter does NOT use this list — it searches the open web.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


# Sources that consume a board-level token from this table.
PER_BOARD_SOURCES = ("greenhouse", "lever", "ashby", "smartrecruiters")


class CompanyBoard(Base, TimestampMixin):
    """One row = one (source, board_token) pair the discovery service polls."""

    __tablename__ = "company_boards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "greenhouse" | "lever" | "ashby" | "smartrecruiters"
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # The slug Greenhouse calls a "board_token", Lever calls "site",
    # Ashby calls "JOB_BOARD_NAME", SmartRecruiters calls "companyIdentifier".
    board_token: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Auto-disable after N consecutive failed runs (404, empty result, etc.)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "board_token", name="uq_company_boards_source_token"),
        Index("ix_company_boards_source", "source"),
        Index("ix_company_boards_is_active", "is_active"),
    )
