"""Goal Engine — runs agent check-ins, detects stuck items, creates initiatives."""

import json
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.agent import Agent
from app.models.checkin import AgentCheckIn
from app.models.conversation import Conversation, Message
from app.models.goal import AgentGoal, GoalStatus
from app.models.initiative import AgentInitiative
from app.models.task import Task, TaskStatus
from app.models.trigger import AgentTrigger

logger = logging.getLogger(__name__)

# How many days without update before a task is "stuck"
STUCK_THRESHOLD_DAYS = 3

_CHECKIN_PROMPT = """You are performing a structured self-assessment. Review your current goals and assigned tasks, then produce a JSON report.

## Your Active Goals
{goals_section}

## Your In-Progress Tasks
{tasks_section}

## Instructions
Produce ONLY valid JSON in this exact structure (no markdown fences, no extra text):
{{
  "summary": "2-3 sentence overall status",
  "goals_reviewed": [
    {{
      "goal_id": "id",
      "title": "goal title",
      "progress": "what you have done toward this goal",
      "status_update": "on_track | at_risk | blocked | completed",
      "next_step": "immediate next action"
    }}
  ],
  "tasks_reviewed": [
    {{
      "task_id": "id",
      "title": "task title",
      "status": "current status",
      "note": "brief update"
    }}
  ],
  "blockers": ["blocker 1", "blocker 2"],
  "proposed_actions": ["action 1", "action 2"],
  "proposed_initiatives": [
    {{
      "title": "initiative title",
      "description": "what and why",
      "rationale": "business reason",
      "estimated_impact": "expected outcome",
      "proposed_actions": ["step 1", "step 2"]
    }}
  ]
}}

Be honest about blockers. Only include proposed_initiatives if you have a genuinely valuable new idea. Empty arrays are fine.
"""


def _format_goals(goals: list[AgentGoal]) -> str:
    if not goals:
        return "No active goals assigned."
    lines = []
    for g in goals:
        lines.append(f"- [{g.id}] {g.title} (priority: {g.priority})")
        if g.description:
            lines.append(f"  Description: {g.description}")
        if g.success_criteria:
            lines.append(f"  Success: {g.success_criteria}")
        if g.deadline:
            lines.append(f"  Deadline: {g.deadline}")
        if g.progress_notes:
            last = g.progress_notes[-1] if g.progress_notes else None
            if last:
                lines.append(f"  Last update: {last.get('note', '')}")
    return "\n".join(lines)


def _format_tasks(tasks: list[Task]) -> str:
    if not tasks:
        return "No in-progress tasks assigned."
    lines = []
    for t in tasks:
        lines.append(f"- [{t.id}] {t.title} (status: {t.status}, priority: {t.priority})")
        if t.description:
            lines.append(f"  {t.description[:200]}")
    return "\n".join(lines)


def _detect_stuck(tasks: list[Task]) -> list[dict]:
    """Flag tasks in_progress/review that haven't been updated recently."""
    threshold = datetime.now(timezone.utc) - timedelta(days=STUCK_THRESHOLD_DAYS)
    stuck = []
    for t in tasks:
        if t.status in (TaskStatus.in_progress.value, TaskStatus.review.value):
            try:
                updated = datetime.fromisoformat(str(t.updated_at))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if updated < threshold:
                    stuck.append({
                        "task_id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "days_stale": (datetime.now(timezone.utc) - updated).days,
                    })
            except Exception:
                pass
    return stuck


