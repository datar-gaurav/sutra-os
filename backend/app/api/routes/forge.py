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

    req.status = ForgeStatus.coding.value
    await db.commit()
    await db.refresh(req)

    # Run coding in background
    asyncio.create_task(_run_coding(req.id))

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

    rounds = list(req.plan_feedback or [])
    rounds.append({
        "round": len(rounds) + 1,
        "feedback": payload.feedback,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    req.plan_feedback = rounds
    req.status = ForgeStatus.planning.value
    await db.commit()
    await db.refresh(req)

    asyncio.create_task(_run_planning(
        req.id, req.repo_url,
        f"{req.description}\n\nUser feedback: {payload.feedback}",
        req.workspace_path or "",
        req.branch_name or "",
        req.llm_provider, req.llm_model, req.auto_approve_plan,
    ))

    _broadcast(req.id, req.status)
    return req


@router.post("/{forge_id}/cancel", response_model=ForgeRequestResponse)
async def cancel_forge(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a forge request and clean up the workspace."""
    from app.core.forge_engine import cleanup_workspace
    from pathlib import Path

    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")

    req.status = ForgeStatus.cancelled.value
    await db.commit()
    await db.refresh(req)

    if req.workspace_path:
        cleanup_workspace(Path(req.workspace_path))

    _broadcast(req.id, req.status)
    return req


@router.delete("/{forge_id}")
async def delete_forge_request(
    forge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a forge request and clean up its workspace."""
    from app.core.forge_engine import cleanup_workspace
    from pathlib import Path

    req = await db.get(ForgeRequest, forge_id)
    if not req:
        raise HTTPException(status_code=404, detail="ForgeRequest not found")

    if req.workspace_path:
        cleanup_workspace(Path(req.workspace_path))

    await db.delete(req)
    await db.commit()
    return {"ok": True, "id": forge_id}


@router.get("/config/settings")
async def get_forge_config(current_user: User = Depends(get_current_user)):
    """Return forge configuration."""
    from app.config import settings
    return {
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


# ─── Background task helpers ──────────────────────────────────────────────────


async def _run_planning(
    forge_id: str, repo_url: str, description: str, workspace_path: str, branch: str,
    llm_provider: str, llm_model: str, auto_approve_plan: bool,
) -> None:
    """Background: clone (if needed) + generate plan."""
    from app.db.session import async_session_factory
    from app.core.forge_engine import clone_repo, create_branch, generate_plan, workspace_for
    from pathlib import Path

    try:
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return

            ws = Path(workspace_path) if workspace_path else workspace_for(forge_id)

            # Clone only if workspace doesn't exist yet
            if not ws.exists():
                try:
                    await clone_repo(repo_url, ws)
                    await create_branch(ws, branch)
                    _append_log(req, "log", "Repo cloned, branch created.")
                except Exception as e:
                    req.status = ForgeStatus.failed.value
                    req.error_log = str(e)
                    await db.commit()
                    _broadcast(forge_id, req.status)
                    return

            try:
                plan = await generate_plan(repo_url, description, ws, llm_provider, llm_model)
                req.plan = plan
                _append_log(req, "log", f"Plan ready: {plan.get('summary', '')}")

                if auto_approve_plan:
                    req.status = ForgeStatus.coding.value
                    _append_log(req, "log", "Auto-approved plan, starting coding...")
                    await db.commit()
                    _broadcast(forge_id, req.status)
                    asyncio.create_task(_run_coding(forge_id))
                    return
                else:
                    req.status = ForgeStatus.awaiting_plan_approval.value
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)

            await db.commit()
            _broadcast(forge_id, req.status)
    except Exception as e:
        logger.error(f"[Forge] _run_planning crashed for {forge_id}: {e}")
        try:
            async with async_session_factory() as db:
                req = await db.get(ForgeRequest, forge_id)
                if req and req.status == ForgeStatus.planning.value:
                    req.status = ForgeStatus.failed.value
                    req.error_log = f"Planning crashed: {e}"
                    await db.commit()
                    _broadcast(forge_id, req.status)
        except Exception:
            pass


async def _run_coding(forge_id: str) -> None:
    """Background: execute coding plan, run tests, commit, push, open PR."""
    from app.db.session import async_session_factory
    from app.core.forge_engine import (
        run_coding, detect_and_run_tests,
        commit_all, push_branch, workspace_for, _get_semaphore,
    )
    from pathlib import Path

    semaphore = _get_semaphore()
    async with semaphore:
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return
            ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
            provider = req.llm_provider
            model = req.llm_model
            plan = req.plan
            desc = req.description
            branch = req.branch_name

        log_entries = list(req.coding_log or [])
        error_msg = None

        async for event in run_coding(ws, plan, desc, provider, model):
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event["event"],
                "message": event["message"],
            }
            log_entries.append(entry)

            async with async_session_factory() as db:
                req2 = await db.get(ForgeRequest, forge_id)
                if req2:
                    req2.coding_log = log_entries
                    await db.commit()

            if event["event"] == "error":
                error_msg = event["message"]
                break

    async with async_session_factory() as db:
        req3 = await db.get(ForgeRequest, forge_id)
        if not req3:
            return
        if error_msg:
            req3.status = ForgeStatus.failed.value
            req3.error_log = error_msg
            await db.commit()
            _broadcast(forge_id, req3.status)
            return

        # Run tests
        req3.status = ForgeStatus.testing.value
        _append_log(req3, "log", "Running tests...")
        await db.commit()
        _broadcast(forge_id, req3.status)

    try:
        test_results = await detect_and_run_tests(ws)
    except Exception as e:
        test_results = {"framework": "error", "exit_code": -1, "stderr": str(e)}

    async with async_session_factory() as db:
        req4 = await db.get(ForgeRequest, forge_id)
        if not req4:
            return
        req4.test_results = test_results
        fw = test_results.get("framework", "none")
        ec = test_results.get("exit_code")
        if fw == "none":
            _append_log(req4, "log", "No test framework detected.")
        else:
            passed = test_results.get("passed")
            failed = test_results.get("failed")
            summary_parts = [f"framework={fw}", f"exit_code={ec}"]
            if passed is not None:
                summary_parts.append(f"passed={passed}")
            if failed is not None:
                summary_parts.append(f"failed={failed}")
            _append_log(req4, "log", f"Tests finished: {', '.join(summary_parts)}")

        # Commit + push + open PR
        try:
            plan_summary = (req4.plan or {}).get("summary", req4.title)
            await commit_all(ws, f"feat: {plan_summary}\n\nGenerated by Sutra Forge")
            await push_branch(ws, branch)

            from github import Github
            from app.config import settings
            gh = Github(settings.github_token)
            repo = gh.get_repo(req4.repo_url)

            # Build PR body with test results
            test_section = ""
            if fw != "none" and fw != "error":
                test_section = f"\n\n## Test Results\n- Framework: {fw}\n- Exit code: {ec}"
                if passed is not None:
                    test_section += f"\n- Passed: {passed}"
                if failed is not None:
                    test_section += f"\n- Failed: {failed}"
                skipped = test_results.get("skipped")
                if skipped is not None:
                    test_section += f"\n- Skipped: {skipped}"

            pr_body = (
                f"## Summary\n{plan_summary}\n\n"
                f"**Feature request:**\n{req4.description}"
                f"{test_section}\n\n"
                f"---\n🤖 Generated by Sutra Forge"
            )
            pr = repo.create_pull(
                title=f"feat: {req4.title}",
                body=pr_body,
                head=branch,
                base=repo.default_branch,
            )
            req4.pr_url = pr.html_url
            req4.pr_number = pr.number
            req4.status = ForgeStatus.completed.value
            _append_log(req4, "log", f"PR #{pr.number} created: {pr.html_url}")
        except Exception as e:
            req4.status = ForgeStatus.failed.value
            req4.error_log = str(e)

        await db.commit()
        _broadcast(forge_id, req4.status)


def _append_log(req, event: str, message: str) -> None:
    from datetime import datetime, timezone
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "message": message,
    }
    req.coding_log = list(req.coding_log or []) + [entry]


def _broadcast(forge_id: str, status: str) -> None:
    async def _do():
        try:
            from app.api.websocket import ws_manager
            await ws_manager.broadcast({"type": "forge_update", "forge_request_id": forge_id, "status": status})
        except Exception:
            pass
    try:
        asyncio.create_task(_do())
    except Exception:
        pass
