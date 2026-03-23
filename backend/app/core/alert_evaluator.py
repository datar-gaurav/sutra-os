"""Alert evaluator — scheduled + immediate alert evaluation engine."""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _fingerprint(rule_type: str, agent_id: str | None, extra: str = "") -> str:
    """Compute a dedup fingerprint for an alert."""
    raw = f"{rule_type}:{agent_id or 'global'}:{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def evaluate_alerts() -> dict:
    """
    Scheduled evaluation: check all active alert rules against current data.
    Creates new AlertRecord entries for triggered rules (with dedup).
    Auto-resolves firing alerts whose condition is no longer true.

    Returns stats dict: {"fired": N, "auto_resolved": N, "rules_checked": N}
    """
    from app.models.alert_record import AlertRecord, AlertRule, AlertStatus
    from app.models.trace import ExecutionTrace
    from app.models.usage import ModelUsage, ModelLimit

    stats = {"fired": 0, "auto_resolved": 0, "rules_checked": 0}

    async with async_session_factory() as db:
        # Load active rules
        result = await db.execute(
            select(AlertRule).where(AlertRule.is_active == True)
        )
        rules = result.scalars().all()
        stats["rules_checked"] = len(rules)

        now = datetime.now(timezone.utc)

        for rule in rules:
            try:
                triggered, context = await _evaluate_rule(db, rule, now)
                fp = _fingerprint(rule.rule_type, rule.agent_id, str(rule.threshold))

                if triggered:
                    await _maybe_fire_alert(db, rule, fp, context, now)
                    stats["fired"] += 1
                else:
                    # Auto-resolve if previously firing
                    resolved = await _auto_resolve(db, fp, now)
                    if resolved:
                        stats["auto_resolved"] += 1
            except Exception as e:
                logger.warning(f"[Alerts] Failed to evaluate rule {rule.name}: {e}")

        await db.commit()

    logger.info(f"[Alerts] Evaluation complete: {stats}")
    return stats


async def _evaluate_rule(
    db: AsyncSession, rule, now: datetime
) -> tuple[bool, dict]:
    """Evaluate a single rule. Returns (triggered: bool, context: dict)."""
    from app.models.trace import ExecutionTrace
    from app.models.usage import ModelUsage, ModelLimit

    cutoff = now - timedelta(minutes=rule.window_minutes)
    context: dict = {"threshold": rule.threshold, "window_minutes": rule.window_minutes}

    if rule.rule_type == "error_rate":
        stmt = select(ExecutionTrace).where(ExecutionTrace.created_at >= cutoff)
        if rule.agent_id:
            stmt = stmt.where(ExecutionTrace.agent_id == rule.agent_id)
        result = await db.execute(stmt)
        traces = result.scalars().all()
        total = len(traces)
        errors = sum(1 for t in traces if t.had_error)
        rate = errors / total if total > 0 else 0
        context.update({"total": total, "errors": errors, "actual_rate": round(rate, 4)})
        # Need at least 5 traces to trigger
        return total >= 5 and rate > rule.threshold, context

    elif rule.rule_type == "latency_p95":
        stmt = select(ExecutionTrace.latency_ms).where(
            ExecutionTrace.created_at >= cutoff,
            ExecutionTrace.latency_ms.isnot(None),
        )
        if rule.agent_id:
            stmt = stmt.where(ExecutionTrace.agent_id == rule.agent_id)
        result = await db.execute(stmt)
        latencies = sorted([row[0] for row in result.all()])
        if len(latencies) < 5:
            return False, context
        p95_idx = int(len(latencies) * 0.95)
        p95 = latencies[min(p95_idx, len(latencies) - 1)]
        context.update({"p95_ms": p95, "sample_count": len(latencies)})
        return p95 > rule.threshold, context

    elif rule.rule_type == "agent_failure_streak":
        # Check consecutive recent errors per agent
        agents_to_check = [rule.agent_id] if rule.agent_id else await _get_active_agent_ids(db)
        max_streak = 0
        worst_agent = None
        for agent_id in agents_to_check:
            streak = await _count_failure_streak(db, agent_id, cutoff)
            if streak > max_streak:
                max_streak = streak
                worst_agent = agent_id
        context.update({"max_streak": max_streak, "agent_id": worst_agent})
        return max_streak >= rule.threshold, context

    elif rule.rule_type == "quota_usage":
        today = now.date()
        usage_result = await db.execute(
            select(ModelUsage).where(ModelUsage.usage_date == today)
        )
        limit_result = await db.execute(select(ModelLimit))
        usages = usage_result.scalars().all()
        limits = limit_result.scalars().all()

        max_pct = 0.0
        worst_model = None
        for u in usages:
            daily_limit = _resolve_limit(u.provider, u.model, limits)
            if daily_limit and daily_limit > 0:
                pct = u.request_count / daily_limit
                if pct > max_pct:
                    max_pct = pct
                    worst_model = f"{u.provider}/{u.model}"
        context.update({"max_usage_pct": round(max_pct, 4), "model": worst_model})
        return max_pct >= rule.threshold, context

    elif rule.rule_type == "agent_down":
        from app.core.agent_manager import agent_manager
        running = agent_manager.get_running_agents()
        for agent_id in running:
            last_trace = await db.execute(
                select(ExecutionTrace.created_at)
                .where(ExecutionTrace.agent_id == agent_id)
                .order_by(ExecutionTrace.created_at.desc())
                .limit(1)
            )
            row = last_trace.first()
            if row and row[0]:
                last_at = row[0]
                if last_at.tzinfo is None:
                    last_at = last_at.replace(tzinfo=timezone.utc)
                silence_min = (now - last_at).total_seconds() / 60
                if silence_min > rule.threshold:
                    context.update({"agent_id": agent_id, "silence_minutes": round(silence_min, 1)})
                    return True, context
        return False, context

    return False, context


