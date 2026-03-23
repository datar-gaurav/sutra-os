"""Approval request routes — human-in-the-loop gates for agent and workflow actions."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ApprovalDecision, ApprovalRequestCreate, ApprovalRequestResponse
from app.core.audit import record_audit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.approval_request import ApprovalRequest, ApprovalStatus
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("/pending-count")
async def pending_count(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(func.count(ApprovalRequest.id)).where(
            ApprovalRequest.status == ApprovalStatus.pending.value
        )
    )
    return {"count": result.scalar() or 0}


@router.get("/", response_model=list[ApprovalRequestResponse])
async def list_approvals(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ApprovalRequest)
    if status:
        query = query.where(ApprovalRequest.status == status)
    query = query.order_by(ApprovalRequest.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=ApprovalRequestResponse)
async def create_approval(
    payload: ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expires_at = None
    if payload.expires_in_minutes:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=payload.expires_in_minutes)

    req = ApprovalRequest(
        title=payload.title,
        description=payload.description,
        category=payload.category,
        risk_level=payload.risk_level,
        context=payload.context,
        action_payload=payload.action_payload,
        requester_agent_id=payload.requester_agent_id,
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        expires_at=expires_at,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)

    try:
        from app.api.websocket import ws_manager
        await ws_manager.broadcast({
            "type": "approval_requested",
            "approval_id": req.id,
            "title": req.title,
            "risk_level": req.risk_level,
            "category": req.category,
        })
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed for approval {req.id}: {e}")

    asyncio.create_task(_dispatch_webhook("approval.requested", {
        "id": req.id, "title": req.title, "category": req.category, "risk_level": req.risk_level,
    }, req.requester_agent_id))
    return req


@router.get("/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(approval_id: str, db: AsyncSession = Depends(get_db)):
    req = await db.get(ApprovalRequest, approval_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return req


@router.post("/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve(
    approval_id: str,
    payload: ApprovalDecision = ApprovalDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await db.get(ApprovalRequest, approval_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req.status != ApprovalStatus.pending.value:
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    # Check expiry
    if req.expires_at and datetime.now(timezone.utc) > req.expires_at:
        req.status = ApprovalStatus.expired.value
        await db.flush()
        raise HTTPException(status_code=400, detail="Approval request has expired")

    req.status = ApprovalStatus.approved.value
    req.reviewer_user_id = current_user.id
    req.reviewer_note = payload.note
    req.decided_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(req)

    await record_audit(
        db, actor_type="user", actor_id=current_user.id,
        action="approve_request", resource_type="approval_request",
        resource_id=approval_id,
    )

    # Execute deferred action if present
    if req.action_payload:
        await _execute_approved_action(req, db)

    # Auto-resume workflow if this approval was for a workflow gate
    if req.workflow_id:
        await _resume_workflow(req.workflow_id)

    # Notify UI
    try:
        from app.api.websocket import ws_manager
        await ws_manager.broadcast({
            "type": "approval_decided",
            "approval_id": req.id,
            "decision": "approved",
        })
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")

    asyncio.create_task(_dispatch_webhook("approval.approved", {
        "id": req.id, "title": req.title, "decided_by": current_user.id,
    }, req.requester_agent_id))
    return req


@router.post("/{approval_id}/reject", response_model=ApprovalRequestResponse)
async def reject(
    approval_id: str,
    payload: ApprovalDecision = ApprovalDecision(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await db.get(ApprovalRequest, approval_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req.status != ApprovalStatus.pending.value:
        raise HTTPException(status_code=400, detail=f"Request is already {req.status}")

    # Check expiry
    if req.expires_at and datetime.now(timezone.utc) > req.expires_at:
        req.status = ApprovalStatus.expired.value
        await db.flush()
        raise HTTPException(status_code=400, detail="Approval request has expired")

    req.status = ApprovalStatus.rejected.value
    req.reviewer_user_id = current_user.id
    req.reviewer_note = payload.note
    req.decided_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(req)

    await record_audit(
        db, actor_type="user", actor_id=current_user.id,
        action="reject_request", resource_type="approval_request",
        resource_id=approval_id,
    )

    try:
        from app.api.websocket import ws_manager
        await ws_manager.broadcast({
            "type": "approval_decided",
            "approval_id": req.id,
            "decision": "rejected",
        })
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")

    asyncio.create_task(_dispatch_webhook("approval.rejected", {
        "id": req.id, "title": req.title, "decided_by": current_user.id,
    }, req.requester_agent_id))
    return req


async def _dispatch_webhook(event: str, payload: dict, agent_id: str | None = None) -> None:
    try:
        from app.core.webhook_service import dispatch_event
        await dispatch_event(event, payload, agent_id)
    except Exception:
        pass


async def _resume_workflow(workflow_id: str) -> None:
    """Re-execute a workflow after an approval gate was approved.

    The workflow engine checks for existing approved ApprovalRequest records,
    so re-running will pass through the now-approved gate and continue.
    """
    import asyncio

    try:
        from app.core.scheduler import execute_workflow
        # Run in background so the approve response returns immediately
        asyncio.create_task(execute_workflow(workflow_id))
        logger.info(f"Auto-resuming workflow {workflow_id} after approval.")
    except Exception as e:
        logger.error(f"Failed to auto-resume workflow {workflow_id}: {e}")


async def _execute_approved_action(req: ApprovalRequest, db: AsyncSession) -> None:
    """Execute the deferred action stored in action_payload after human approval."""
    payload = req.action_payload or {}
    action = payload.get("action") or payload.get("type")

    try:
        if action == "run_prompt":
            agent_id = payload.get("agent_id") or req.requester_agent_id
            prompt = payload.get("prompt")
            if agent_id and prompt:
                from app.core.orchestrator import orchestrator
                await orchestrator.route_message(
                    agent_id=agent_id,
                    message=f"[APPROVED ACTION]\n{prompt}",
                    chat_history=[],
                )

        elif action == "complete_goal":
            goal_id = payload.get("goal_id")
            if goal_id:
                from app.models.goal import AgentGoal
                from datetime import datetime, timezone
                goal = await db.get(AgentGoal, goal_id)
                if goal and goal.status != "completed":
                    goal.status = "completed"
                    goal.progress_notes = list(goal.progress_notes or []) + [{
                        "note": f"Marked completed by {req.reviewer_user_id or 'human reviewer'} after agent request.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "approval",
                    }]
                    await db.flush()
                    logger.info(f"Goal {goal_id} marked completed via approval {req.id}")

        elif action == "evolve_action":
            suggestion_id = payload.get("suggestion_id")
            if suggestion_id:
                from app.core.evolve_service import execute_evolve_action
                import asyncio
                asyncio.create_task(execute_evolve_action(suggestion_id))
                logger.info(f"Evolve action triggered for suggestion {suggestion_id}")

        await record_audit(
            db, action="execute_approved_action", actor_type="system",
            resource_type="approval_request", resource_id=req.id,
            details={"action": action},
        )
    except Exception as e:
        logger.error(f"Failed to execute approved action for {req.id}: {e}")
