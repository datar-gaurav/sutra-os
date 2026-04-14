"""Job application tracking API — dashboard backend for LinkedIn captures."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory, get_db
from app.models.job_application import JOB_STATUSES, JobApplication
from app.models.trigger import AgentTrigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/job-applications", tags=["job-applications"])
public_router = APIRouter(prefix="/job-applications", tags=["job-applications-public"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class JobApplicationOut(BaseModel):
    id: str
    job_title: str
    company: str | None
    location: str | None
    salary: str | None
    job_description: str | None
    job_url: str | None
    source: str
    status: str
    notes: str | None
    tags: list
    resume_drive_url: str | None
    resume_drive_file_id: str | None
    analysis_drive_url: str | None
    fit_score: int | None
    review_rounds: int = 2
    review_log: list | None = None
    people: list | None = None
    applied_at: datetime | None
    last_status_change_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    tags: list | None = None
    resume_drive_url: str | None = None
    resume_drive_file_id: str | None = None
    analysis_drive_url: str | None = None
    fit_score: int | None = None
    review_rounds: int | None = None
    applied_at: datetime | None = None


class CapturePayload(BaseModel):
    job_title: str | None = None
    company: str | None = None
    location: str | None = None
    salary: str | None = None
    job_description: str | None = None
    job_url: str | None = None
    url: str | None = None  # extension sometimes sends `url`
    source: str | None = "linkedin"
    people: list | None = None
    review_rounds: int | None = None  # override default (2)


# ─── Public capture (Chrome extension) ────────────────────────────────────────

@public_router.post("/capture")
async def capture_job(
    payload: CapturePayload,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint hit by the Chrome extension. Creates a JobApplication row
    and fires the Resume Builder LinkedIn webhook trigger with the application id.
    """
    job_title = (payload.job_title or "").strip() or "Untitled role"
    company = (payload.company or "").strip() or None
    job_url = (payload.job_url or payload.url or "").strip() or None

    # Deduplicate by (company, job_title) — return existing row if present
    existing = None
    if company:
        result = await db.execute(
            select(JobApplication).where(
                JobApplication.company == company,
                JobApplication.job_title == job_title,
            )
        )
        existing = result.scalars().first()

    people = payload.people or []

    if existing:
        app_row = existing
        # Refresh data in case posting changed
        app_row.location = payload.location or app_row.location
        app_row.salary = payload.salary or app_row.salary
        app_row.job_description = payload.job_description or app_row.job_description
        app_row.job_url = job_url or app_row.job_url
        if people:
            app_row.people = people
        app_row.raw_payload = payload.model_dump()
    else:
        app_row = JobApplication(
            job_title=job_title,
            company=company,
            location=(payload.location or "").strip() or None,
            salary=(payload.salary or "").strip() or None,
            job_description=payload.job_description,
            job_url=job_url,
            source=payload.source or "linkedin",
            status="captured",
            people=people,
            review_rounds=payload.review_rounds if payload.review_rounds is not None else 2,
            raw_payload=payload.model_dump(),
        )
        db.add(app_row)

    await db.commit()
    await db.refresh(app_row)

    # Fire Resume Builder webhook trigger (if present + active)
    trig_result = await db.execute(
        select(AgentTrigger).where(
            AgentTrigger.trigger_type == "webhook",
            AgentTrigger.is_active == True,  # noqa: E712
            AgentTrigger.name == "LinkedIn Job Webhook",
        )
    )
    trigger = trig_result.scalars().first()

    if trigger:
        fire_payload = {
            "application_id": app_row.id,
            "job_title": app_row.job_title,
            "company": app_row.company,
            "location": app_row.location,
            "salary": app_row.salary,
            "job_description": app_row.job_description,
            "job_url": app_row.job_url,
        }
        app_id_captured = app_row.id

        async def _fire():
            try:
                from app.core.resume_review_loop import run_resume_review_loop
                await run_resume_review_loop(app_id_captured, fire_payload)
            except Exception as e:
                logger.exception(f"Resume review loop failed: {e}")
                # Fall back to the plain trigger so the user still gets a resume.
                try:
                    from app.core.goal_engine import fire_trigger
                    await fire_trigger(trigger.id, fire_payload)
                except Exception as e2:
                    logger.exception(f"Fallback trigger fire also failed: {e2}")

        background_tasks.add_task(_fire)

    return {
        "application_id": app_row.id,
        "status": app_row.status,
        "agent_fired": bool(trigger),
        "deduped": existing is not None,
    }


