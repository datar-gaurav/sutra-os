"""Tag a posting with H-1B sponsorship tier.

Three-step match against `h1b_sponsors`:
    1. Override map (h1b_name_overrides) — manual translations.
    2. Exact normalized name match.
    3. Token-set match (cheap LIKE-based fallback).

The result populates JobPosting.sponsor_tier and .sponsor_match_method.
The dropping decision (filter vs show) is made at *query time* by the API,
not here — this stage only annotates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_discovery.normalize import normalize_company
from app.models.h1b_sponsor import H1bNameOverride, H1bSponsor, tier_for_approvals

logger = logging.getLogger(__name__)


@dataclass
class H1bMatch:
    tier: int
    method: str  # "exact" | "token" | "override" | "none"
    matched_name: str | None = None
    total_approvals: int = 0


async def lookup_h1b(db: AsyncSession, company: str) -> H1bMatch:
    """Look up sponsorship tier for a company name."""
    if not company:
        return H1bMatch(tier=0, method="none")

    norm = normalize_company(company)
    if not norm:
        return H1bMatch(tier=0, method="none")

    # 1. Override map
    override_q = select(H1bNameOverride.to_name).where(H1bNameOverride.from_name == norm)
    override_res = await db.execute(override_q)
    override_to = override_res.scalar()
    target_name = override_to or norm
    method = "override" if override_to else None

    # 2. Exact normalized hit, summed across last 3 fiscal years
    fy_cutoff = await _latest_fy_floor(db)
    exact = await db.execute(
        select(func.sum(H1bSponsor.approvals)).where(
            H1bSponsor.normalized_name == target_name,
            H1bSponsor.fiscal_year >= fy_cutoff,
        )
    )
    approvals = int(exact.scalar() or 0)
    if approvals > 0:
        return H1bMatch(
            tier=tier_for_approvals(approvals),
            method=method or "exact",
            matched_name=target_name,
            total_approvals=approvals,
        )

    # 3. Token-set match — every token of the normalized name must appear
    # as a substring in the row's normalized_name. Cheap and works against
    # the index well enough for v1.
    tokens = [t for t in target_name.split() if len(t) > 2]
    if not tokens:
        return H1bMatch(tier=0, method=method or "none")

    conditions = [H1bSponsor.normalized_name.ilike(f"%{t}%") for t in tokens]
    token_q = select(
        H1bSponsor.normalized_name,
        func.sum(H1bSponsor.approvals).label("appr"),
    ).where(
        H1bSponsor.fiscal_year >= fy_cutoff,
        *conditions,
    ).group_by(H1bSponsor.normalized_name).order_by(func.sum(H1bSponsor.approvals).desc()).limit(1)
    token_res = await db.execute(token_q)
    row = token_res.first()
    if row and row.appr:
        return H1bMatch(
            tier=tier_for_approvals(int(row.appr)),
            method="token",
            matched_name=row.normalized_name,
            total_approvals=int(row.appr),
        )

    return H1bMatch(tier=0, method=method or "none")


async def _latest_fy_floor(db: AsyncSession) -> int:
    """Return the lowest FY we still consider 'recent' (last 3 fiscal years)."""
    res = await db.execute(select(func.max(H1bSponsor.fiscal_year)))
    latest = res.scalar()
    if not latest:
        # No data loaded yet — be permissive so unmatched ≠ false positive.
        return 0
    return int(latest) - 2


async def is_active_sponsor(db: AsyncSession, company: str, min_tier: int = 1) -> bool:
    """Convenience wrapper used in tests."""
    match = await lookup_h1b(db, company)
    return match.tier >= min_tier
