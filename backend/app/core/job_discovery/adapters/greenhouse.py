"""Greenhouse public boards API.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

No auth, no `q=` parameter — title filtering happens locally.
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


def _parse_updated(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Greenhouse: "2024-04-01T18:23:54.123-07:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class GreenhouseAdapter(JobSourceAdapter):
    name = "greenhouse"
    supports_server_search = False

    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        tokens = query.targets.get(self.name) or []
        if not tokens:
            return
        cutoff = datetime.now(timezone.utc).timestamp() - query.lookback_hours * 3600

        async with make_client() as client:
            for token in tokens:
                url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
                payload = await get_json(client, url, params={"content": "true"})
                if not isinstance(payload, dict):
                    logger.info("greenhouse: %s returned no/invalid payload", token)
                    continue
                jobs = payload.get("jobs") or []
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
                    updated = _parse_updated(j.get("updated_at"))
                    if updated and updated.timestamp() < cutoff:
                        continue

                    company = (
                        (j.get("company_name") or "").strip()
                        or (payload.get("name") or "").strip()
                        or token
                    )
                    location = ((j.get("location") or {}).get("name") or "").strip() or None
                    apply_url = (j.get("absolute_url") or "").strip()
                    snippet = html_to_snippet(j.get("content"))

                    if query.location_filter and location:
                        if query.location_filter.lower() not in location.lower():
                            continue

                    yield NormalizedPosting(
                        source=self.name,
                        job_title=title,
                        company=company,
                        job_url=canonicalize_url(apply_url),
                        source_company_token=token,
                        external_id=str(j.get("id") or ""),
                        location=location,
                        salary=None,
                        description_snippet=snippet,
                        posted_at=updated,
                        matched_terms=hits,
                        no_sponsorship_signal=has_no_sponsorship_phrase(snippet),
                        raw={"id": j.get("id"), "updated_at": j.get("updated_at")},
                    )
                    yielded += 1
                    if yielded >= query.max_results:
                        break
                logger.debug("greenhouse: %s yielded %d", token, yielded)