# ─── Authenticated CRUD ───────────────────────────────────────────────────────

@router.get("/", response_model=list[JobApplicationOut])
async def list_applications(
    status: str | None = Query(None),
    company: str | None = Query(None),
    search: str | None = Query(None),
    since_days: int | None = Query(None),
    limit: int = Query(500, le=2000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JobApplication)
    if status:
        stmt = stmt.where(JobApplication.status == status)
    if company:
        stmt = stmt.where(JobApplication.company.ilike(f"%{company}%"))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                JobApplication.job_title.ilike(like),
                JobApplication.company.ilike(like),
                JobApplication.job_description.ilike(like),
                JobApplication.notes.ilike(like),
            )
        )
    if since_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        stmt = stmt.where(JobApplication.created_at >= cutoff)
    stmt = stmt.order_by(desc(JobApplication.created_at)).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Aggregate stats for the dashboard."""
    # Status counts
    by_status_result = await db.execute(
        select(JobApplication.status, func.count()).group_by(JobApplication.status)
    )
    by_status = {row[0]: row[1] for row in by_status_result.all()}
    # Ensure all statuses present
    for s in JOB_STATUSES:
        by_status.setdefault(s, 0)

    total = sum(by_status.values())

    # This week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count()).where(JobApplication.created_at >= week_ago)
    )
    this_week = week_result.scalar() or 0

    # Top companies
    top_co_result = await db.execute(
        select(JobApplication.company, func.count().label("n"))
        .where(JobApplication.company.isnot(None))
        .group_by(JobApplication.company)
        .order_by(desc("n"))
        .limit(10)
    )
    top_companies = [{"company": r[0], "count": r[1]} for r in top_co_result.all()]

    # Daily sparkline (last 30 days)
    since = datetime.now(timezone.utc) - timedelta(days=30)
    daily_result = await db.execute(
        select(
            func.date(JobApplication.created_at).label("day"),
            func.count().label("n"),
        )
        .where(JobApplication.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    daily = [{"day": str(r[0]), "count": r[1]} for r in daily_result.all()]

    # Response / conversion
    applied_or_beyond = sum(
        by_status.get(s, 0) for s in ["applied", "interviewing", "offer", "rejected"]
    )
    interviewing_or_beyond = sum(
        by_status.get(s, 0) for s in ["interviewing", "offer"]
    )
    response_rate = (
        round(100.0 * interviewing_or_beyond / applied_or_beyond, 1)
        if applied_or_beyond
        else 0.0
    )

    return {
        "total": total,
        "this_week": this_week,
        "by_status": by_status,
        "top_companies": top_companies,
        "daily": daily,
        "response_rate": response_rate,
    }


@router.get("/{app_id}", response_model=JobApplicationOut)
async def get_application(app_id: str, db: AsyncSession = Depends(get_db)):
    app_row = await db.get(JobApplication, app_id)
    if not app_row:
        raise HTTPException(404, "Application not found")
    return app_row


@router.patch("/{app_id}", response_model=JobApplicationOut)
async def update_application(
    app_id: str,
    payload: JobApplicationUpdate,
    db: AsyncSession = Depends(get_db),
):
    app_row = await db.get(JobApplication, app_id)
    if not app_row:
        raise HTTPException(404, "Application not found")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        if data["status"] not in JOB_STATUSES:
            raise HTTPException(400, f"Invalid status. Must be one of {JOB_STATUSES}")
        if data["status"] != app_row.status:
            app_row.last_status_change_at = datetime.now(timezone.utc)
            if data["status"] == "applied" and not app_row.applied_at:
                app_row.applied_at = datetime.now(timezone.utc)

    for k, v in data.items():
        setattr(app_row, k, v)

    await db.commit()
    await db.refresh(app_row)
    return app_row


@router.delete("/{app_id}")
async def delete_application(app_id: str, db: AsyncSession = Depends(get_db)):
    app_row = await db.get(JobApplication, app_id)
    if not app_row:
        raise HTTPException(404, "Application not found")
    await db.delete(app_row)
    await db.commit()
    return {"deleted": True}


@router.get("/meta/statuses")
async def list_statuses():
    return {"statuses": JOB_STATUSES}


@router.post("/{app_id}/retry-review")
async def retry_review(
    app_id: str,
    background_tasks: BackgroundTasks,
    reset: bool = Query(False, description="Clear review_log before rerunning"),
    db: AsyncSession = Depends(get_db),
):
    """Rerun the resume build → critic → revise loop for an existing row.

    Useful when the initial run failed (rate limit, missing key, bad reply
    from a critic, etc.). If `reset=true`, the prior review_log is cleared
    so the new run starts fresh.
    """
    app_row = await db.get(JobApplication, app_id)
    if not app_row:
        raise HTTPException(404, "Application not found")

    if reset:
        app_row.review_log = []
        app_row.status = "captured"
        app_row.resume_drive_url = None
        app_row.resume_drive_file_id = None
        app_row.analysis_drive_url = None
        app_row.fit_score = None
        await db.commit()

    fire_payload = {
        "application_id": app_row.id,
        "job_title": app_row.job_title,
        "company": app_row.company,
        "location": app_row.location,
        "salary": app_row.salary,
        "job_description": app_row.job_description,
        "job_url": app_row.job_url,
    }

    async def _rerun():
        try:
            from app.core.resume_review_loop import run_resume_review_loop
            await run_resume_review_loop(app_id, fire_payload)
        except Exception as e:
            logger.exception(f"Retry review loop failed: {e}")

    background_tasks.add_task(_rerun)
    return {"status": "queued", "application_id": app_id, "reset": reset}


@router.get("/{app_id}/review-stream")
async def review_stream(app_id: str):
    """SSE stream of review-loop log entries as they are persisted.

    The loop writes each builder/critic turn to `review_log` in the DB.
    This endpoint polls the row every ~1.5s and emits new entries. Closes
    when status reaches 'resume_generated' and no new entries for ~10s.
    """
    async def gen():
        last_len = 0
        idle_ticks = 0
        # Initial hello so the client opens the connection immediately
        yield f"data: {json.dumps({'type': 'open', 'application_id': app_id})}\n\n"
        while True:
            async with async_session_factory() as db:
                row = await db.get(JobApplication, app_id)
                if not row:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'not found'})}\n\n"
                    return
                log = list(row.review_log or [])
                status = row.status
                review_rounds = row.review_rounds or 0

            if len(log) > last_len:
                for entry in log[last_len:]:
                    yield f"data: {json.dumps({'type': 'log', 'entry': entry})}\n\n"
                last_len = len(log)
                idle_ticks = 0
            else:
                idle_ticks += 1

            # Termination: resume generated AND we've seen at least the expected
            # number of entries (1 builder + 2*rounds) AND idle for ~10s.
            expected_min = 1 + 2 * review_rounds
            if (
                status == "resume_generated"
                and last_len >= expected_min
                and idle_ticks >= 6
            ):
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # Hard cap at 20 minutes so the connection never hangs forever
            if idle_ticks > 800:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                return

            await asyncio.sleep(1.5)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
