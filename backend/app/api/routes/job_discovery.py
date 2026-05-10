"""Job-discovery API — configs, postings, company boards, H-1B refresh."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_discovery.adapters import build_default_registry
from app.core.job_discovery.h1b_loader import (
    DEFAULT_USCIS_SOURCES,
    load_uscis_bytes,
    load_uscis_csv,
    refresh_uscis_default,
)
from app.core.job_discovery.service import promote_to_application, run_job_search
from app.db.session import get_db
from app.models.company_board import PER_BOARD_SOURCES, CompanyBoard
from app.models.h1b_sponsor import H1bSponsor
from app.models.job_posting import JobPosting
from app.models.job_search_config import JobSearchConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/job-discovery", tags=["job-discovery"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ConfigIn(BaseModel):
    name: str
    title_query: str
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    location_filter: str | None = None
    lookback_hours: int = 24
    schedule_cron: str = "0 7 * * *"
    timezone: str = "America/Los_Angeles"
    sources_enabled: list[str] = Field(
        default_factory=lambda: ["greenhouse", "lever", "ashby", "smartrecruiters", "discovery"]
    )
    max_results_per_run: int = 200
    h1b_only: bool = True
    h1b_min_tier: int = 1
    exclude_companies: list[str] = Field(default_factory=list)
    is_active: bool = True


class ConfigPatch(BaseModel):
    name: str | None = None
    title_query: str | None = None
    keywords: list[str] | None = None
    exclude_keywords: list[str] | None = None
    location_filter: str | None = None
    lookback_hours: int | None = None
    schedule_cron: str | None = None
    timezone: str | None = None
    sources_enabled: list[str] | None = None
    max_results_per_run: int | None = None
    h1b_only: bool | None = None
    h1b_min_tier: int | None = None
    exclude_companies: list[str] | None = None
    is_active: bool | None = None


class ConfigOut(BaseModel):
    id: str
    name: str
    title_query: str
    keywords: list[str]
    exclude_keywords: list[str]
    location_filter: str | None
    lookback_hours: int
    schedule_cron: str
    timezone: str
    sources_enabled: list[str]
    max_results_per_run: int
    h1b_only: bool
    h1b_min_tier: int
    exclude_companies: list[str]
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_count_new: int
    last_run_count_seen: int
    last_run_summary: dict | None
    last_run_error: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PostingOut(BaseModel):
    id: str
    config_id: str | None
    source: str
    source_company_token: str | None
    external_id: str | None
    job_title: str
    company: str
    location: str | None
    salary: str | None
    remote: bool | None
    job_url: str
    description_snippet: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    matched_terms: list[str]
    status: str
    sponsor_tier: int | None
    sponsor_match_method: str | None
    no_sponsorship_signal: bool
    application_id: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PostingPatch(BaseModel):
    status: str | None = None  # only "seen" / "dismissed" allowed via API


class CompanyBoardIn(BaseModel):
    company_name: str
    source: str
    board_token: str
    is_active: bool = True


class CompanyBoardOut(CompanyBoardIn):
    id: str
    consecutive_failures: int
    last_success_at: datetime | None
    last_failure_reason: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Configs CRUD ────────────────────────────────────────────────────────────

@router.get("/configs", response_model=list[ConfigOut])
async def list_configs(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(JobSearchConfig).order_by(JobSearchConfig.created_at.desc()))
    return res.scalars().all()


@router.post("/configs", response_model=ConfigOut)
async def create_config(payload: ConfigIn, db: AsyncSession = Depends(get_db)):
    cfg = JobSearchConfig(**payload.model_dump())
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    # Re-sync scheduler so the new config is picked up immediately.
    try:
        from app.core.scheduler import sync_job_search_configs
        await sync_job_search_configs()
    except Exception as e:
        logger.warning("scheduler resync after config create failed: %s", e)
    return cfg


@router.patch("/configs/{config_id}", response_model=ConfigOut)
async def update_config(
    config_id: str,
    payload: ConfigPatch,
    db: AsyncSession = Depends(get_db),
):
    cfg = await db.get(JobSearchConfig, config_id)
    if not cfg:
        raise HTTPException(404, "Config not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    await db.commit()
    await db.refresh(cfg)
    try:
        from app.core.scheduler import sync_job_search_configs
        await sync_job_search_configs()
    except Exception as e:
        logger.warning("scheduler resync after config update failed: %s", e)
    return cfg


@router.delete("/configs/{config_id}")
async def delete_config(config_id: str, db: AsyncSession = Depends(get_db)):
    cfg = await db.get(JobSearchConfig, config_id)
    if not cfg:
        raise HTTPException(404, "Config not found")
    await db.delete(cfg)
    await db.commit()
    try:
        from app.core.scheduler import sync_job_search_configs
        await sync_job_search_configs()
    except Exception as e:
        logger.warning("scheduler resync after config delete failed: %s", e)
    return {"deleted": True}


@router.post("/configs/{config_id}/run")
async def run_config_now(
    config_id: str,
    background_tasks: BackgroundTasks,
    inline: bool = Query(False, description="Run inline and return summary (slower)"),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a search now. Defaults to background; inline=true waits for the result."""
    cfg = await db.get(JobSearchConfig, config_id)
    if not cfg:
        raise HTTPException(404, "Config not found")
    if inline:
        return await run_job_search(config_id)
    background_tasks.add_task(run_job_search, config_id)
    return {"status": "queued", "config_id": config_id}


# ─── Postings ────────────────────────────────────────────────────────────────

