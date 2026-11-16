"""Forge routes — manage and stream ForgeRequests."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.code_executor import (
    CodeExecutorUnavailable,
    broadcast_forge as _broadcast,
    cancel_everywhere,
    get_executor,
)
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.forge import ForgeRequest, ForgeStatus
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/forge", tags=["forge"])


# ─── Schemas ──────────────────────────────────────────────────────────────────


class ForgeCreateRequest(BaseModel):
    repo_url: str
    description: str
    llm_provider: str = "groq"
    llm_model: str = "qwen/qwen3-32b"
    auto_approve_plan: bool = False


class ForgePlanFeedback(BaseModel):
    feedback: str = ""


class ForgeRequestResponse(BaseModel):
    id: str
    title: str
    description: str
    repo_url: str
    branch_name: str | None
    llm_provider: str
    llm_model: str
    auto_approve_plan: bool
    status: str
    queue_position: int | None = None  # populated by list endpoint for queued items
    plan: dict | None
    plan_feedback: list | None
    pr_url: str | None
    pr_number: int | None
    coding_log: list | None
    test_results: dict | None
    error_log: str | None
    source_channel: str
    creator_user_id: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[ForgeRequestResponse])
async def list_forge_requests(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all forge requests, optionally filtered by status."""
    q = select(ForgeRequest).order_by(ForgeRequest.created_at.desc())
    if status:
        q = q.where(ForgeRequest.status == status)
    result = await db.execute(q)
    rows = result.scalars().all()

    # Annotate queue_position for queued items (1 = next to run)
    queued = sorted(
        [r for r in rows if r.status == ForgeStatus.queued.value],
        key=lambda r: r.created_at,
    )
    position_map = {r.id: i + 1 for i, r in enumerate(queued)}

    out = []
    for r in rows:
        resp = ForgeRequestResponse.model_validate(r)
        resp.queue_position = position_map.get(r.id)
        out.append(resp)
    return out


