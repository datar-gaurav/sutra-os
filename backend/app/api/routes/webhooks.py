"""Outbound webhook subscription management."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionResponse,
    WebhookSubscriptionUpdate,
    WebhookDeliveryResponse,
)
from app.core.vault import encrypt_secret
from app.db.session import get_db
from app.models.webhook import WEBHOOK_EVENTS, WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Supported events list ────────────────────────────────────────────────────

@router.get("/events")
async def list_event_types():
    """Return all event types the platform can emit."""
    return {"events": ["*"] + WEBHOOK_EVENTS}


# ─── Subscriptions ────────────────────────────────────────────────────────────

@router.get("/subscriptions", response_model=list[WebhookSubscriptionResponse])
async def list_subscriptions(
    agent_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
    if agent_id:
        q = q.where(WebhookSubscription.agent_id == agent_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/subscriptions", response_model=WebhookSubscriptionResponse, status_code=201)
async def create_subscription(
    payload: WebhookSubscriptionCreate, db: AsyncSession = Depends(get_db)
):
    sub = WebhookSubscription(
        name=payload.name,
        url=str(payload.url),
        secret=encrypt_secret(payload.secret) if payload.secret else None,
        events=payload.events,
        is_active=payload.is_active,
        agent_id=payload.agent_id,
        headers=payload.headers or {},
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    logger.info(f"Created webhook subscription {sub.id}: {sub.name} → {sub.url}")
    return sub


@router.get("/subscriptions/{sub_id}", response_model=WebhookSubscriptionResponse)
async def get_subscription(sub_id: str, db: AsyncSession = Depends(get_db)):
    sub = await db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Webhook subscription not found")
    return sub


@router.put("/subscriptions/{sub_id}", response_model=WebhookSubscriptionResponse)
async def update_subscription(
    sub_id: str, payload: WebhookSubscriptionUpdate, db: AsyncSession = Depends(get_db)
):
    sub = await db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Webhook subscription not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "secret" and value:
            value = encrypt_secret(value)
        elif field == "url" and value:
            value = str(value)
        setattr(sub, field, value)

    await db.commit()
    await db.refresh(sub)
    return sub


@router.delete("/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(sub_id: str, db: AsyncSession = Depends(get_db)):
    sub = await db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Webhook subscription not found")
    await db.delete(sub)
    await db.commit()


@router.post("/subscriptions/{sub_id}/test")
async def test_subscription(
    sub_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Send a test event to verify the webhook endpoint is reachable."""
    sub = await db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Webhook subscription not found")

    async def _test():
        from app.core.webhook_service import _deliver
        await _deliver(sub, "test.ping", {"message": "Sutra webhook test", "subscription_id": sub_id})

    background_tasks.add_task(_test)
    return {"message": f"Test event queued for subscription '{sub.name}'"}


# ─── Delivery log ─────────────────────────────────────────────────────────────

@router.get("/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    subscription_id: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)
    if subscription_id:
        q = q.where(WebhookDelivery.subscription_id == subscription_id)
    if status:
        q = q.where(WebhookDelivery.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    delivery = await db.get(WebhookDelivery, delivery_id)
    if not delivery:
        raise HTTPException(404, "Delivery not found")

    async def _retry():
        from app.core.webhook_service import retry_delivery as _retry_svc
        await _retry_svc(delivery_id)

    background_tasks.add_task(_retry)
    return {"message": "Retry queued", "delivery_id": delivery_id}
