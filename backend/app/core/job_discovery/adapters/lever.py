"""Lever public postings API.

Endpoint: https://api.lever.co/v0/postings/{site}?mode=json

No auth, no `q=` parameter. `createdAt` is a millisecond UNIX timestamp.
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


class LeverAdapter(JobSourceAdapter):
    name = "lever"
    supports_server_search = False

    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        sites = query.targets.get(self.name) or []
        if not sites:
            return
        cutoff_ms = (datetime.now(timezone.utc).timestamp() - query.lookback_hours * 3600) * 1000

        async with make_client() as client:
            for site in sites:
                url = f"https://api.lever.co/v0/postings/{site}"
                payload = await get_json(client, url, params={"mode": "json"})
                if not isinstance(payload, list):
                    logger.info("lever: %s returned no/invalid payload", site)
                    continue
                yielded = 0
                for j in payload:
                    title = (j.get("text") or "").strip()
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

                    created = j.get("createdAt")
                    if isinstance(created, (int, float)) and created < cutoff_ms:
                        continue

                    cats = j.get("categories") or {}
                    location = (cats.get("location") or "").strip() or None
                    salary = (cats.get("commitment") or "").strip() or None
                    apply_url = (j.get("hostedUrl") or j.get("applyUrl") or "").strip()

                    description = j.get("descriptionPlain") or j.get("description")
                    snippet = html_to_snippet(description) if description else None

                    if query.location_filter and location:
                        if query.location_filter.lower() not in location.lower():
                            continue

                    posted_at = None
                    if isinstance(created, (int, float)):
                        try:
                            posted_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc)
                        except Exception:
                            pass

                    # Lever doesn't expose company_name on most boards — site
                    # slug is usually the company name in lowercase.
                    company = site.replace("-", " ").title()

                    yield NormalizedPosting(
                        source=self.name,
                        job_title=title,
                        company=company,
                        job_url=canonicalize_url(apply_url),
                        source_company_token=site,
                        external_id=str(j.get("id") or ""),
                        location=location,
                        salary=salary,
                        description_snippet=snippet,
                        posted_at=posted_at,
                        matched_terms=hits,
                        no_sponsorship_signal=has_no_sponsorship_phrase(snippet),
                        raw={"id": j.get("id"), "createdAt": created},
                    )
                    yielded += 1
                    if yielded >= query.max_results:
                        break
                logger.debug("lever: %s yielded %d", site, yielded)
