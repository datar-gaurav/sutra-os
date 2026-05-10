"""Saved searches for the Job Discovery feature.

Each config drives a daily APScheduler cron job that fans out to enabled
source adapters (Greenhouse, Lever, Ashby, SmartRecruiters, CSE discovery)
and persists the discovered postings (deduped, H-1B-tagged) into
`job_postings`.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class JobSearchConfig(Base, TimestampMixin):
    """A user-defined search the scheduler runs daily."""

    __tablename__ = "job_search_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title_query: Mapped[str] = mapped_column(String(500), nullable=False)
    # Extra OR-keywords ("PM", "Product Lead") used to widen the local title match.
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # Strings that, if present in the title, exclude the posting ("intern", "contract").
    exclude_keywords: Mapped[list] = mapped_column(JSON, default=list)
    # Optional substring filter on `location` (case-insensitive). Empty = any.
    location_filter: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # How far back to consider a posting "new" — applied after fetch when the
    # source returns more than 24h of jobs. Always overlap a bit (e.g. 30h on a
    # 24h schedule) so we don't lose postings on the seam.
    lookback_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)

    # Standard 5-field cron, evaluated in `timezone`. Default: 7am every day.
    schedule_cron: Mapped[str] = mapped_column(String(64), default="0 7 * * *", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Los_Angeles", nullable=False)

    # ["greenhouse", "lever", "ashby", "smartrecruiters", "discovery"]
    sources_enabled: Mapped[list] = mapped_column(JSON, default=list)
    max_results_per_run: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    # H-1B filtering — defaults match the v1 product decision: on, tier_1+
    h1b_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    h1b_min_tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Companies to mute regardless of match (e.g. high-volume body shops).
    exclude_companies: Mapped[list] = mapped_column(JSON, default=list)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Telemetry — populated by the scheduler after each run.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_run_count_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_count_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_run_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_job_search_configs_is_active", "is_active"),
    )
