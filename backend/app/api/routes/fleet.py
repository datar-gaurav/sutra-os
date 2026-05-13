"""Fleet routes — UI endpoints (user-authed) + host-worker endpoints (bearer token)."""

import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.fleet import FleetJob, FleetStatus
from app.models.user import User
from app.core import fleet_orchestrator as fleet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fleet", tags=["fleet"])


# ─── Worker bearer auth (separate from user session auth) ─────────────────────


async def require_worker_token(authorization: str | None = Header(default=None)) -> str:
    """Validate the host-worker shared secret. Returns the worker_id header value."""
    expected = (settings.fleet_worker_token or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="fleet_worker_token not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    presented = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="invalid worker token")
    return "ok"


async def require_worker_id(x_worker_id: str | None = Header(default=None)) -> str:
    if not x_worker_id:
        raise HTTPException(status_code=400, detail="missing X-Worker-Id header")
    return x_worker_id


# ─── Schemas ──────────────────────────────────────────────────────────────────


class FleetJobResponse(BaseModel):
    id: str
    repo_url: str
    issue_ref: str | None
    title: str
    prompt: str
    branch_name: str | None
    status: str
    triage: dict | None
    decisions: list | None
    run_log: list | None
    claimed_by: str | None
    claimed_at: str | None
    pr_url: str | None
    pr_number: int | None
    error_log: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FleetCreateRequest(BaseModel):
    repo_url: str
    prompt: str
    title: str | None = None
    issue_ref: str | None = None


class LogBatch(BaseModel):
    lines: list[dict]   # [{stream, line, timestamp}]


class DecisionEntry(BaseModel):
    decision: str
    detail: str = ""


class StatusUpdate(BaseModel):
    status: str
    error: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None


# ─── UI endpoints (user-authed) ───────────────────────────────────────────────


@router.get("/", response_model=list[FleetJobResponse])
async def list_jobs(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(FleetJob).order_by(FleetJob.created_at.desc())
    if status:
        q = q.where(FleetJob.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.post("/", response_model=FleetJobResponse)
async def create_job(
    payload: FleetCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually enqueue a job — bypasses triage."""
    job = FleetJob(
        repo_url=payload.repo_url,
        issue_ref=payload.issue_ref,
        title=(payload.title or payload.prompt)[:200],
        prompt=payload.prompt,
        status=FleetStatus.queued.value,
        decisions=[],
        run_log=[],
        creator_user_id=current_user.id,
    )
    db.add(job)
    await db.flush()
    job.branch_name = fleet.make_branch_name(job.title, job.id)
    await db.commit()
    await db.refresh(job)

    from app.core.fleet_dispatcher import dispatch_to_host
    await dispatch_to_host(reason=f"manual-enqueued-{job.id[:8]}")

    return job


@router.post("/triage", response_model=FleetJobResponse | None)
async def trigger_triage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run one triage pass on demand (the scheduler also runs this hourly)."""
    return await fleet.triage_and_enqueue(db)


@router.get("/worker-health")
async def worker_health(current_user: User = Depends(get_current_user)):
    """Probe the host worker daemon. Used by the UI for the online badge."""
    from app.core.fleet_dispatcher import probe_host_worker
    return await probe_host_worker()


@router.post("/dispatch")
async def dispatch_now(current_user: User = Depends(get_current_user)):
    """Force-dispatch — UI button. Useful for poking the host after fixing it."""
    from app.core.fleet_dispatcher import dispatch_to_host
    ok = await dispatch_to_host(reason="manual-dispatch")
    return {"dispatched": ok}


@router.post("/{job_id}/cancel", response_model=FleetJobResponse)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await db.get(FleetJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="FleetJob not found")
    job.status = FleetStatus.cancelled.value
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently remove a fleet job row. Only allowed for terminal states so
    an in-flight worker can't be silently orphaned."""
    job = await db.get(FleetJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="FleetJob not found")
    terminal = {FleetStatus.pr_created.value, FleetStatus.failed.value, FleetStatus.cancelled.value}
    if job.status not in terminal:
        raise HTTPException(
            status_code=409,
            detail=f"cannot delete job in status '{job.status}' — cancel it first",
        )
    await db.delete(job)
    await db.commit()
    return {"ok": True}


# ─── Host worker endpoints (bearer auth) ──────────────────────────────────────


@router.post("/claim", response_model=FleetJobResponse | None)
async def worker_claim(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_worker_token),
    worker_id: str = Depends(require_worker_id),
):
    """Host worker pulls the next queued job (atomic claim). 204 if queue empty."""
    job = await fleet.claim_next_job(db, worker_id)
    return job  # None → FastAPI returns null; worker treats as "nothing to do"


@router.post("/{job_id}/logs")
async def worker_logs(
    job_id: str,
    batch: LogBatch,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_worker_token),
):
    await fleet.append_run_log(db, job_id, batch.lines)
    return {"ok": True}


@router.post("/{job_id}/decision")
async def worker_decision(
    job_id: str,
    entry: DecisionEntry,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_worker_token),
):
    await fleet.record_decision(db, job_id, entry.decision, entry.detail)
    return {"ok": True}


@router.post("/{job_id}/status", response_model=FleetJobResponse)
async def worker_status(
    job_id: str,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_worker_token),
):
    await fleet.update_status(
        db, job_id, payload.status,
        error=payload.error, pr_url=payload.pr_url, pr_number=payload.pr_number,
    )
    job = await db.get(FleetJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="FleetJob not found")
    return job


@router.get("/{job_id}", response_model=FleetJobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await db.get(FleetJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="FleetJob not found")
    return job
