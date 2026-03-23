"""Agent Triggers API — webhook / schedule / manual event triggers."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.trigger import AgentTrigger, TriggerType

router = APIRouter(prefix="/triggers", tags=["triggers"])


@router.get("/")
async def list_triggers(
    agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(AgentTrigger).order_by(AgentTrigger.created_at.desc())
    if agent_id:
        q = q.where(AgentTrigger.agent_id == agent_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", status_code=201)
async def create_trigger(data: dict, db: AsyncSession = Depends(get_db)):
    trigger = AgentTrigger(
        agent_id=data["agent_id"],
        name=data["name"],
        description=data.get("description"),
        trigger_type=data.get("trigger_type", TriggerType.manual.value),
        is_active=data.get("is_active", True),
        cron_expression=data.get("cron_expression"),
        prompt_template=data.get(
            "prompt_template",
            "You have been triggered. Please review your goals and report status.",
        ),
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)

    # If it's a schedule trigger, sync scheduler
    if trigger.trigger_type == TriggerType.schedule.value and trigger.cron_expression:
        from app.core.scheduler import sync_triggers
        import asyncio
        asyncio.create_task(sync_triggers())

    return trigger


@router.get("/{trigger_id}")
async def get_trigger(trigger_id: str, db: AsyncSession = Depends(get_db)):
    trigger = await db.get(AgentTrigger, trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    return trigger


@router.put("/{trigger_id}")
async def update_trigger(trigger_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    trigger = await db.get(AgentTrigger, trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    for field in ("name", "description", "trigger_type", "is_active",
                  "cron_expression", "prompt_template"):
        if field in data:
            setattr(trigger, field, data[field])
    await db.commit()
    await db.refresh(trigger)

    # Re-sync scheduler for schedule triggers
    from app.core.scheduler import sync_triggers
    import asyncio
    asyncio.create_task(sync_triggers())

    return trigger


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(trigger_id: str, db: AsyncSession = Depends(get_db)):
    trigger = await db.get(AgentTrigger, trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    await db.delete(trigger)
    await db.commit()

    # Remove from scheduler if scheduled
    from app.core.scheduler import scheduler
    job_id = f"trigger_{trigger_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


@router.post("/{trigger_id}/fire")
async def fire_trigger_manual(
    trigger_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Manually fire a trigger (authenticated)."""
    trigger = await db.get(AgentTrigger, trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found")

    payload = {}
    try:
        payload = await request.json()
    except Exception:
        pass

    async def _do_fire():
        from app.core.goal_engine import fire_trigger
        await fire_trigger(trigger_id, payload)

    background_tasks.add_task(_do_fire)
    return {"message": f"Trigger '{trigger.name}' fired"}


# ─── Public webhook endpoint (no auth — uses token) ──────────────────────────

public_router = APIRouter(prefix="/triggers", tags=["triggers-public"])


@public_router.post("/webhook/{token}")
async def webhook_fire(
    token: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public webhook endpoint. Fire trigger by token (no auth required)."""
    result = await db.execute(
        select(AgentTrigger).where(
            AgentTrigger.webhook_token == token,
            AgentTrigger.is_active == True,
            AgentTrigger.trigger_type == TriggerType.webhook.value,
        )
    )
    trigger = result.scalars().first()
    if not trigger:
        raise HTTPException(404, "Webhook not found or inactive")

    payload = {}
    try:
        payload = await request.json()
    except Exception:
        pass

    async def _do_fire():
        from app.core.goal_engine import fire_trigger
        await fire_trigger(trigger.id, payload)

    background_tasks.add_task(_do_fire)
    return {"received": True, "trigger": trigger.name}
