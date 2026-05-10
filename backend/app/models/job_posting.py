"""Discovered job postings from public ATS feeds + CSE.

Distinct from `JobApplication` — a posting is something we found, an
application is something the user has decided to pursue. The "Apply" button
in the UI promotes a posting to a JobApplication and back-links it via
`application_id`.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


# UI status. Distinct from JobApplication.status — a posting becomes an
# application when the user hits "Apply".
POSTING_STATUSES = (
    "new",         # never seen by the user
    "seen",        # user opened it (drawer)
    "dismissed",   # user explicitly dismissed
    "applied",     # promoted to a JobApplication row
)

# How the H-1B match was made. "none" means we did look but found nothing —
# different from null, which means we didn't check yet.
H1B_MATCH_METHODS = ("exact", "token", "override", "none")


class JobPosting(Base, TimestampMixin):
    """A single discovered posting, deduped by canonical apply URL."""

    __tablename__ = "job_postings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Which search first surfaced this posting. Other configs that re-find
    # the same posting just bump last_seen_at + matched_terms.
    config_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_company_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # sha256 of the canonicalized apply URL (or composite fallback) — primary
    # dedup key. Unique constraint enforced below.
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    job_title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote: Mapped[bool | None] = mapped_column(nullable=True)

    # Canonical (UTM-stripped, lower-host) apply URL.
    job_url: Mapped[str] = mapped_column(Text, nullable=False)
    description_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source-reported timestamp where available. Falls back to first_seen_at.
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Which search keywords matched. Used to explain "why is this in my feed".
    matched_terms: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)

    # H-1B sponsorship signal — populated at write time by the H1BFilter stage.
    sponsor_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sponsor_match_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Stored separately so we can show "may not sponsor for this role" badge
    # even on tier_3 employers.
    no_sponsorship_signal: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Linked JobApplication once the user clicks Apply.
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Raw payload from the source — kept for debugging / forensics.
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("dedup_hash", name="uq_job_postings_dedup_hash"),
        Index("ix_job_postings_config_id", "config_id"),
        Index("ix_job_postings_status", "status"),
        Index("ix_job_postings_first_seen_at", "first_seen_at"),
        Index("ix_job_postings_company", "company"),
        Index("ix_job_postings_sponsor_tier", "sponsor_tier"),
    )