def _resolve_limit(provider: str, model: str, limits) -> int | None:
    exact = next((l for l in limits if l.provider == provider and l.model == model), None)
    if exact:
        return exact.daily_limit
    wildcard = next((l for l in limits if l.provider == provider and l.model == "*"), None)
    return wildcard.daily_limit if wildcard else 100


async def _get_active_agent_ids(db: AsyncSession) -> list[str]:
    from app.models.agent import Agent
    result = await db.execute(
        select(Agent.id).where(Agent.status == "running")
    )
    return [row[0] for row in result.all()]


async def _count_failure_streak(
    db: AsyncSession, agent_id: str, cutoff: datetime
) -> int:
    """Count consecutive errors from most recent trace backward."""
    from app.models.trace import ExecutionTrace
    result = await db.execute(
        select(ExecutionTrace.had_error)
        .where(
            ExecutionTrace.agent_id == agent_id,
            ExecutionTrace.created_at >= cutoff,
        )
        .order_by(ExecutionTrace.created_at.desc())
        .limit(20)
    )
    streak = 0
    for (had_error,) in result.all():
        if had_error:
            streak += 1
        else:
            break
    return streak


async def _maybe_fire_alert(
    db: AsyncSession, rule, fingerprint: str, context: dict, now: datetime
) -> None:
    """Create a new AlertRecord if not already firing and not in cooldown."""
    from app.models.alert_record import AlertRecord, AlertStatus

    # Check for existing firing alert with same fingerprint
    existing = await db.execute(
        select(AlertRecord).where(
            AlertRecord.fingerprint == fingerprint,
            AlertRecord.status == AlertStatus.firing.value,
        )
    )
    if existing.scalars().first():
        return  # Already firing, skip

    # Check cooldown — was there a recently resolved alert?
    cooldown_cutoff = now - timedelta(minutes=rule.cooldown_minutes)
    recent_resolved = await db.execute(
        select(AlertRecord).where(
            AlertRecord.fingerprint == fingerprint,
            AlertRecord.status.in_([AlertStatus.resolved.value, AlertStatus.acknowledged.value]),
            AlertRecord.resolved_at >= cooldown_cutoff,
        )
    )
    if recent_resolved.scalars().first():
        return  # In cooldown

    # Determine agent_id from rule or context
    agent_id = rule.agent_id or context.get("agent_id")

    # Build title/message
    title, message = _build_alert_message(rule, context)

    alert = AlertRecord(
        rule_id=rule.id,
        rule_type=rule.rule_type,
        severity=rule.severity,
        status=AlertStatus.firing.value,
        title=title,
        message=message,
        agent_id=agent_id,
        fingerprint=fingerprint,
        context=context,
        fired_at=now,
        notification_sent=False,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)

    # Send notifications
    asyncio.create_task(_send_notifications(alert, rule))


def _build_alert_message(rule, context: dict) -> tuple[str, str]:
    """Build human-readable title and message for an alert."""
    rt = rule.rule_type

    if rt == "error_rate":
        rate_pct = round(context.get("actual_rate", 0) * 100, 1)
        threshold_pct = round(rule.threshold * 100, 1)
        title = f"Error Rate {rate_pct}% (threshold: {threshold_pct}%)"
        message = (
            f"Error rate is {rate_pct}% over the last {rule.window_minutes} minutes "
            f"({context.get('errors', 0)}/{context.get('total', 0)} requests failed). "
            f"Threshold: {threshold_pct}%."
        )
    elif rt == "latency_p95":
        p95 = context.get("p95_ms", 0)
        title = f"P95 Latency {p95}ms (threshold: {int(rule.threshold)}ms)"
        message = (
            f"95th percentile latency is {p95}ms over the last {rule.window_minutes} minutes "
            f"({context.get('sample_count', 0)} samples). Threshold: {int(rule.threshold)}ms."
        )
    elif rt == "agent_failure_streak":
        streak = context.get("max_streak", 0)
        agent = context.get("agent_id", "unknown")
        title = f"Agent Failure Streak: {streak} consecutive errors"
        message = f"Agent {agent[:8]}... has {streak} consecutive errors. Threshold: {int(rule.threshold)}."
    elif rt == "quota_usage":
        pct = round(context.get("max_usage_pct", 0) * 100, 1)
        model = context.get("model", "unknown")
        title = f"Quota Usage {pct}% — {model}"
        message = f"Model {model} is at {pct}% of daily quota. Threshold: {round(rule.threshold * 100)}%."
    elif rt == "agent_down":
        agent = context.get("agent_id", "unknown")
        silence = context.get("silence_minutes", 0)
        title = f"Agent Unresponsive: {agent[:8]}..."
        message = f"Agent {agent[:8]}... is running but has no activity for {silence} minutes."
    else:
        title = f"Alert: {rule.name}"
        message = f"Rule {rule.name} triggered with threshold {rule.threshold}."

    return title, message


