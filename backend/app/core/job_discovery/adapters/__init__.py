"""Source adapters. One file per ATS / discovery layer."""

from app.core.job_discovery.adapters.base import (
    JobSourceAdapter,
    NormalizedPosting,
    SearchQuery,
)
from app.core.job_discovery.adapters.ashby import AshbyAdapter
from app.core.job_discovery.adapters.discovery import CSEDiscoveryAdapter
from app.core.job_discovery.adapters.greenhouse import GreenhouseAdapter
from app.core.job_discovery.adapters.lever import LeverAdapter
from app.core.job_discovery.adapters.smartrecruiters import SmartRecruitersAdapter

__all__ = [
    "JobSourceAdapter",
    "NormalizedPosting",
    "SearchQuery",
    "AshbyAdapter",
    "CSEDiscoveryAdapter",
    "GreenhouseAdapter",
    "LeverAdapter",
    "SmartRecruitersAdapter",
]


def build_default_registry() -> dict[str, JobSourceAdapter]:
    """Return one instance per source keyed by its `name`."""
    return {
        a.name: a for a in (
            GreenhouseAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            SmartRecruitersAdapter(),
            CSEDiscoveryAdapter(),
        )
    }
