"""Ashby public job-board API.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true

No auth, no `q=` parameter. `publishedDate` is ISO-8601.
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


def _format_compensation(comp: dict | None) -> str | None:
    if not isinstance(comp, dict):
        return None
    summary = comp.get("compensationTierSummary") or comp.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    tiers = comp.get("compensationTiers") or comp.get("tiers")
    if isinstance(tiers, list) and tiers:
        first = tiers[0]
        if isinstance(first, dict):
            return first.get("tierSummary") or first.get("summary")
    return None


class AshbyAdapter(JobSourceAdapter):
    name = "ashby"
    supports_server_search = False

    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        boards = query.targets.get(self.name) or []
        if not boards:
            return
        # No cutoff — boards return all open postings; dedup_hash prevents re-inserts.

        async with make_client() as client:
            for board in boards:
                url = f"https://api.ashbyhq.com/posting-api/job-board/{board}"
                payload = await get_json(
                    client, url, params={"includeCompensation": "true"}
                )
                if not isinstance(payload, dict):
                    logger.info("ashby: %s returned no/invalid payload", board)
                    continue
                jobs = payload.get("jobs") or []
                # Some boards return company name on the board envelope
                board_company = (payload.get("name") or board).strip()
                yielded = 0
                for j in jobs:
                    title = (j.get("title") or "").strip()
                    if not title:
                        continue
                    matched, hits = title_matches(
                        title,
                        query.title_query,
                        query.keywords,
                        query.exclude_keywords,
                    )
                    if not matched:
                        continue
                    published = _parse_iso(j.get("publishedDate") or j.get("publishedAt"))

                    location = (j.get("locationName") or j.get("location") or "").strip() or None
                    apply_url = (j.get("applyUrl") or j.get("jobUrl") or "").strip()
                    snippet = html_to_snippet(j.get("descriptionHtml") or j.get("description"))
                    salary = _format_compensation(j.get("compensation"))

                    if query.location_filter and location:
                        if query.location_filter.lower() not in location.lower():
                            continue

                    yield NormalizedPosting(
                        source=self.name,
                        job_title=title,
                        company=board_company,
                        job_url=canonicalize_url(apply_url),
                        source_company_token=board,
                        external_id=str(j.get("id") or ""),
                        location=location,
                        salary=salary,
                        remote=j.get("isRemote"),
                        description_snippet=snippet,
                        posted_at=published,
                        matched_terms=hits,
                        no_sponsorship_signal=has_no_sponsorship_phrase(snippet),
                        raw={
                            "id": j.get("id"),
                            "publishedDate": j.get("publishedDate"),
                        },
                    )
                    yielded += 1
                    if yielded >= query.max_results:
                        break
                logger.debug("ashby: %s yielded %d", board, yielded)
