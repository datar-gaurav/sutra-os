"""Council API routes — CRUD + streaming execution."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import CouncilCreate, CouncilResponse
from app.core.audit import record_audit
from app.core.council_engine import council_engine
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.council import Council, CouncilStatus
from app.models.user import User

router = APIRouter(prefix="/councils", tags=["councils"])


@router.get("/", response_model=list[CouncilResponse])
async def list_councils(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Council)
    if status:
        query = query.where(Council.status == status)
    query = query.order_by(Council.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CouncilResponse, status_code=201)
async def create_council(
    payload: CouncilCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    council = Council(
        title=payload.title,
        question=payload.question,
        context=payload.context.model_dump() if payload.context else {},
        advisor_agent_ids=payload.advisor_agent_ids,
        arbitrator_agent_id=payload.arbitrator_agent_id,
        debate_mode=payload.debate_mode.value,
        role_assignments=payload.role_assignments or {},
        num_rounds=payload.num_rounds,
        created_by_user_id=current_user.id,
        messages=[],
    )
    db.add(council)
    await db.flush()
    await db.refresh(council)
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.id,
        action="create_council",
        resource_type="council",
        resource_id=council.id,
        details={"title": council.title, "num_rounds": council.num_rounds},
    )
    return council


@router.get("/{council_id}", response_model=CouncilResponse)
async def get_council(council_id: str, db: AsyncSession = Depends(get_db)):
    council = await db.get(Council, council_id)
    if not council:
        raise HTTPException(status_code=404, detail="Council not found")
    return council


@router.delete("/{council_id}", status_code=204)
async def delete_council(
    council_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    council = await db.get(Council, council_id)
    if not council:
        raise HTTPException(status_code=404, detail="Council not found")
    await db.delete(council)
    await record_audit(
        db,
        actor_type="user",
        actor_id=current_user.id,
        action="delete_council",
        resource_type="council",
        resource_id=council_id,
    )


@router.post("/{council_id}/run")
async def run_council(council_id: str, db: AsyncSession = Depends(get_db)):
    """Run (or restart) a council and stream events as SSE."""
    council = await db.get(Council, council_id)
    if not council:
        raise HTTPException(status_code=404, detail="Council not found")
    if council.status == CouncilStatus.active.value:
        raise HTTPException(status_code=400, detail="Council is already running")

    async def event_generator():
        async for event in council_engine.run(council_id):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{council_id}/reset", response_model=CouncilResponse)
async def reset_council(
    council_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a finished or failed council back to pending."""
    council = await db.get(Council, council_id)
    if not council:
        raise HTTPException(status_code=404, detail="Council not found")
    council.status = CouncilStatus.pending.value
    council.messages = []
    council.final_report = None
    council.concluded_at = None
    await db.flush()
    await db.refresh(council)
    return council
