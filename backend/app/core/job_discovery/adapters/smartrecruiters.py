"""SmartRecruiters public postings API.

Endpoint:
    https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings
        ?q={POSITION_TITLE}&limit=100&offset=0

No auth, server-side title search via `q=`. The list endpoint returns
summary objects; we fetch the full detail for sponsorship-phrase scanning.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.core.job_discovery.adapters.base import (
    JobSourceAdapter,
    NormalizedPosting,
    SearchQuery,
)
from app.core.job_discovery.http import get_json, html_to_snippet, make_client
from app.core.job_discovery.normalize import (
    canonicalize_url,
    has_no_sponsorship_phrase,
    title_matches,
)

logger = logging.getLogger(__name__)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class SmartRecruitersAdapter(JobSourceAdapter):
    name = "smartrecruiters"
    supports_server_search = True

    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        companies = query.targets.get(self.name) or []
        if not companies:
            return
        # No cutoff — boards return all open postings; dedup_hash prevents re-inserts.

        async with make_client() as client:
            for cid in companies:
                url = f"https://api.smartrecruiters.com/v1/companies/{cid}/postings"
                payload = await get_json(
                    client,
                    url,
                    params={"q": query.title_query, "limit": 100, "offset": 0},
                )
                if not isinstance(payload, dict):
                    logger.info("smartrecruiters: %s returned no/invalid payload", cid)
                    continue
                content = payload.get("content") or []
                yielded = 0
                for j in content:
                    title = (j.get("name") or "").strip()
                    if not title:
                        continue
                    # Server already filtered by `q`, but still apply local
                    # exclude_keywords + bonus keywords for hit-tracking.
                    matched, hits = title_matches(
                        title,
                        query.title_query,
                        query.keywords,
                        query.exclude_keywords,
                    )
                    if not matched:
                        continue

                    released = _parse_iso(j.get("releasedDate") or j.get("createdOn"))

                    loc = j.get("location") or {}
                    location_parts = [
                        loc.get("city"),
                        loc.get("region"),
                        loc.get("country"),
                    ]
                    location = ", ".join(p for p in location_parts if p) or None

                    apply_url = (j.get("ref") or "").strip() or (j.get("postingUrl") or "").strip()
                    snippet = html_to_snippet(
                        (j.get("jobAd") or {}).get("sections", {}).get("jobDescription", {}).get("text")
                        if isinstance(j.get("jobAd"), dict) else None
                    )
                    company = (j.get("company") or {}).get("name") or cid

                    if query.location_filter and location:
                        if query.location_filter.lower() not in location.lower():
                            continue

                    yield NormalizedPosting(
                        source=self.name,
                        job_title=title,
                        company=company,
                        job_url=canonicalize_url(apply_url),
                        source_company_token=cid,
                        external_id=str(j.get("id") or ""),
                        location=location,
                        salary=None,
                        remote=(loc.get("remote") if isinstance(loc, dict) else None),
                        description_snippet=snippet,
                        posted_at=released,
                        matched_terms=hits,
                        no_sponsorship_signal=has_no_sponsorship_phrase(snippet),
                        raw={"id": j.get("id"), "releasedDate": j.get("releasedDate")},
                    )
                    yielded += 1
                    if yielded >= query.max_results:
                        break
                logger.debug("smartrecruiters: %s yielded %d", cid, yielded)
