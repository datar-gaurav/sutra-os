"""Job-discovery orchestration.

`run_job_search(config_id)` is the top-level entry point — fans out to
enabled adapters concurrently, normalizes, applies the H-1B filter, dedups,
upserts into `job_postings`, writes a run summary back to the config.

`promote_to_application(posting_id)` mirrors the LinkedIn-extension capture
path: creates a JobApplication row and fires the existing resume review
loop in the background.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_discovery.adapters import (
    NormalizedPosting,
    SearchQuery,
    build_default_registry,
)
from app.core.job_discovery.h1b_filter import lookup_h1b
from app.core.job_discovery.normalize import (
    canonicalize_url,
    dedup_hash,
    normalize_company,
)
from app.db.session import async_session_factory
from app.models.company_board import PER_BOARD_SOURCES, CompanyBoard
from app.models.job_application import JobApplication
from app.models.job_posting import JobPosting
from app.models.job_search_config import JobSearchConfig

logger = logging.getLogger(__name__)


# ─── Targets resolution ──────────────────────────────────────────────────────

async def _build_targets(db: AsyncSession) -> dict[str, list[str]]:
    """Read active CompanyBoard rows into the {source: [token, ...]} shape."""
    result = await db.execute(
        select(CompanyBoard).where(
            CompanyBoard.is_active == True,  # noqa: E712
            CompanyBoard.source.in_(PER_BOARD_SOURCES),
        )
    )
    targets: dict[str, list[str]] = {s: [] for s in PER_BOARD_SOURCES}
    for row in result.scalars().all():
        targets.setdefault(row.source, []).append(row.board_token)
    return targets


# ─── Per-adapter fetch + collection ──────────────────────────────────────────

async def _collect_one(adapter, query: SearchQuery) -> tuple[str, list[NormalizedPosting], str | None]:
    name = adapter.name
    out: list[NormalizedPosting] = []
    try:
        async for p in adapter.fetch(query):
            out.append(p)
    except Exception as e:
        logger.exception("adapter %s failed: %s", name, e)
        return name, out, str(e)
    return name, out, None


# ─── Persistence ─────────────────────────────────────────────────────────────

async def _upsert_posting(
    db: AsyncSession,
    p: NormalizedPosting,
    *,
    config_id: str | None,
) -> tuple[bool, str]:
    """Upsert a single posting. Returns (is_new, posting_id)."""
    canon_url = canonicalize_url(p.job_url)
    h = dedup_hash(
        canon_url,
        fallback=(p.company, p.job_title, p.location or ""),
    )

    # Check sponsorship tier — done inline so the row is fully tagged on insert.
    h1b_match = await lookup_h1b(db, p.company)

    now = datetime.now(timezone.utc)
    posted_at = p.posted_at or now

    values = {
        "config_id": config_id,
        "source": p.source,
        "source_company_token": p.source_company_token,
        "external_id": p.external_id,
        "dedup_hash": h,
        "job_title": p.job_title[:500],
        "company": (p.company or "Unknown")[:255],
        "location": (p.location or None) and p.location[:255],
        "salary": (p.salary or None) and p.salary[:255],
        "remote": p.remote,
        "job_url": canon_url or p.job_url,
        "description_snippet": p.description_snippet or None,
        "posted_at": posted_at,
        "first_seen_at": now,
        "last_seen_at": now,
        "matched_terms": p.matched_terms,
        "status": "new",
        "sponsor_tier": h1b_match.tier,
        "sponsor_match_method": h1b_match.method,
        "no_sponsorship_signal": p.no_sponsorship_signal,
        "raw_payload": p.raw,
    }

    # Postgres UPSERT keyed on dedup_hash. On collision we bump last_seen_at and
    # union the matched_terms — matching the design doc's "hard key" behaviour.
    stmt = pg_insert(JobPosting).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_job_postings_dedup_hash",
        set_={
            "last_seen_at": now,
            # Re-tag sponsorship in case the loader has run since first_seen.
            "sponsor_tier": values["sponsor_tier"],
            "sponsor_match_method": values["sponsor_match_method"],
            # Refresh body so older rows pick up the full description after
            # the snippet cap was raised (was 2000, now 32000).
            "description_snippet": values["description_snippet"],
        },
    ).returning(JobPosting.id, JobPosting.first_seen_at)

    result = await db.execute(stmt)
    row = result.first()
    is_new = bool(row and row.first_seen_at == now)
    return is_new, (row.id if row else "")


# ─── Public: run_job_search ──────────────────────────────────────────────────

async def run_job_search(config_id: str) -> dict:
    """Execute one full discovery run for a config. Returns a summary dict."""
    started_at = datetime.now(timezone.utc)
    logger.info("[discovery] config %s starting", config_id)

    async with async_session_factory() as db:
        cfg = await db.get(JobSearchConfig, config_id)
        if not cfg:
            return {"status": "missing", "config_id": config_id}
        if not cfg.is_active:
            return {"status": "inactive", "config_id": config_id}

        targets = await _build_targets(db)
        excluded_companies_norm = {normalize_company(c) for c in (cfg.exclude_companies or []) if c}

    sources = list(cfg.sources_enabled or [])
    registry = build_default_registry()
    selected = [registry[s] for s in sources if s in registry]

    if not selected:
        async with async_session_factory() as db:
            row = await db.get(JobSearchConfig, config_id)
            if row:
                row.last_run_at = started_at
                row.last_run_status = "no_sources"
                row.last_run_error = "No enabled sources match the registry."
                await db.commit()
        return {"status": "no_sources", "config_id": config_id}

    query = SearchQuery(
        title_query=cfg.title_query,
        keywords=list(cfg.keywords or []),
        exclude_keywords=list(cfg.exclude_keywords or []),
        location_filter=cfg.location_filter,
        # Always overlap a bit so we don't lose postings on the seam.
        lookback_hours=int(cfg.lookback_hours * 1.25 + 6),
        targets=targets,
        max_results=cfg.max_results_per_run,
    )

    # Concurrent fetch
    results = await asyncio.gather(
        *[_collect_one(a, query) for a in selected],
        return_exceptions=False,
    )

    # Flatten + apply config-level exclude_companies
    all_postings: list[NormalizedPosting] = []
    per_source_counts: Counter[str] = Counter()
    per_source_errors: dict[str, str] = {}
    for name, ps, err in results:
        if err:
            per_source_errors[name] = err
        for p in ps:
            if normalize_company(p.company) in excluded_companies_norm:
                continue
            all_postings.append(p)
            per_source_counts[name] += 1

    # Persist + mark per_source counts
    new_count = 0
    seen_count = 0
    persisted_errors = 0
    async with async_session_factory() as db:
        for p in all_postings:
            try:
                is_new, _pid = await _upsert_posting(db, p, config_id=config_id)
                if is_new:
                    new_count += 1
                else:
                    seen_count += 1
            except Exception as e:
                persisted_errors += 1
                logger.warning("upsert failed for %s/%s: %s", p.source, p.job_title, e)
        await db.commit()

        cfg = await db.get(JobSearchConfig, config_id)
        if cfg:
            cfg.last_run_at = started_at
            cfg.last_run_count_new = new_count
            cfg.last_run_count_seen = seen_count
            cfg.last_run_status = "ok" if not per_source_errors else "partial"
            cfg.last_run_summary = {
                "per_source": dict(per_source_counts),
                "errors": per_source_errors,
                "duration_sec": (datetime.now(timezone.utc) - started_at).total_seconds(),
                "persisted_errors": persisted_errors,
            }
            cfg.last_run_error = "; ".join(f"{k}: {v}" for k, v in per_source_errors.items()) or None
            await db.commit()

    summary = {
        "status": "ok" if not per_source_errors else "partial",
        "config_id": config_id,
        "new": new_count,
        "seen": seen_count,
        "per_source": dict(per_source_counts),
        "errors": per_source_errors,
        "persisted_errors": persisted_errors,
    }
    logger.info("[discovery] config %s done: %s", config_id, summary)
    return summary


# ─── Public: promote_to_application ──────────────────────────────────────────

async def promote_to_application(posting_id: str) -> dict:
    """Create a JobApplication from a JobPosting and fire the resume loop.

    Mirrors the LinkedIn-extension capture path in
    api/routes/job_applications.py::capture_job — except the posting comes
    from the discovery feed instead of the Chrome extension.
    """
    from app.models.trigger import AgentTrigger

    async with async_session_factory() as db:
        posting = await db.get(JobPosting, posting_id)
        if not posting:
            return {"status": "missing", "posting_id": posting_id}
        if posting.application_id:
            existing = await db.get(JobApplication, posting.application_id)
            if existing:
                return {
                    "status": "already_promoted",
                    "posting_id": posting_id,
                    "application_id": existing.id,
                }

        # Re-use the dedup logic from capture_job — link to existing JobApp
        # if (company, job_title) already exists.
        existing_app = None
        if posting.company:
            res = await db.execute(
                select(JobApplication).where(
                    JobApplication.company == posting.company,
                    JobApplication.job_title == posting.job_title,
                )
            )
            existing_app = res.scalars().first()

        if existing_app:
            app_row = existing_app
            app_row.location = posting.location or app_row.location
            app_row.salary = posting.salary or app_row.salary
            app_row.job_description = (
                posting.description_snippet or app_row.job_description
            )
            app_row.job_url = posting.job_url or app_row.job_url
        else:
            app_row = JobApplication(
                job_title=posting.job_title,
                company=posting.company,
                location=posting.location,
                salary=posting.salary,
                job_description=posting.description_snippet,
                job_url=posting.job_url,
                source=f"discovery:{posting.source}",
                status="captured",
                review_rounds=2,
                raw_payload={"posting_id": posting.id, "raw": posting.raw_payload},
            )
            db.add(app_row)

        await db.flush()
        application_id = app_row.id

        # Link the posting back, mark applied
        posting.application_id = application_id
        posting.status = "applied"
        await db.commit()

        # Look up the LinkedIn Job Webhook trigger so the resume builder fires.
        trig_result = await db.execute(
            select(AgentTrigger).where(
                AgentTrigger.trigger_type == "webhook",
                AgentTrigger.is_active == True,  # noqa: E712
                AgentTrigger.name == "LinkedIn Job Webhook",
            )
        )
        trigger = trig_result.scalars().first()

    fired = False
    if trigger:
        fire_payload = {
            "application_id": application_id,
            "job_title": app_row.job_title,
            "company": app_row.company,
            "location": app_row.location,
            "salary": app_row.salary,
            "job_description": app_row.job_description,
            "job_url": app_row.job_url,
        }
        try:
            from app.core.resume_review_loop import run_resume_review_loop
            asyncio.create_task(run_resume_review_loop(application_id, fire_payload))
            fired = True
        except Exception as e:
            logger.exception("Failed to schedule resume review loop: %s", e)

    return {
        "status": "promoted",
        "posting_id": posting_id,
        "application_id": application_id,
        "deduped": existing_app is not None,
        "resume_loop_fired": fired,
    }
