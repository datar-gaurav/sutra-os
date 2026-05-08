"""Google Programmable Search (CSE) discovery adapter.

Casts a wider net than the seeded ATS boards by querying:
    site:greenhouse.io OR site:lever.co OR site:jobs.ashbyhq.com
    OR site:smartrecruiters.com OR site:linkedin.com/jobs
    "{title}"

with `dateRestrict=d1` to bias toward the last 24 hours.

Hard-capped per `settings.job_discovery_cse_query_cap` queries per run.
Discovery yields lightweight NormalizedPosting items — the persister will
upsert them and rely on dedup_hash to merge with anything already found by
the structured ATS adapters.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.config import settings
from app.core.job_discovery.adapters.base import (
    JobSourceAdapter,
    NormalizedPosting,
    SearchQuery,
)
from app.core.job_discovery.http import get_json, make_client
from app.core.job_discovery.normalize import canonicalize_url, title_matches

logger = logging.getLogger(__name__)

CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Domains that imply a particular ATS, used to tag the source on the posting
# we yield. The persister still keys dedup off the canonical URL, so a CSE
# hit on greenhouse.io will collapse with a Greenhouse adapter hit if both
# observed the same posting.
SITE_TO_SOURCE = {
    "greenhouse.io": "greenhouse",
    "boards.greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "jobs.lever.co": "lever",
    "ashbyhq.com": "ashby",
    "jobs.ashbyhq.com": "ashby",
    "smartrecruiters.com": "smartrecruiters",
    "jobs.smartrecruiters.com": "smartrecruiters",
    "linkedin.com": "linkedin",
    "www.linkedin.com": "linkedin",
}

# The siteSearch passed to CSE — kept narrow enough that results are
# almost always real apply pages.
SITE_RESTRICT = (
    "greenhouse.io OR boards.greenhouse.io OR "
    "lever.co OR jobs.lever.co OR "
    "ashbyhq.com OR jobs.ashbyhq.com OR "
    "smartrecruiters.com OR jobs.smartrecruiters.com OR "
    "linkedin.com/jobs"
)


def _source_for_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return "discovery"
    return SITE_TO_SOURCE.get(host, "discovery")


def _company_guess(url: str) -> str:
    """Best-effort company name guess from the apply URL path."""
    try:
        u = urlparse(url)
    except Exception:
        return ""
    parts = [p for p in (u.path or "").split("/") if p]
    if not parts:
        return u.netloc.replace("www.", "").split(".")[0].title()

    # boards.greenhouse.io/{company}/jobs/{id}
    # jobs.lever.co/{site}/{id}
    # jobs.ashbyhq.com/{board}/{id}
    # api.smartrecruiters.com/.../companies/{cid}/postings/{id}
    # www.linkedin.com/jobs/view/{id}
    host = u.netloc.lower()
    if "greenhouse" in host:
        return parts[0].replace("-", " ").title()
    if "lever" in host:
        return parts[0].replace("-", " ").title()
    if "ashby" in host:
        return parts[0].replace("-", " ").title()
    if "smartrecruiters" in host:
        # Try to find the company segment
        for i, p in enumerate(parts):
            if p == "companies" and i + 1 < len(parts):
                return parts[i + 1].replace("-", " ").title()
    if "linkedin" in host:
        return "LinkedIn (resolve company)"
    return parts[0].replace("-", " ").title()


class CSEDiscoveryAdapter(JobSourceAdapter):
    name = "discovery"
    supports_server_search = True

    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        if not settings.google_cse_api_key or not settings.google_cse_id:
            logger.info("discovery: CSE not configured (set GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID)")
            return

        # CSE returns up to 10 results per call; we cap to settings.job_discovery_cse_query_cap.
        cap = max(1, int(settings.job_discovery_cse_query_cap))
        # We always at least one query; pagination uses `start=11, 21, ...` if needed.
        # Don't go beyond ~5 pages even if cap allows — diminishing returns.
        max_pages = min(5, cap)

        # Map "lookback_hours" to CSE's coarse `dateRestrict` parameter.
        if query.lookback_hours <= 24:
            date_restrict = "d1"
        elif query.lookback_hours <= 72:
            date_restrict = "d3"
        elif query.lookback_hours <= 24 * 7:
            date_restrict = "w1"
        else:
            date_restrict = "m1"

        # Build the search query. Quote the title so CSE treats it as a phrase.
        q = f'"{query.title_query}"'

        seen_urls: set[str] = set()
        queries_used = 0

        async with make_client() as client:
            for page in range(max_pages):
                if queries_used >= cap:
                    break
                start = 1 + page * 10
                params = {
                    "key": settings.google_cse_api_key,
                    "cx": settings.google_cse_id,
                    "q": q,
                    "siteSearch": SITE_RESTRICT,
                    "siteSearchFilter": "i",  # include sites in siteSearch
                    "dateRestrict": date_restrict,
                    "num": 10,
                    "start": start,
                }
                payload = await get_json(client, CSE_ENDPOINT, params=params)
                queries_used += 1
                if not isinstance(payload, dict):
                    break
                items = payload.get("items") or []
                if not items:
                    break
                for it in items:
                    link = (it.get("link") or "").strip()
                    title = (it.get("title") or "").strip()
                    if not link or not title:
                        continue
                    canon = canonicalize_url(link)
                    if not canon or canon in seen_urls:
                        continue
                    seen_urls.add(canon)

                    # CSE results often have " - Greenhouse" / " | Lever" suffixes;
                    # apply title_matches on the raw title since the user-defined
                    # exclude_keywords still need to fire.
                    matched, hits = title_matches(
                        title,
                        query.title_query,
                        query.keywords,
                        query.exclude_keywords,
                    )
                    if not matched:
                        continue

                    yield NormalizedPosting(
                        source=_source_for_url(canon),
                        job_title=title,
                        company=_company_guess(canon),
                        job_url=canon,
                        source_company_token=None,
                        external_id=None,
                        location=None,
                        description_snippet=(it.get("snippet") or "").strip() or None,
                        posted_at=datetime.now(timezone.utc),  # CSE doesn't give posted_at
                        matched_terms=hits + ["cse"],
                        no_sponsorship_signal=False,
                        raw={"cse_link": link, "cse_displayLink": it.get("displayLink")},
                    )

        logger.debug(
            "discovery: used %d/%d CSE queries, found %d unique URLs",
            queries_used, cap, len(seen_urls),
        )
