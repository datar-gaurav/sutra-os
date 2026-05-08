"""Adapter contract and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchQuery:
    """What a config asks an adapter to fetch."""

    title_query: str
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    location_filter: str | None = None
    lookback_hours: int = 24
    # (source -> [board_token, ...]) for adapters that need a per-company token.
    targets: dict[str, list[str]] = field(default_factory=dict)
    # Cap how many postings the adapter is allowed to surface in a single run.
    max_results: int = 200


@dataclass
class NormalizedPosting:
    """Adapter output — uniform shape that the persister writes to JobPosting."""

    source: str
    job_title: str
    company: str
    job_url: str  # canonical apply URL
    source_company_token: str | None = None
    external_id: str | None = None
    location: str | None = None
    salary: str | None = None
    remote: bool | None = None
    description_snippet: str | None = None
    posted_at: datetime | None = None
    matched_terms: list[str] = field(default_factory=list)
    no_sponsorship_signal: bool = False
    raw: dict | None = None


class JobSourceAdapter(ABC):
    """Subclass for each source. `fetch()` is the only required method."""

    name: str = ""
    supports_server_search: bool = False

    @abstractmethod
    async def fetch(self, query: SearchQuery) -> AsyncIterator[NormalizedPosting]:
        """Yield NormalizedPosting items matching `query`.

        Implementations should:
          1. Hit the source's public endpoint.
          2. Apply title/keyword/lookback filters (server-side if supported,
             otherwise locally inside the adapter).
          3. Canonicalize the apply URL.
          4. Yield NormalizedPosting instances.

        On error: log, swallow, return early. The orchestrator catches
        per-adapter exceptions but adapters should fail soft for partial
        success across sources.
        """
        if False:  # pragma: no cover - keeps the type checker happy
            yield  # type: ignore[misc]