async def run_checkin(agent_id: str) -> AgentCheckIn:
    """Run a self-assessment check-in for the given agent. Returns the saved record."""
    async with async_session_factory() as db:
        agent = await db.get(Agent, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Load active goals
        goals_result = await db.execute(
            select(AgentGoal).where(
                AgentGoal.agent_id == agent_id,
                AgentGoal.status == GoalStatus.active.value,
            )
        )
        goals = goals_result.scalars().all()

        # Load in-progress tasks
        tasks_result = await db.execute(
            select(Task).where(
                Task.assignee_agent_id == agent_id,
                Task.status.in_([TaskStatus.in_progress.value, TaskStatus.review.value, TaskStatus.todo.value]),
            )
        )
        tasks = tasks_result.scalars().all()

        # Build prompt
        prompt = _CHECKIN_PROMPT.format(
            goals_section=_format_goals(list(goals)),
            tasks_section=_format_tasks(list(tasks)),
        )

        # Invoke agent
        raw_response = ""
        had_error = False
        try:
            from app.core.agent_manager import agent_manager
            if not agent_manager.is_running(agent_id):
                # Start agent temporarily for check-in
                config = {
                    "id": agent.id,
                    "name": agent.name,
                    "system_prompt": agent.system_prompt,
                    "llm_provider": agent.llm_provider,
                    "llm_model": agent.llm_model,
                    "temperature": agent.temperature,
                    "max_tokens": agent.max_tokens,
                    "enabled_tools": agent.enabled_tools or [],
                    "secondary_provider": agent.secondary_provider,
                    "secondary_model": agent.secondary_model,
                    "fallback_provider": agent.fallback_provider,
                    "fallback_model": agent.fallback_model,
                }
                await agent_manager.start_agent(config)

            from app.core.orchestrator import orchestrator
            result = await orchestrator.route_message(
                agent_id=agent_id,
                message=prompt,
                chat_history=[],
            )
            raw_response = result.get("output", "")
            if result.get("error"):
                had_error = True
        except Exception as e:
            logger.error(f"Check-in invocation failed for agent {agent_id}: {e}")
            raw_response = str(e)
            had_error = True

        # Parse JSON from response
        parsed: dict = {}
        try:
            # Strip markdown fences if present
            text = raw_response.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)
        except Exception:
            logger.warning(f"Could not parse check-in JSON for agent {agent_id}")
            parsed = {}

        stuck_items = _detect_stuck(list(tasks))

        # Build check-in record
        checkin = AgentCheckIn(
            agent_id=agent_id,
            summary=parsed.get("summary", raw_response[:500] if raw_response else "Check-in completed."),
            goals_reviewed=parsed.get("goals_reviewed", []),
            tasks_reviewed=parsed.get("tasks_reviewed", []),
            blockers=parsed.get("blockers", []),
            proposed_actions=parsed.get("proposed_actions", []),
            stuck_items=stuck_items,
            proposed_initiatives=parsed.get("proposed_initiatives", []),
            had_error=had_error,
            raw_response=raw_response[:5000] if raw_response else None,
        )
        db.add(checkin)
        await db.flush()
        await db.refresh(checkin)

        # ── Auto-sync: write agent's goal progress back to the goal records ──
        goals_by_id = {g.id: g for g in goals}
        for gr in parsed.get("goals_reviewed", []):
            gid = gr.get("goal_id", "")
            if gid in goals_by_id:
                goal_obj = goals_by_id[gid]
                note_text = gr.get("progress", "")
                if note_text:
                    entry = {
                        "note": note_text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "checkin",
                    }
                    goal_obj.progress_notes = list(goal_obj.progress_notes or []) + [entry]

                # If agent reports completed, create an approval request instead of auto-completing
                su = gr.get("status_update", "")
                if su == "completed":
                    from app.models.approval_request import ApprovalRequest
                    approval = ApprovalRequest(
                        title=f"Goal Completion: {goal_obj.title}",
                        description=(
                            f"Agent self-reported this goal as completed during check-in.\n\n"
                            f"**Agent's progress note:** {note_text}\n\n"
                            f"**Success Criteria:** {goal_obj.success_criteria or 'Not specified'}"
                        ),
                        category="goal_completion",
                        risk_level="low",
                        context={"goal_id": gid, "goal_title": goal_obj.title, "checkin_id": checkin.id},
                        action_payload={"action": "complete_goal", "goal_id": gid},
                        requester_agent_id=agent_id,
                    )
                    db.add(approval)

        # ── Save proposed initiatives ──
        initiative_ids = []
        for init_data in parsed.get("proposed_initiatives", []):
            if isinstance(init_data, dict) and init_data.get("title"):
                initiative = AgentInitiative(
                    agent_id=agent_id,
                    checkin_id=checkin.id,
                    title=init_data.get("title", ""),
                    description=init_data.get("description"),
                    rationale=init_data.get("rationale"),
                    proposed_actions=init_data.get("proposed_actions", []),
                    estimated_impact=init_data.get("estimated_impact"),
                )
                db.add(initiative)
                await db.flush()
                initiative_ids.append(initiative.id)

        await db.commit()
        await db.refresh(checkin)
        logger.info(f"Check-in complete for agent {agent_id}: {checkin.id}")

        # ── Post-check-in notifications via WebSocket ──
        try:
            from app.api.websocket import manager
            import asyncio

            # Notify: check-in completed
            asyncio.create_task(manager.broadcast({
                "type": "checkin_completed",
                "agent_id": agent_id,
                "checkin_id": checkin.id,
                "summary": checkin.summary,
                "stuck_count": len(stuck_items),
                "initiative_count": len(initiative_ids),
                "blocker_count": len(parsed.get("blockers", [])),
            }))

            # Notify: stuck items need attention
            if stuck_items:
                asyncio.create_task(manager.broadcast({
                    "type": "stuck_items_detected",
                    "agent_id": agent_id,
                    "checkin_id": checkin.id,
                    "items": stuck_items,
                }))

            # Notify: new initiatives proposed
            for iid in initiative_ids:
                asyncio.create_task(manager.broadcast({
                    "type": "initiative_proposed",
                    "agent_id": agent_id,
                    "checkin_id": checkin.id,
                    "initiative_id": iid,
                }))
        except Exception as e:
            logger.debug(f"WebSocket notification failed (non-critical): {e}")

        return checkin