@router.get("/postings", response_model=list[PostingOut])
async def list_postings(
    config_id: str | None = Query(None),
    status: str | None = Query(None),
    source: str | None = Query(None),
    since_hours: int | None = Query(None),
    search: str | None = Query(None),
    h1b_only: bool | None = Query(None),
    h1b_min_tier: int | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JobPosting)
    if config_id:
        stmt = stmt.where(JobPosting.config_id == config_id)
    if status:
        stmt = stmt.where(JobPosting.status == status)
    if source:
        stmt = stmt.where(JobPosting.source == source)
    if since_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        stmt = stmt.where(JobPosting.first_seen_at >= cutoff)
    if h1b_only:
        min_tier = h1b_min_tier if h1b_min_tier is not None else 1
        stmt = stmt.where(JobPosting.sponsor_tier >= min_tier)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                JobPosting.job_title.ilike(like),
                JobPosting.company.ilike(like),
                JobPosting.description_snippet.ilike(like),
            )
        )
    stmt = stmt.order_by(desc(JobPosting.first_seen_at)).limit(limit).offset(offset)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.patch("/postings/{posting_id}", response_model=PostingOut)
async def update_posting(
    posting_id: str,
    payload: PostingPatch,
    db: AsyncSession = Depends(get_db),
):
    posting = await db.get(JobPosting, posting_id)
    if not posting:
        raise HTTPException(404, "Posting not found")
    if payload.status:
        if payload.status not in ("new", "seen", "dismissed"):
            raise HTTPException(400, "status must be new|seen|dismissed (Apply uses /apply endpoint)")
        posting.status = payload.status
    await db.commit()
    await db.refresh(posting)
    return posting


@router.post("/postings/{posting_id}/apply")
async def apply_to_posting(posting_id: str):
    """Promote a posting to a JobApplication and fire the resume review loop."""
    result = await promote_to_application(posting_id)
    if result.get("status") == "missing":
        raise HTTPException(404, "Posting not found")
    return result


# ─── Sources / boards ────────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources():
    """Registry metadata used by the config UI."""
    reg = build_default_registry()
    return [
        {
            "name": a.name,
            "supports_server_search": a.supports_server_search,
            "needs_board_token": a.name in PER_BOARD_SOURCES,
        }
        for a in reg.values()
    ]


@router.get("/boards", response_model=list[CompanyBoardOut])
async def list_boards(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(CompanyBoard).order_by(CompanyBoard.company_name))
    return res.scalars().all()


@router.post("/boards", response_model=CompanyBoardOut)
async def create_board(payload: CompanyBoardIn, db: AsyncSession = Depends(get_db)):
    if payload.source not in PER_BOARD_SOURCES:
        raise HTTPException(400, f"source must be one of {list(PER_BOARD_SOURCES)}")
    board = CompanyBoard(**payload.model_dump())
    db.add(board)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(409, f"Board already exists for that source/token: {e}")
    await db.refresh(board)
    return board


@router.patch("/boards/{board_id}", response_model=CompanyBoardOut)
async def update_board(board_id: str, payload: CompanyBoardIn, db: AsyncSession = Depends(get_db)):
    board = await db.get(CompanyBoard, board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    for k, v in payload.model_dump().items():
        setattr(board, k, v)
    await db.commit()
    await db.refresh(board)
    return board


@router.delete("/boards/{board_id}")
async def delete_board(board_id: str, db: AsyncSession = Depends(get_db)):
    board = await db.get(CompanyBoard, board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    await db.delete(board)
    await db.commit()
    return {"deleted": True}


# ─── H-1B sponsor data ──────────────────────────────────────────────────────

@router.get("/h1b/stats")
async def h1b_stats(db: AsyncSession = Depends(get_db)):
    """Quick health stats for the sponsor table."""
    total = await db.execute(select(func.count()).select_from(H1bSponsor))
    by_fy = await db.execute(
        select(H1bSponsor.fiscal_year, func.count())
        .group_by(H1bSponsor.fiscal_year)
        .order_by(H1bSponsor.fiscal_year.desc())
    )
    return {
        "total_rows": int(total.scalar() or 0),
        "by_fiscal_year": [{"fiscal_year": r[0], "count": r[1]} for r in by_fy.all()],
        "default_sources": DEFAULT_USCIS_SOURCES,
    }


class H1bRefreshIn(BaseModel):
    url: str | None = None
    fiscal_year: int | None = None


@router.post("/h1b/refresh")
async def h1b_refresh(
    payload: H1bRefreshIn,
    background_tasks: BackgroundTasks,
):
    """Refresh USCIS sponsor data.

    With no body: re-fetches the canonical FY22-FY24 sources in the background.
    With {url, fiscal_year}: loads a single CSV inline and returns its summary
    (including detailed error info if the URL is wrong / 404 / HTML page).
    """
    if payload.url and payload.fiscal_year:
        return await load_uscis_csv(payload.url, payload.fiscal_year)
    background_tasks.add_task(refresh_uscis_default)
    return {"status": "queued", "sources": DEFAULT_USCIS_SOURCES}


@router.post("/h1b/upload")
async def h1b_upload(
    fiscal_year: int = Form(...),
    file: UploadFile = File(...),
):
    """Upload a USCIS Employer Data Hub CSV directly.

    Use this when the URL refresh fails — USCIS rotates file URLs and the
    backend may be behind a network that can't reach uscis.gov. Download the
    .csv from
        https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
    and POST it as multipart form-data with `fiscal_year` (e.g. 2024) and
    `file` (the .csv or .csv.zip).
    """
    body = await file.read()
    if not body:
        raise HTTPException(400, "uploaded file is empty")
    label = f"upload:{file.filename or 'unknown'}"
    return await load_uscis_bytes(body, fiscal_year=fiscal_year, source_label=label)