@router.post("/", response_model=ForgeRequestResponse)
async def create_forge_request(
    payload: ForgeCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new forge request and add it to the queue.

    Requests are executed one-by-one by the nightly Forge queue runner
    (default: 7 PM PST daily via FORGE_QUEUE_CRON).  They are NOT started
    immediately so that the queue is always processed in order.
    """
    from app.core.forge_engine import make_branch_name, workspace_for

    req = ForgeRequest(
        title=payload.description[:80],
        description=payload.description,
        repo_url=payload.repo_url,
        llm_provider=payload.llm_provider,
        llm_model=payload.llm_model,
        auto_approve_plan=payload.auto_approve_plan,
        status=ForgeStatus.queued.value,   # ← wait in queue, not planning
        source_channel="ui",
        creator_user_id=current_user.id,
        coding_log=[],
        plan_feedback=[],
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)

    branch = make_branch_name(payload.description, req.id)
    workspace = workspace_for(req.id)
    req.branch_name = branch
    req.workspace_path = str(workspace)

    await db.commit()
    await db.refresh(req)

    # Tell the UI something was enqueued
    _broadcast(req.id, req.status)

    resp = ForgeRequestResponse.model_validate(req)
    # Calculate queue position (this request is always last in the queue)
    result = await db.execute(
        select(ForgeRequest)
        .where(ForgeRequest.status == ForgeStatus.queued.value)
        .order_by(ForgeRequest.created_at)
    )
    queued_ids = [r.id for r in result.scalars().all()]
    resp.queue_position = queued_ids.index(req.id) + 1 if req.id in queued_ids else None
    return resp


@router.get("/{forge_id}", response_model=ForgeRequestResponse)
async def get_forge_request(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")
    return req


@router.get("/{forge_id}/stream")
async def stream_forge_log(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE stream of coding_log entries for a forge request (tails as new entries appear)."""

    async def event_generator():
        last_len = 0
        for _ in range(600):  # max ~10 minutes at 1s interval
            async with db.begin_nested():
                req = await db.get(ForgeRequest, forge_id)
            if not req:
                yield f"event: error\ndata: {json.dumps({'message': 'not found'})}\n\n"
                return

            log = req.coding_log or []
            new_entries = log[last_len:]
            for entry in new_entries:
                yield f"event: log\ndata: {json.dumps(entry)}\n\n"
            last_len = len(log)

            # Terminal states — send final status and close
            if req.status in (
                ForgeStatus.completed.value,
                ForgeStatus.failed.value,
                ForgeStatus.cancelled.value,
                ForgeStatus.pr_created.value,
            ):
                yield f"event: status\ndata: {json.dumps({'status': req.status, 'pr_url': req.pr_url})}\n\n"
                return

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/{forge_id}/approve-plan", response_model=ForgeRequestResponse)
async def approve_plan(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve the implementation plan and trigger coding execution."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")
    if req.status != ForgeStatus.awaiting_plan_approval.value:
        raise HTTPException(status_code=400, detail=f"Request is in status '{req.status}', expected awaiting_plan_approval")
    executor = _plan_reviewing_executor()

    req.status = ForgeStatus.coding.value
    await db.commit()
    await db.refresh(req)

    await _run(executor.execute(req.id))
    _broadcast(req.id, req.status)
    return req


@router.post("/{forge_id}/request-changes", response_model=ForgeRequestResponse)
async def request_plan_changes(
    forge_id: str,
    payload: ForgePlanFeedback,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Provide feedback on the plan; re-generates the plan incorporating feedback."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")
    executor = _plan_reviewing_executor()

    rounds = list(req.plan_feedback or [])
    rounds.append({
        "round": len(rounds) + 1,
        "feedback": payload.feedback,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    req.plan_feedback = rounds
    await db.commit()

    await _run(executor.start(req.id, feedback=payload.feedback))
    await db.refresh(req)
    return req


@router.post("/{forge_id}/cancel", response_model=ForgeRequestResponse)
async def cancel_forge(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a forge request wherever it runs (local workspace, Shakha job)."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")

    req.status = ForgeStatus.cancelled.value
    await db.commit()
    await db.refresh(req)

    await cancel_everywhere(req.id)
    _broadcast(req.id, req.status)
    return req


@router.delete("/{forge_id}")
async def delete_forge_request(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a forge request, stopping any work it still has running."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")

    await cancel_everywhere(req.id)

    await db.delete(req)
    await db.commit()
    return {"ok": True, "id": forge_id}


@router.get("/config/settings")
async def get_forge_config(current_user: User = Depends(get_current_user)):
    """Return forge configuration."""
    from app.config import settings
    executor = get_executor()
    ok, reason = executor.availability()
    return {
        "executor": executor.name,
        "executor_available": ok,
        "executor_reason": reason,
        # False → hide Approve / Request changes: the executor reviews plans itself
        "reviews_plan": executor.reviews_plan,
        "max_concurrent": settings.forge_max_concurrent,
        "default_provider": settings.forge_default_provider,
        "default_model": settings.forge_default_model,
        "workspace_root": settings.forge_workspace_root,
    }


@router.post("/{forge_id}/retry", response_model=ForgeRequestResponse)
async def retry_forge(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-queue a failed / stuck forge request (it will run on the next queue flush)."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")
    if req.status not in (ForgeStatus.planning.value, ForgeStatus.failed.value, ForgeStatus.queued.value):
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry requests in planning, queued, or failed status, got '{req.status}'",
        )

    req.status = ForgeStatus.queued.value   # back to queue, not immediate
    req.error_log = None
    await db.commit()
    await db.refresh(req)

    _broadcast(req.id, req.status)
    return req


@router.post("/{forge_id}/run-now", response_model=ForgeRequestResponse)
async def run_forge_now(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Immediately start planning for a queued or failed forge request, bypassing the schedule."""
    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")
    if req.status not in (ForgeStatus.queued.value, ForgeStatus.failed.value):
        raise HTTPException(
            status_code=400,
            detail=f"Can only run queued or failed requests immediately, got '{req.status}'",
        )

    await _run(get_executor().start(req.id))
    await db.refresh(req)
    return req


# ─── Executor helpers ─────────────────────────────────────────────────────────


async def _run(coro):
    """Await an executor call, turning 'unavailable' into a 503."""
    try:
        return await coro
    except CodeExecutorUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))


def _plan_reviewing_executor():
    executor = get_executor()
    if not executor.reviews_plan:
        raise HTTPException(
            status_code=409,
            detail=f"The {executor.name} executor reviews plans itself; approve or give feedback there.",
        )
    return executor
