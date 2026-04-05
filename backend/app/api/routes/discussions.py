"""Discussion API routes — CRUD + streaming execution."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    DiscussionCreate, DiscussionResponse, DiscussionUpdate,
)
from app.core.audit import record_audit
from app.core.discussion_engine import discussion_engine
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.discussion import Discussion, DiscussionStatus
from app.models.user import User

router = APIRouter(prefix="/discussions", tags=["discussions"])


@router.get("/", response_model=list[DiscussionResponse])
async def list_discussions(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Discussion)
    if status:
        query = query.where(Discussion.status == status)
    query = query.order_by(Discussion.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=DiscussionResponse, status_code=201)
async def create_discussion(
    payload: DiscussionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.participant_agent_ids:
        raise HTTPException(status_code=400, detail="At least one participant agent is required")

    discussion = Discussion(
        title=payload.title,
        topic=payload.topic,
        type=payload.type.value,
        participant_agent_ids=payload.participant_agent_ids,
        moderator_agent_id=payload.moderator_agent_id,
        max_rounds=payload.max_rounds,
        task_id=payload.task_id,
        created_by_user_id=current_user.id,
        messages=[],
    )
    db.add(discussion)
    await db.flush()
    await db.refresh(discussion)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="create_discussion", resource_type="discussion",
                       resource_id=discussion.id, details={"title": discussion.title})
    return discussion


@router.get("/{discussion_id}", response_model=DiscussionResponse)
async def get_discussion(discussion_id: str, db: AsyncSession = Depends(get_db)):
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    return discussion


@router.put("/{discussion_id}", response_model=DiscussionResponse)
async def update_discussion(
    discussion_id: str,
    payload: DiscussionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    if discussion.status == DiscussionStatus.active.value:
        raise HTTPException(status_code=400, detail="Cannot edit an active discussion")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(discussion, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    await db.refresh(discussion)
    return discussion


@router.delete("/{discussion_id}", status_code=204)
async def delete_discussion(
    discussion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    await db.delete(discussion)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="delete_discussion", resource_type="discussion",
                       resource_id=discussion_id)


@router.post("/{discussion_id}/run")
async def run_discussion(
    discussion_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Start/resume a discussion and stream events as SSE."""
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    if discussion.status == DiscussionStatus.concluded.value:
        raise HTTPException(status_code=400, detail="Discussion is already concluded")
    if discussion.status == DiscussionStatus.active.value:
        raise HTTPException(status_code=400, detail="Discussion is already running")

    async def event_generator():
        async for event in discussion_engine.run(discussion_id):
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


@router.post("/{discussion_id}/message", response_model=DiscussionResponse)
async def add_human_message(
    discussion_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a human message to a discussion (before running or between rounds)."""
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    if discussion.status == DiscussionStatus.active.value:
        raise HTTPException(status_code=400, detail="Cannot add messages while discussion is running")

    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")

    from datetime import datetime, timezone

    # Determine the current round from existing messages
    current_round = max((m.get("round", 0) for m in (discussion.messages or [])), default=0) or 1

    msg_entry = {
        "agent_id": f"user:{current_user.id}",
        "agent_name": current_user.username or current_user.email or "Human",
        "content": content,
        "round": current_round,
        "is_moderator": False,
        "is_human": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    messages = list(discussion.messages or [])
    messages.append(msg_entry)
    discussion.messages = messages
    await db.flush()
    await db.refresh(discussion)
    return discussion


@router.post("/{discussion_id}/reset", response_model=DiscussionResponse)
async def reset_discussion(
    discussion_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reset a failed or concluded discussion back to pending so it can be re-run."""
    discussion = await db.get(Discussion, discussion_id)
    if not discussion:
        raise HTTPException(status_code=404, detail="Discussion not found")
    discussion.status = DiscussionStatus.pending.value
    discussion.messages = []
    discussion.summary = None
    discussion.action_items = None
    discussion.concluded_at = None
    await db.flush()
    await db.refresh(discussion)
    return discussion
