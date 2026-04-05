"""Alert API routes — list, acknowledge, resolve alerts; CRUD alert rules."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.alert_record import AlertRecord, AlertRule, AlertStatus

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Alert Records ─────────────────────────────────────────────────────────────

@router.get("/")
async def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    agent_id: str | None = None,
    rule_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List alerts with optional filters."""
    stmt = select(AlertRecord).order_by(AlertRecord.fired_at.desc())

    if status:
        stmt = stmt.where(AlertRecord.status == status)
    if severity:
        stmt = stmt.where(AlertRecord.severity == severity)
    if agent_id:
        stmt = stmt.where(AlertRecord.agent_id == agent_id)
    if rule_type:
        stmt = stmt.where(AlertRecord.rule_type == rule_type)

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    alerts = result.scalars().all()

    return [
        {
            "id": a.id,
            "rule_id": a.rule_id,
            "rule_type": a.rule_type,
            "severity": a.severity,
            "status": a.status,
            "title": a.title,
            "message": a.message,
            "agent_id": a.agent_id,
            "fingerprint": a.fingerprint,
            "context": a.context,
            "fired_at": str(a.fired_at) if a.fired_at else None,
            "acknowledged_at": str(a.acknowledged_at) if a.acknowledged_at else None,
            "acknowledged_by": a.acknowledged_by,
            "resolved_at": str(a.resolved_at) if a.resolved_at else None,
            "resolved_by": a.resolved_by,
            "notification_sent": a.notification_sent,
            "created_at": str(a.created_at),
        }
        for a in alerts
    ]


@router.get("/summary")
async def alert_summary(db: AsyncSession = Depends(get_db)):
    """Get alert counts by status and severity for badge display."""
    firing_result = await db.execute(
        select(func.count(AlertRecord.id)).where(AlertRecord.status == "firing")
    )
    ack_result = await db.execute(
        select(func.count(AlertRecord.id)).where(AlertRecord.status == "acknowledged")
    )
    critical_result = await db.execute(
        select(func.count(AlertRecord.id)).where(
            AlertRecord.status == "firing",
            AlertRecord.severity == "critical",
        )
    )
    warning_result = await db.execute(
        select(func.count(AlertRecord.id)).where(
            AlertRecord.status == "firing",
            AlertRecord.severity == "warning",
        )
    )

    return {
        "firing_count": firing_result.scalar() or 0,
        "acknowledged_count": ack_result.scalar() or 0,
        "critical_count": critical_result.scalar() or 0,
        "warning_count": warning_result.scalar() or 0,
    }


@router.post("/acknowledge-all")
async def acknowledge_all(db: AsyncSession = Depends(get_db)):
    """Bulk acknowledge all firing alerts."""
    result = await db.execute(
        select(AlertRecord).where(AlertRecord.status == "firing")
    )
    alerts = result.scalars().all()
    now = datetime.now(timezone.utc)
    for a in alerts:
        a.status = AlertStatus.acknowledged.value
        a.acknowledged_at = now
        a.acknowledged_by = "user"
    await db.commit()
    return {"acknowledged": len(alerts)}


# ── Alert Rules ───────────────────────────────────────────────────────────────
# NOTE: These static /rules routes MUST come before the /{alert_id} dynamic
# route, otherwise FastAPI will match "rules" as an alert_id and return 404.

@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db)):
    """List all alert rules."""
    result = await db.execute(select(AlertRule).order_by(AlertRule.created_at))
    rules = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "rule_type": r.rule_type,
            "is_active": r.is_active,
            "severity": r.severity,
            "agent_id": r.agent_id,
            "threshold": r.threshold,
            "window_minutes": r.window_minutes,
            "cooldown_minutes": r.cooldown_minutes,
            "notify_webhook": r.notify_webhook,
            "notify_websocket": r.notify_websocket,
            "notify_email": r.notify_email,
            "created_at": str(r.created_at),
            "updated_at": str(r.updated_at),
        }
        for r in rules
    ]


@router.post("/rules")
async def create_rule(data: dict, db: AsyncSession = Depends(get_db)):
    """Create a custom alert rule."""
    rule = AlertRule(
        name=data.get("name", "Custom Rule"),
        rule_type=data.get("rule_type", "error_rate"),
        is_active=data.get("is_active", True),
        severity=data.get("severity", "warning"),
        agent_id=data.get("agent_id"),
        threshold=data.get("threshold", 0.01),
        window_minutes=data.get("window_minutes", 10),
        cooldown_minutes=data.get("cooldown_minutes", 30),
        notify_webhook=data.get("notify_webhook", True),
        notify_websocket=data.get("notify_websocket", True),
        notify_email=data.get("notify_email"),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"id": rule.id, "name": rule.name, "status": "created"}


# ── Per-alert routes (dynamic /{alert_id} — must come AFTER all static routes) ─

@router.get("/{alert_id}")
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single alert with full context."""
    alert = await db.get(AlertRecord, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "id": alert.id,
        "rule_id": alert.rule_id,
        "rule_type": alert.rule_type,
        "severity": alert.severity,
        "status": alert.status,
        "title": alert.title,
        "message": alert.message,
        "agent_id": alert.agent_id,
        "fingerprint": alert.fingerprint,
        "context": alert.context,
        "fired_at": str(alert.fired_at) if alert.fired_at else None,
        "acknowledged_at": str(alert.acknowledged_at) if alert.acknowledged_at else None,
        "acknowledged_by": alert.acknowledged_by,
        "resolved_at": str(alert.resolved_at) if alert.resolved_at else None,
        "resolved_by": alert.resolved_by,
        "notification_sent": alert.notification_sent,
        "created_at": str(alert.created_at),
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Acknowledge a firing alert."""
    alert = await db.get(AlertRecord, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status != "firing":
        raise HTTPException(status_code=400, detail=f"Cannot acknowledge alert in '{alert.status}' status")

    alert.status = AlertStatus.acknowledged.value
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = "user"  # TODO: inject current_user.id
    await db.commit()
    return {"status": "acknowledged", "id": alert.id}


@router.post("/{alert_id}/resolve")
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Manually resolve an alert."""
    alert = await db.get(AlertRecord, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status in ("resolved", "expired"):
        raise HTTPException(status_code=400, detail=f"Alert is already {alert.status}")

    alert.status = AlertStatus.resolved.value
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = "user"
    await db.commit()
    return {"status": "resolved", "id": alert.id}


# ── Per-rule routes (dynamic /{rule_id} — must come AFTER static /rules routes) ─

@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Update an alert rule."""
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field in [
        "name", "rule_type", "is_active", "severity", "agent_id",
        "threshold", "window_minutes", "cooldown_minutes",
        "notify_webhook", "notify_websocket", "notify_email",
    ]:
        if field in data:
            setattr(rule, field, data[field])

    await db.commit()
    return {"id": rule.id, "status": "updated"}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Delete an alert rule."""
    rule = await db.get(AlertRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"status": "deleted"}
