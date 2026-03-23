"""Goals, Check-ins, and Initiatives API."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.checkin import AgentCheckIn
from app.models.goal import AgentGoal, GoalStatus
from app.models.initiative import AgentInitiative, InitiativeStatus
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["goals"])


# ─── Goals ────────────────────────────────────────────────────────────────────

@router.get("/goals/")
async def list_goals(
    agent_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentGoal).order_by(AgentGoal.created_at.desc())
    if agent_id:
        q = q.where(AgentGoal.agent_id == agent_id)
    if status:
        q = q.where(AgentGoal.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/goals/", status_code=201)
async def create_goal(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    goal = AgentGoal(
        agent_id=data["agent_id"],
        title=data["title"],
        description=data.get("description"),
        priority=data.get("priority", "medium"),
        deadline=data.get("deadline"),
        success_criteria=data.get("success_criteria"),
        created_by_user_id=current_user.id,
    )
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


@router.get("/goals/{goal_id}")
async def get_goal(goal_id: str, db: AsyncSession = Depends(get_db)):
    goal = await db.get(AgentGoal, goal_id)
    if not goal:
        raise HTTPException(404, "Goal not found")
    return goal


@router.put("/goals/{goal_id}")
async def update_goal(goal_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    goal = await db.get(AgentGoal, goal_id)
    if not goal:
        raise HTTPException(404, "Goal not found")
    for field in ("title", "description", "status", "priority", "deadline",
                  "success_criteria"):
        if field in data:
            setattr(goal, field, data[field])
    await db.flush()
    await db.refresh(goal)
    return goal


@router.post("/goals/{goal_id}/progress")
async def add_progress_note(goal_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Append a progress note to a goal."""
    goal = await db.get(AgentGoal, goal_id)
    if not goal:
        raise HTTPException(404, "Goal not found")
    note = {
        "note": data.get("note", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    goal.progress_notes = list(goal.progress_notes or []) + [note]
    await db.flush()
    await db.refresh(goal)
    return goal


@router.delete("/goals/{goal_id}", status_code=204)
async def delete_goal(goal_id: str, db: AsyncSession = Depends(get_db)):
    goal = await db.get(AgentGoal, goal_id)
    if not goal:
        raise HTTPException(404, "Goal not found")
    await db.delete(goal)
    await db.flush()


# ─── Check-ins ────────────────────────────────────────────────────────────────

@router.get("/checkins/")
async def list_checkins(
    agent_id: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentCheckIn).order_by(desc(AgentCheckIn.created_at)).limit(limit)
    if agent_id:
        q = q.where(AgentCheckIn.agent_id == agent_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/checkins/run/{agent_id}")
async def run_checkin(
    agent_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual check-in for an agent. Runs in background."""
    agent = await db.get(__import__("app.models.agent", fromlist=["Agent"]).Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    async def _do_checkin():
        try:
            from app.core.goal_engine import run_checkin as _run
            await _run(agent_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background check-in failed: {e}")

    background_tasks.add_task(_do_checkin)
    return {"message": f"Check-in started for agent {agent_id}"}


@router.get("/checkins/{checkin_id}")
async def get_checkin(checkin_id: str, db: AsyncSession = Depends(get_db)):
    checkin = await db.get(AgentCheckIn, checkin_id)
    if not checkin:
        raise HTTPException(404, "Check-in not found")
    return checkin


@router.delete("/checkins/{checkin_id}", status_code=204)
async def delete_checkin(
    checkin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    checkin = await db.get(AgentCheckIn, checkin_id)
    if not checkin:
        raise HTTPException(404, "Check-in not found")
    await db.delete(checkin)
    await db.flush()


# ─── Initiatives ──────────────────────────────────────────────────────────────

@router.get("/initiatives/")
async def list_initiatives(
    status: str | None = None,
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentInitiative).order_by(desc(AgentInitiative.created_at))
    if status:
        q = q.where(AgentInitiative.status == status)
    if agent_id:
        q = q.where(AgentInitiative.agent_id == agent_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/initiatives/", status_code=201)
async def create_initiative(data: dict, db: AsyncSession = Depends(get_db)):
    """Manually create an initiative (agents create them during check-ins)."""
    initiative = AgentInitiative(
        agent_id=data["agent_id"],
        title=data["title"],
        description=data.get("description"),
        rationale=data.get("rationale"),
        proposed_actions=data.get("proposed_actions", []),
        estimated_impact=data.get("estimated_impact"),
    )
    db.add(initiative)
    await db.flush()
    await db.refresh(initiative)
    return initiative


@router.post("/initiatives/{initiative_id}/approve")
async def approve_initiative(
    initiative_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initiative = await db.get(AgentInitiative, initiative_id)
    if not initiative:
        raise HTTPException(404, "Initiative not found")
    note = (payload or {}).get("note", "") or ""
    initiative.status = InitiativeStatus.approved.value
    initiative.reviewed_by_user_id = current_user.id
    initiative.reviewer_note = note or None
    initiative.reviewed_at = datetime.now(timezone.utc).isoformat()
    await db.flush()

    # Auto-create tasks from proposed_actions
    from app.models.task import Task, TaskPriority, TaskStatus
    created_task_ids = []
    for i, action_text in enumerate(initiative.proposed_actions or []):
        if not action_text:
            continue
        task = Task(
            title=str(action_text)[:500],
            description=f"Auto-created from approved initiative: {initiative.title}",
            status=TaskStatus.todo.value,
            priority=TaskPriority.medium.value,
            assignee_agent_id=initiative.agent_id,
        )
        db.add(task)
        await db.flush()
        created_task_ids.append(task.id)

    await db.commit()
    await db.refresh(initiative)

    # Notify UI
    try:
        from app.api.websocket import ws_manager
        import asyncio
        asyncio.create_task(ws_manager.broadcast({
            "type": "initiative_approved",
            "initiative_id": initiative_id,
            "agent_id": initiative.agent_id,
            "tasks_created": len(created_task_ids),
        }))
    except Exception:
        pass

    return {**initiative.__dict__, "tasks_created": created_task_ids}


@router.post("/initiatives/{initiative_id}/reject")
async def reject_initiative(
    initiative_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initiative = await db.get(AgentInitiative, initiative_id)
    if not initiative:
        raise HTTPException(404, "Initiative not found")
    note = (payload or {}).get("note", "") or ""
    initiative.status = InitiativeStatus.rejected.value
    initiative.reviewed_by_user_id = current_user.id
    initiative.reviewer_note = note or None
    initiative.reviewed_at = datetime.now(timezone.utc).isoformat()
    await db.flush()
    await db.refresh(initiative)
    return initiative


@router.delete("/initiatives/{initiative_id}", status_code=204)
async def delete_initiative(
    initiative_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    initiative = await db.get(AgentInitiative, initiative_id)
    if not initiative:
        raise HTTPException(404, "Initiative not found")
    await db.delete(initiative)
    await db.flush()


@router.put("/initiatives/{initiative_id}")
async def update_initiative(initiative_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    initiative = await db.get(AgentInitiative, initiative_id)
    if not initiative:
        raise HTTPException(404, "Initiative not found")
    for field in ("title", "description", "rationale", "proposed_actions",
                  "estimated_impact", "status"):
        if field in data:
            setattr(initiative, field, data[field])
    await db.flush()
    await db.refresh(initiative)
    return initiative
