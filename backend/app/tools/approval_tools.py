"""LangChain tools for agents to request human approval before high-stakes actions."""

import json
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

APPROVAL_TOOL_IDS = {"request_approval"}

# Risk levels ordered from lowest to highest
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _should_auto_approve(risk_level: str, auto_approve_below: str | None) -> bool:
    """Return True if this risk level qualifies for automatic approval.

    auto_approve_below="low"    → auto-approve only "low" risk
    auto_approve_below="medium" → auto-approve "low" and "medium" risk
    auto_approve_below=None     → never auto-approve
    """
    if not auto_approve_below:
        return False
    threshold = _RISK_ORDER.get(auto_approve_below, -1)
    level = _RISK_ORDER.get(risk_level, 99)
    return level <= threshold


def create_approval_tools(agent_id: str):
    """Create approval tools bound to a specific agent as the requester."""

    @tool
    async def request_approval(
        title: str,
        description: str,
        category: str = "general",
        risk_level: str = "medium",
        reasoning: str = "",
        alternatives: str = "",
        risk_assessment: str = "",
        recommended_action: str = "",
        action_payload: str = "",
        expires_in_minutes: int = 60,
    ) -> str:
        """Request human approval before proceeding with a high-stakes action.

        Use this tool when you need to take an action that is:
        - financial: involves money, budget, or purchasing decisions
        - external: sends emails, posts to social media, contacts external parties
        - destructive: deletes data, files, or makes irreversible changes
        - strategic: major decisions affecting product direction or organization

        If the agent has auto-approval enabled for the given risk level,
        the action will be approved automatically without human intervention.

        Args:
            title: Short title for the approval request (max 300 chars).
            description: Clear description of what you want to do and why.
            category: One of: financial, external, destructive, strategic, general.
            risk_level: One of: low, medium, high, critical.
            reasoning: Your reasoning for why this action is needed.
            alternatives: Other options you considered.
            risk_assessment: What could go wrong if this proceeds.
            recommended_action: What you recommend the human approve.
            action_payload: JSON string with the action to execute if approved.
                            Format: {"type": "run_prompt", "prompt": "...", "agent_id": "..."}
            expires_in_minutes: Minutes until this request expires (default 60).

        Returns JSON with the approval_id and status message.
        """
        valid_categories = {"financial", "external", "destructive", "strategic", "general"}
        valid_risk_levels = {"low", "medium", "high", "critical"}

        if category not in valid_categories:
            category = "general"
        if risk_level not in valid_risk_levels:
            risk_level = "medium"

        context = {
            "reasoning": reasoning,
            "alternatives": alternatives,
            "risk_assessment": risk_assessment,
            "recommended_action": recommended_action,
        }

        parsed_payload = None
        if action_payload:
            try:
                parsed_payload = json.loads(action_payload)
            except json.JSONDecodeError:
                parsed_payload = {"raw": action_payload}

        # ── Check auto-approval ──────────────────────────────────────────────
        from app.models.agent import Agent

        async with async_session_factory() as db:
            agent = await db.get(Agent, agent_id)
            auto_approve_setting = agent.auto_approve_below if agent else None

        if _should_auto_approve(risk_level, auto_approve_setting):
            # Auto-approve: create an already-approved record for audit trail
            from app.models.approval_request import ApprovalRequest, ApprovalStatus

            async with async_session_factory() as db:
                req = ApprovalRequest(
                    title=title,
                    description=description,
                    category=category,
                    risk_level=risk_level,
                    context={**context, "auto_approved": True},
                    action_payload=parsed_payload,
                    requester_agent_id=agent_id,
                    status=ApprovalStatus.approved.value,
                    reviewer_note=f"Auto-approved: risk_level '{risk_level}' within agent threshold '{auto_approve_setting}'",
                    decided_at=datetime.now(timezone.utc),
                )
                db.add(req)
                await db.commit()
                await db.refresh(req)

                # Execute deferred action immediately
                if parsed_payload:
                    from app.api.routes.approvals import _execute_approved_action
                    await _execute_approved_action(req, db)

                logger.info(
                    f"Agent {agent_id} auto-approved request {req.id}: "
                    f"{title!r} (risk={risk_level}, threshold={auto_approve_setting})"
                )

            try:
                from app.api.websocket import ws_manager
                await ws_manager.broadcast({
                    "type": "approval_auto_approved",
                    "approval_id": req.id,
                    "title": title,
                    "risk_level": risk_level,
                    "agent_id": agent_id,
                })
            except Exception:
                pass

            return json.dumps({
                "approval_id": req.id,
                "status": "auto_approved",
                "message": (
                    f"Action auto-approved (risk '{risk_level}' is within your "
                    f"auto-approval threshold '{auto_approve_setting}'). "
                    f"Proceeding immediately. Audit record: {req.id}."
                ),
            })

        # ── Normal flow: create pending approval ─────────────────────────────
        from app.models.approval_request import ApprovalRequest

        async with async_session_factory() as db:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

            req = ApprovalRequest(
                title=title,
                description=description,
                category=category,
                risk_level=risk_level,
                context=context,
                action_payload=parsed_payload,
                requester_agent_id=agent_id,
                expires_at=expires_at,
            )
            db.add(req)
            await db.commit()
            await db.refresh(req)

            logger.info(f"Agent {agent_id} created approval request {req.id}: {title!r}")

            try:
                from app.api.websocket import ws_manager
                await ws_manager.broadcast({
                    "type": "approval_requested",
                    "approval_id": req.id,
                    "title": title,
                    "risk_level": risk_level,
                    "category": category,
                    "requester_agent_id": agent_id,
                })
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed for approval {req.id}: {e}")

            return json.dumps({
                "approval_id": req.id,
                "status": "pending",
                "message": (
                    f"Approval request submitted to human reviewers. "
                    f"Request ID: {req.id}. "
                    f"I have paused this action and am awaiting human sign-off. "
                    f"The request expires in {expires_in_minutes} minutes. "
                    f"You can review it at /approvals."
                ),
            })

    return [request_approval]