async def fire_trigger(trigger_id: str, payload: dict | None = None) -> dict:
    """Execute an agent trigger (webhook or manual fire)."""
    # Phase 1: Load trigger + agent data, then release the DB session
    async with async_session_factory() as db:
        trigger = await db.get(AgentTrigger, trigger_id)
        if not trigger or not trigger.is_active:
            return {"error": "Trigger not found or inactive"}

        agent = await db.get(Agent, trigger.agent_id)
        if not agent:
            return {"error": "Agent not found"}

        agent_id = trigger.agent_id
        prompt_template = trigger.prompt_template
        agent_config = {
            "id": agent.id,
            "name": agent.name,
            "system_prompt": agent.system_prompt,
            "llm_provider": agent.llm_provider,
            "llm_model": agent.llm_model,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "enabled_tools": agent.enabled_tools or [],
            "secondary_provider": agent.secondary_provider,
            "secondary_model": agent.secondary_model,
            "fallback_provider": agent.fallback_provider,
            "fallback_model": agent.fallback_model,
        }

    # Phase 2: Run the LLM call (may take minutes) — no DB session held open
    payload_str = json.dumps(payload, indent=2) if payload else "{}"
    prompt = prompt_template.replace("{payload}", payload_str)

    output = ""
    error_msg = None
    conversation_id = None
    try:
        from app.core.agent_manager import agent_manager
        if not agent_manager.is_running(agent_id):
            await agent_manager.start_agent(agent_config)

        from app.core.orchestrator import orchestrator

        # Create a conversation so the output is visible in the agent chat UI
        async with async_session_factory() as db:
            async with db.begin():
                conversation = Conversation(
                    agent_id=agent_id,
                    title=f"Webhook: {prompt[:80]}",
                    source="webhook",
                )
                db.add(conversation)
                await db.flush()
                await db.refresh(conversation)
                conversation_id = conversation.id

                user_msg = Message(
                    conversation_id=conversation_id,
                    role="user",
                    content=prompt,
                )
                db.add(user_msg)

            result = await orchestrator.route_message(
                agent_id=agent_id,
                message=prompt,
                chat_history=[],
                db=db,
            )
            output = result.get("output", "")

            async with db.begin():
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=output,
                    tool_calls={"steps": result.get("intermediate_steps", [])} if result.get("intermediate_steps") else None,
                )
                db.add(assistant_msg)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Trigger {trigger_id} fire failed: {e}")

    # Phase 3: Update trigger stats with a fresh DB session
    try:
        async with async_session_factory() as db:
            async with db.begin():
                trigger = await db.get(AgentTrigger, trigger_id)
                if trigger:
                    trigger.last_fired_at = datetime.now(timezone.utc).isoformat()
                    trigger.fire_count = (trigger.fire_count or 0) + 1
                    trigger.last_output = output[:2000] if output else None
                    trigger.last_error = error_msg
    except Exception as e:
        logger.error(f"Failed to update trigger stats for {trigger_id}: {e}")

    return {"output": output, "error": error_msg, "conversation_id": conversation_id}
