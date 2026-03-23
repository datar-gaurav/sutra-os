"""Audit logging helpers — write immutable audit records to the database."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.correlation import get_request_id
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_type: str = "user",
    actor_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """
    Append an audit record. Silently swallows errors so auditing never
    breaks a real request.

    Usage:
        await record_audit(
            db, action="agent.create", resource_type="agent",
            resource_id=agent.id, actor_id=current_user.id,
        )
    """
    try:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=get_request_id() or None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        # Flush immediately so the record lands even if the caller commits later
        await db.flush()
    except Exception as exc:
        logger.warning(f"Failed to write audit log for action={action}: {exc}")