async def _auto_resolve(
    db: AsyncSession, fingerprint: str, now: datetime
) -> bool:
    """Auto-resolve a firing alert if its condition is no longer true."""
    from app.models.alert_record import AlertRecord, AlertStatus

    result = await db.execute(
        select(AlertRecord).where(
            AlertRecord.fingerprint == fingerprint,
            AlertRecord.status == AlertStatus.firing.value,
        )
    )
    alert = result.scalars().first()
    if not alert:
        return False

    alert.status = AlertStatus.resolved.value
    alert.resolved_at = now
    alert.resolved_by = "system"

    # Notify resolution
    asyncio.create_task(_send_resolve_notification(alert))
    return True


async def _send_notifications(alert, rule) -> None:
    """Send notifications for a newly fired alert."""
    try:
        # WebSocket broadcast
        if rule.notify_websocket:
            from app.api.websocket import ws_manager
            await ws_manager.broadcast({
                "type": "alert_fired",
                "data": {
                    "id": alert.id,
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "rule_type": alert.rule_type,
                    "agent_id": alert.agent_id,
                    "fired_at": alert.fired_at.isoformat() if alert.fired_at else None,
                },
            })

        # Webhook dispatch
        if rule.notify_webhook:
            try:
                from app.core.webhook_service import dispatch_event
                await dispatch_event("alert.fired", {
                    "alert_id": alert.id,
                    "severity": alert.severity,
                    "title": alert.title,
                    "message": alert.message,
                    "rule_type": alert.rule_type,
                    "agent_id": alert.agent_id,
                    "context": alert.context,
                }, agent_id=alert.agent_id)
            except Exception:
                pass

        # Mark notification sent
        async with async_session_factory() as db:
            from app.models.alert_record import AlertRecord
            rec = await db.get(AlertRecord, alert.id)
            if rec:
                rec.notification_sent = True
                await db.commit()

    except Exception as e:
        logger.warning(f"[Alerts] Notification failed for alert {alert.id}: {e}")


async def _send_resolve_notification(alert) -> None:
    """Send notification when an alert is auto-resolved."""
    try:
        from app.api.websocket import ws_manager
        await ws_manager.broadcast({
            "type": "alert_resolved",
            "data": {
                "id": alert.id,
                "title": alert.title,
                "rule_type": alert.rule_type,
                "resolved_by": "system",
            },
        })

        try:
            from app.core.webhook_service import dispatch_event
            await dispatch_event("alert.resolved", {
                "alert_id": alert.id,
                "title": alert.title,
                "rule_type": alert.rule_type,
                "resolved_by": "system",
            }, agent_id=alert.agent_id)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"[Alerts] Resolve notification failed: {e}")


# ── Immediate alert check (called from orchestrator._save_trace) ─────────────

async def check_trace_for_immediate_alert(agent_id: str, had_error: bool) -> None:
    """
    Called inline after a trace is saved. Checks for agent failure streaks.
    Lightweight: single DB query.
    """
    if not had_error:
        return

    try:
        async with async_session_factory() as db:
            from app.models.alert_record import AlertRecord, AlertRule, AlertStatus
            from app.models.trace import ExecutionTrace

            # Get the agent_failure_streak rule
            result = await db.execute(
                select(AlertRule).where(
                    AlertRule.rule_type == "agent_failure_streak",
                    AlertRule.is_active == True,
                )
            )
            rules = result.scalars().all()
            if not rules:
                return

            now = datetime.now(timezone.utc)

            for rule in rules:
                # Skip if rule is scoped to a different agent
                if rule.agent_id and rule.agent_id != agent_id:
                    continue

                cutoff = now - timedelta(minutes=rule.window_minutes)
                streak = await _count_failure_streak(db, agent_id, cutoff)

                if streak >= rule.threshold:
                    fp = _fingerprint(rule.rule_type, agent_id, str(rule.threshold))
                    context = {"max_streak": streak, "agent_id": agent_id, "threshold": rule.threshold}
                    await _maybe_fire_alert(db, rule, fp, context, now)
                    await db.commit()

    except Exception as e:
        logger.debug(f"[Alerts] Immediate check failed for agent {agent_id}: {e}")
