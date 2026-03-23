"""Scheduling tools — allow agents to create and manage their own triggers."""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

SCHEDULING_TOOL_IDS = {
    "schedule_self",
    "list_my_triggers",
    "cancel_trigger",
}


def create_scheduling_tools(agent_id: str):
    """Create scheduling tools bound to a specific agent."""

    @tool
    async def schedule_self(
        name: str,
        cron_expression: str,
        prompt: str,
        description: str = "",
    ) -> str:
        """Create a scheduled trigger that will invoke you (this agent) on a cron schedule.

        This lets you autonomously schedule future check-ins, monitoring tasks,
        or recurring work without human intervention.

        Args:
            name: A descriptive name for the trigger (e.g., "Daily news summary").
            cron_expression: Standard cron (5-field): "minute hour day month weekday".
                Examples:
                  "0 9 * * *"    — every day at 9 AM
                  "*/30 * * * *" — every 30 minutes
                  "0 9 * * 1"    — every Monday at 9 AM
                  "0 */6 * * *"  — every 6 hours
            prompt: The message/instruction you'll receive when the trigger fires.
                    Supports {payload} placeholder for webhook data.
            description: Optional description of what this trigger does.

        Returns JSON with the trigger ID and details.
        """
        from app.db.session import async_session_factory
        from app.models.trigger import AgentTrigger

        try:
            async with async_session_factory() as db:
                trigger = AgentTrigger(
                    agent_id=agent_id,
                    name=name,
                    description=description or f"Self-scheduled by agent: {name}",
                    trigger_type="schedule",
                    cron_expression=cron_expression,
                    prompt_template=prompt,
                    is_active=True,
                )
                db.add(trigger)
                await db.commit()
                await db.refresh(trigger)

            # Sync scheduler so the new cron job is picked up immediately
            from app.core.scheduler import sync_triggers
            await sync_triggers()

            logger.info(
                f"Agent {agent_id} self-scheduled trigger {trigger.id}: "
                f"{name!r} cron={cron_expression}"
            )

            return json.dumps({
                "success": True,
                "trigger_id": trigger.id,
                "name": name,
                "cron": cron_expression,
                "prompt": prompt,
                "message": f"Trigger '{name}' created. You will be invoked on schedule: {cron_expression}.",
            })
        except Exception as e:
            logger.error(f"schedule_self error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def list_my_triggers(include_inactive: bool = False) -> str:
        """List all triggers configured for you (this agent).
        Returns each trigger's ID, name, type, cron, status, and fire count."""
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.trigger import AgentTrigger

        try:
            async with async_session_factory() as db:
                query = select(AgentTrigger).where(AgentTrigger.agent_id == agent_id)
                if not include_inactive:
                    query = query.where(AgentTrigger.is_active == True)  # noqa: E712
                result = await db.execute(query.order_by(AgentTrigger.created_at.desc()))
                triggers = result.scalars().all()

            return json.dumps({
                "triggers": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "type": t.trigger_type,
                        "cron": t.cron_expression,
                        "prompt": t.prompt_template[:100] + ("..." if len(t.prompt_template) > 100 else ""),
                        "is_active": t.is_active,
                        "fire_count": t.fire_count,
                        "last_fired_at": t.last_fired_at,
                    }
                    for t in triggers
                ],
                "total": len(triggers),
            })
        except Exception as e:
            logger.error(f"list_my_triggers error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def cancel_trigger(trigger_id: str) -> str:
        """Deactivate one of your triggers by its ID. The trigger won't fire again
        but its history is preserved. Use list_my_triggers to find trigger IDs."""
        from app.db.session import async_session_factory
        from app.models.trigger import AgentTrigger

        try:
            async with async_session_factory() as db:
                trigger = await db.get(AgentTrigger, trigger_id)
                if not trigger:
                    return json.dumps({"error": f"Trigger '{trigger_id}' not found."})
                if trigger.agent_id != agent_id:
                    return json.dumps({"error": "You can only cancel your own triggers."})

                trigger.is_active = False
                await db.commit()

            from app.core.scheduler import sync_triggers
            await sync_triggers()

            logger.info(f"Agent {agent_id} cancelled trigger {trigger_id}")
            return json.dumps({
                "success": True,
                "trigger_id": trigger_id,
                "message": f"Trigger '{trigger.name}' deactivated.",
            })
        except Exception as e:
            logger.error(f"cancel_trigger error: {e}")
            return json.dumps({"error": str(e)})

    return [schedule_self, list_my_triggers, cancel_trigger]
