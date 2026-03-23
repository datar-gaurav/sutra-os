"""Goal tools — let agents read, update, and complete their own goals."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

GOAL_TOOL_IDS = {"get_my_goals", "update_goal_progress", "request_goal_completion"}


def create_goal_tools(agent_id: str):
    @tool
    async def get_my_goals(include_completed: bool = False) -> str:
        """List your currently assigned goals with their details, progress, and deadlines.

        Args:
            include_completed: If True, also show completed/abandoned goals.
        """
        from app.db.session import async_session_factory
        from app.models.goal import AgentGoal, GoalStatus
        from sqlalchemy import select

        async with async_session_factory() as db:
            q = select(AgentGoal).where(AgentGoal.agent_id == agent_id)
            if not include_completed:
                q = q.where(AgentGoal.status.in_([GoalStatus.active.value, GoalStatus.paused.value]))
            q = q.order_by(AgentGoal.priority, AgentGoal.created_at)
            result = await db.execute(q)
            goals = result.scalars().all()

        if not goals:
            return "You have no active goals assigned."

        lines = []
        for g in goals:
            lines.append(f"## [{g.priority.upper()}] {g.title}")
            lines.append(f"   ID: {g.id} | Status: {g.status}")
            if g.description:
                lines.append(f"   Description: {g.description}")
            if g.success_criteria:
                lines.append(f"   Success criteria: {g.success_criteria}")
            if g.deadline:
                lines.append(f"   Deadline: {g.deadline}")
            notes = g.progress_notes or []
            if notes:
                last = notes[-1]
                lines.append(f"   Latest progress ({last.get('timestamp', '?')}): {last.get('note', '')}")
            lines.append("")
        return "\n".join(lines)

    @tool
    async def update_goal_progress(goal_id: str, note: str, status: str = "") -> str:
        """Report progress on one of your goals. Call this whenever you make meaningful progress.

        Args:
            goal_id: The goal UUID to update.
            note: Description of what you accomplished or observed.
            status: Optionally change goal status to 'active', 'paused', or 'at_risk'. Leave empty to keep current status.
        """
        from app.db.session import async_session_factory
        from app.models.goal import AgentGoal

        async with async_session_factory() as db:
            goal = await db.get(AgentGoal, goal_id)
            if not goal:
                return f"Error: Goal {goal_id} not found."
            if goal.agent_id != agent_id:
                return "Error: This goal is not assigned to you."

            entry = {
                "note": note,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "agent",
            }
            goal.progress_notes = list(goal.progress_notes or []) + [entry]

            if status and status in ("active", "paused"):
                goal.status = status

            await db.commit()
            await db.refresh(goal)

        # Broadcast to UI
        try:
            from app.api.websocket import manager
            import asyncio
            asyncio.create_task(manager.broadcast({
                "type": "goal_progress",
                "agent_id": agent_id,
                "goal_id": goal_id,
                "note": note,
            }))
        except Exception:
            pass

        return f"Progress recorded for goal '{goal.title}'. Total progress notes: {len(goal.progress_notes)}"

    @tool
    async def request_goal_completion(goal_id: str, evidence: str) -> str:
        """Request human approval to mark a goal as completed. Use when you believe you have met the success criteria.

        Args:
            goal_id: The goal UUID you believe is complete.
            evidence: Summary of what was accomplished and how success criteria were met.
        """
        from app.db.session import async_session_factory
        from app.models.goal import AgentGoal
        from app.models.approval_request import ApprovalRequest

        async with async_session_factory() as db:
            goal = await db.get(AgentGoal, goal_id)
            if not goal:
                return f"Error: Goal {goal_id} not found."
            if goal.agent_id != agent_id:
                return "Error: This goal is not assigned to you."
            if goal.status == "completed":
                return "This goal is already marked as completed."

            # Create an approval request
            approval = ApprovalRequest(
                title=f"Goal Completion: {goal.title}",
                description=f"Agent requests to mark this goal as completed.\n\n**Evidence:**\n{evidence}\n\n**Success Criteria:**\n{goal.success_criteria or 'Not specified'}",
                category="goal_completion",
                risk_level="low",
                context={
                    "goal_id": goal_id,
                    "goal_title": goal.title,
                    "evidence": evidence,
                },
                action_payload={
                    "action": "complete_goal",
                    "goal_id": goal_id,
                },
                requester_agent_id=agent_id,
            )
            db.add(approval)
            await db.commit()
            await db.refresh(approval)

        # Notify via WebSocket
        try:
            from app.api.websocket import manager
            import asyncio
            asyncio.create_task(manager.broadcast({
                "type": "approval_requested",
                "approval_id": approval.id,
                "category": "goal_completion",
                "title": approval.title,
                "agent_id": agent_id,
            }))
        except Exception:
            pass

        return f"Completion request submitted for approval (ID: {approval.id}). A human reviewer will approve or reject this."

    return [get_my_goals, update_goal_progress, request_goal_completion]
