"""Evolve routes — self-improving platform agent API."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.evolve import EvolveRun, EvolveSuggestion, SuggestionStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evolve", tags=["evolve"])


@router.get("/suggestions")
async def list_suggestions(
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(EvolveSuggestion)
    if status:
        query = query.where(EvolveSuggestion.status == status)
    if category:
        query = query.where(EvolveSuggestion.category == category)
    if priority:
        query = query.where(EvolveSuggestion.priority == priority)
    query = query.order_by(EvolveSuggestion.created_at.desc()).limit(limit)
    result = await db.execute(query)
    suggestions = result.scalars().all()
    return [_suggestion_to_dict(s) for s in suggestions]


@router.get("/suggestions/{suggestion_id}")
async def get_suggestion(suggestion_id: str, db: AsyncSession = Depends(get_db)):
    suggestion = await db.get(EvolveSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return _suggestion_to_dict(suggestion)


@router.post("/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, db: AsyncSession = Depends(get_db)):
    suggestion = await db.get(EvolveSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status not in (SuggestionStatus.proposed.value, SuggestionStatus.pending_approval.value):
        raise HTTPException(status_code=400, detail=f"Cannot dismiss suggestion in status {suggestion.status}")
    suggestion.status = SuggestionStatus.dismissed.value
    await db.commit()
    return _suggestion_to_dict(suggestion)


@router.get("/runs")
async def list_runs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EvolveRun).order_by(EvolveRun.created_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [_run_to_dict(r) for r in runs]


@router.post("/trigger/{run_type}")
async def trigger_run(run_type: str):
    if run_type not in ("daily_analysis", "competitor_monitor"):
        raise HTTPException(status_code=400, detail="run_type must be daily_analysis or competitor_monitor")

    import asyncio
    from app.core.evolve_service import run_daily_analysis, run_competitor_monitor

    if run_type == "daily_analysis":
        run = await run_daily_analysis()
    else:
        run = await run_competitor_monitor()

    return _run_to_dict(run)


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db)):
    # Suggestion counts by status
    status_result = await db.execute(
        select(EvolveSuggestion.status, func.count(EvolveSuggestion.id))
        .group_by(EvolveSuggestion.status)
    )
    status_counts = {row[0]: row[1] for row in status_result.all()}

    # Recent runs
    runs_result = await db.execute(
        select(EvolveRun).order_by(EvolveRun.created_at.desc()).limit(5)
    )
    recent_runs = [_run_to_dict(r) for r in runs_result.scalars().all()]

    # Competitor gap count
    gap_result = await db.execute(
        select(func.count(EvolveSuggestion.id)).where(
            EvolveSuggestion.category == "competitor_gap",
            EvolveSuggestion.status.in_(["proposed", "pending_approval"]),
        )
    )
    competitor_gaps = gap_result.scalar() or 0

    # Health score (simple: 100 - error_rate)
    health_score = 100
    try:
        from app.models.trace import ExecutionTrace
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        total_result = await db.execute(
            select(func.count(ExecutionTrace.id)).where(ExecutionTrace.created_at >= cutoff)
        )
        total = total_result.scalar() or 0
        error_result = await db.execute(
            select(func.count(ExecutionTrace.id)).where(
                ExecutionTrace.created_at >= cutoff,
                ExecutionTrace.had_error == True,
            )
        )
        error_count = error_result.scalar() or 0
        if total > 0:
            health_score = round(100 - (error_count / total * 100), 1)
    except Exception:
        pass

    return {
        "health_score": health_score,
        "suggestion_counts": status_counts,
        "total_suggestions": sum(status_counts.values()),
        "pending_count": status_counts.get("pending_approval", 0) + status_counts.get("proposed", 0),
        "approved_count": status_counts.get("approved", 0) + status_counts.get("completed", 0),
        "rejected_count": status_counts.get("rejected", 0) + status_counts.get("dismissed", 0),
        "competitor_gaps": competitor_gaps,
        "recent_runs": recent_runs,
    }


# ── Competitor Repos Management ───────────────────────────────────────────────


@router.get("/competitor-repos")
async def get_competitor_repos(db: AsyncSession = Depends(get_db)):
    """Get the list of monitored competitor GitHub repos."""
    from app.core.system_settings import sys_settings
    raw = sys_settings.get("evolve_competitor_repos")
    if not raw:
        from app.config import settings
        raw = settings.evolve_competitor_repos
    repos = [r.strip() for r in raw.split(",") if r.strip()]
    return {"repos": repos}


class CompetitorReposUpdate(BaseModel):
    repos: list[str]


@router.put("/competitor-repos")
async def update_competitor_repos(
    body: CompetitorReposUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the list of monitored competitor GitHub repos."""
    # Validate: each entry should look like owner/repo
    cleaned = []
    for repo in body.repos:
        repo = repo.strip().strip("/")
        # Strip full GitHub URLs down to owner/repo
        if "github.com/" in repo:
            repo = repo.split("github.com/")[-1]
        repo = repo.strip("/")
        if "/" not in repo or len(repo.split("/")) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid repo format: '{repo}'. Expected 'owner/repo'.",
            )
        cleaned.append(repo)

    from app.core.system_settings import sys_settings
    value = ",".join(cleaned)
    await sys_settings.update(db, {"evolve_competitor_repos": value})
    return {"repos": cleaned}


def _suggestion_to_dict(s: EvolveSuggestion) -> dict:
    return {
        "id": s.id,
        "evolve_agent_id": s.evolve_agent_id,
        "category": s.category,
        "source": s.source,
        "title": s.title,
        "description": s.description,
        "evidence": s.evidence,
        "priority": s.priority,
        "status": s.status,
        "approval_request_id": s.approval_request_id,
        "action_type": s.action_type,
        "action_config": s.action_config,
        "result_id": s.result_id,
        "result_type": s.result_type,
        "run_id": s.run_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _run_to_dict(r: EvolveRun) -> dict:
    return {
        "id": r.id,
        "run_type": r.run_type,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "status": r.status,
        "stats": r.stats,
        "error_log": r.error_log,
        "suggestions_generated": r.suggestions_generated,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
