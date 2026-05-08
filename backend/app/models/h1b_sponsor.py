"""H-1B sponsorship lookup table built from the USCIS Employer Data Hub CSV.

The H1BFilter stage of the discovery pipeline checks postings against this
table and tags each posting with a `sponsor_tier`:

    tier_0: no records found
    tier_1: 1-9 approvals across last 3 fiscal years
    tier_2: 10-99 approvals
    tier_3: 100+ approvals
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


def tier_for_approvals(approvals: int) -> int:
    """Map an approval count to a tier integer."""
    if approvals <= 0:
        return 0
    if approvals < 10:
        return 1
    if approvals < 100:
        return 2
    return 3


class H1bSponsor(Base):
    """One row per (employer, fiscal_year, source) — aggregate at query time."""

    __tablename__ = "h1b_sponsors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Normalized employer name (lower, stripped of legal suffixes/punctuation).
    # See app/core/job_discovery/normalize.normalize_company.
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ein: Mapped[str | None] = mapped_column(String(16), nullable=True)

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    approvals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    denials: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # "uscis" | "dol" — only "uscis" populated in v1.
    source: Mapped[str] = mapped_column(String(16), default="uscis", nullable=False)

    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "normalized_name", "fiscal_year", "source",
            name="uq_h1b_sponsors_name_fy_src",
        ),
        Index("ix_h1b_sponsors_normalized_name", "normalized_name"),
        Index("ix_h1b_sponsors_ein", "ein"),
    )


class H1bNameOverride(Base):
    """Manual mapping for high-frequency mismatches (e.g. Alphabet -> Google).

    Edited from the Settings UI. The H1BFilter consults this map first, before
    exact/token matching against `h1b_sponsors`.
    """

    __tablename__ = "h1b_name_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # Both columns are normalized form. `from_name` is what we see in postings,
    # `to_name` is what to look up in h1b_sponsors.
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)
    to_name: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("from_name", name="uq_h1b_name_overrides_from"),
    )
