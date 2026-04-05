"""Outbound webhook delivery service.

Call `dispatch_event(event_type, payload)` from anywhere in the app to fan-out
to all matching active subscriptions.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.webhook import DeliveryStatus, WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)

# Request timeout for outbound webhook POSTs
_TIMEOUT = 10.0


async def dispatch_event(
    event_type: str,
    payload: dict,
    agent_id: str | None = None,
) -> None:
    """Dispatch an event to all matching active webhook subscriptions.

    Runs delivery for each subscription concurrently. Errors are logged and
    recorded as failed deliveries — they never propagate to the caller.

    Args:
        event_type: One of the WEBHOOK_EVENTS strings (e.g. "task.created").
        payload:    Event data to POST as JSON.
        agent_id:   If provided, also match subscriptions scoped to this agent.
    """
    import asyncio

    async with async_session_factory() as db:
        result = await db.execute(
            select(WebhookSubscription).where(WebhookSubscription.is_active == True)  # noqa: E712
        )
        subs = result.scalars().all()

    matching = [
        s for s in subs
        if _matches(s, event_type, agent_id)
    ]

    if not matching:
        return

    envelope = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    if agent_id:
        envelope["agent_id"] = agent_id

    tasks = [_deliver(sub, event_type, envelope) for sub in matching]
    await asyncio.gather(*tasks, return_exceptions=True)


def _matches(sub: WebhookSubscription, event_type: str, agent_id: str | None) -> bool:
    """Return True if this subscription should receive this event."""
    events = sub.events or []
    if "*" not in events and event_type not in events:
        return False
    # If subscription is scoped to an agent, only fire for that agent
    if sub.agent_id and sub.agent_id != agent_id:
        return False
    return True


async def _deliver(sub: WebhookSubscription, event_type: str, envelope: dict) -> None:
    """POST the envelope to a single subscription URL and record the delivery."""
    body = json.dumps(envelope, default=str)
    headers = {"Content-Type": "application/json", "X-Sutra-Event": event_type}

    # Merge any custom headers from the subscription
    if sub.headers:
        headers.update(sub.headers)

    # HMAC-SHA256 signature
    if sub.secret:
        try:
            from app.core.vault import decrypt_secret
            raw_secret = decrypt_secret(sub.secret).encode()
        except Exception:
            raw_secret = sub.secret.encode()
        sig = hmac.new(raw_secret, body.encode(), hashlib.sha256).hexdigest()
        headers["X-Sutra-Signature"] = f"sha256={sig}"

    status = DeliveryStatus.pending.value
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.post(sub.url, content=body, headers=headers)
            response_status = resp.status_code
            response_body = resp.text[:2000]
            if resp.is_success:
                status = DeliveryStatus.delivered.value
                logger.info(f"Webhook {sub.id} delivered {event_type} → {sub.url} [{resp.status_code}]")
            else:
                status = DeliveryStatus.failed.value
                error = f"HTTP {resp.status_code}"
                logger.warning(f"Webhook {sub.id} non-2xx {event_type} → {sub.url} [{resp.status_code}]")
    except Exception as exc:
        status = DeliveryStatus.failed.value
        error = str(exc)
        logger.error(f"Webhook {sub.id} delivery error {event_type} → {sub.url}: {exc}")

    # Persist delivery record and update subscription stats
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event_type=event_type,
            payload=envelope,
            status=status,
            response_status=response_status,
            response_body=response_body,
            error=error,
            delivered_at=now if status == DeliveryStatus.delivered.value else None,
        )
        db.add(delivery)

        fresh_sub = await db.get(WebhookSubscription, sub.id)
        if fresh_sub:
            fresh_sub.delivery_count = (fresh_sub.delivery_count or 0) + 1
            if status == DeliveryStatus.failed.value:
                fresh_sub.failure_count = (fresh_sub.failure_count or 0) + 1
            else:
                fresh_sub.last_delivery_at = now

        await db.commit()


async def retry_delivery(delivery_id: str) -> dict:
    """Re-attempt a previously failed delivery."""
    async with async_session_factory() as db:
        delivery = await db.get(WebhookDelivery, delivery_id)
        if not delivery:
            return {"error": "Delivery not found"}
        sub = await db.get(WebhookSubscription, delivery.subscription_id)
        if not sub:
            return {"error": "Subscription not found"}
        delivery.attempt_count = (delivery.attempt_count or 1) + 1
        delivery.status = DeliveryStatus.pending.value
        await db.commit()

    await _deliver(sub, delivery.event_type, delivery.payload)
    return {"retried": True, "delivery_id": delivery_id}
