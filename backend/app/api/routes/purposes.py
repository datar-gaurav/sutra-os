"""LLM Purpose CRUD and live capacity status API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LLMPurposeCreate, LLMPurposeResponse, LLMPurposeUpdate
from app.db.session import get_db
from app.models.agent import Agent
from app.models.llm_purpose import LLMPurpose

router = APIRouter(prefix="/purposes", tags=["purposes"])


@router.get("/", response_model=list[LLMPurposeResponse])
async def list_purposes(db: AsyncSession = Depends(get_db)):
    """List all purposes."""
    result = await db.execute(select(LLMPurpose).order_by(LLMPurpose.name))
    return result.scalars().all()


@router.post("/", response_model=LLMPurposeResponse, status_code=201)
async def create_purpose(
    payload: LLMPurposeCreate, db: AsyncSession = Depends(get_db)
):
    """Create a new purpose."""
    existing = await db.execute(
        select(LLMPurpose).where(LLMPurpose.name == payload.name)
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Purpose name already exists")

    purpose = LLMPurpose(**payload.model_dump())
    db.add(purpose)
    await db.flush()
    await db.refresh(purpose)
    return purpose


@router.get("/{purpose_id}", response_model=LLMPurposeResponse)
async def get_purpose(purpose_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single purpose."""
    purpose = await db.get(LLMPurpose, purpose_id)
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")
    return purpose


@router.put("/{purpose_id}", response_model=LLMPurposeResponse)
async def update_purpose(
    purpose_id: str,
    payload: LLMPurposeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a purpose."""
    purpose = await db.get(LLMPurpose, purpose_id)
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(purpose, field, value)

    await db.flush()
    await db.refresh(purpose)
    return purpose


@router.delete("/{purpose_id}", status_code=204)
async def delete_purpose(purpose_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a purpose. Fails if agents reference it."""
    purpose = await db.get(LLMPurpose, purpose_id)
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")

    # Check if any agents use this purpose
    agents_result = await db.execute(
        select(Agent.id).where(Agent.purpose_id == purpose_id).limit(1)
    )
    if agents_result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete: agents are using this purpose",
        )

    await db.delete(purpose)


@router.get("/{purpose_id}/status")
async def get_purpose_status(purpose_id: str, db: AsyncSession = Depends(get_db)):
    """Get live capacity status for each slot of a purpose."""
    from app.core.usage_tracker import check_capacity, get_current_usage

    purpose = await db.get(LLMPurpose, purpose_id)
    if not purpose:
        raise HTTPException(status_code=404, detail="Purpose not found")

    slots_status = []
    for i in range(1, 6):
        slot = getattr(purpose, f"priority_{i}")
        if not slot or not isinstance(slot, dict) or not slot.get("provider"):
            slots_status.append({
                "priority": i,
                "provider": None,
                "model": None,
                "has_capacity": False,
                "reason": "Not configured",
                "usage": None,
            })
            continue

        provider = slot["provider"]
        model = slot["model"]
        has_capacity, reason = await check_capacity(provider, model, 0, db=db)
        usage = await get_current_usage(provider, model)

        slots_status.append({
            "priority": i,
            "provider": provider,
            "model": model,
            "has_capacity": has_capacity,
            "reason": reason if not has_capacity else "",
            "usage": usage,
        })

    # Determine overall status
    active_slot = next((s for s in slots_status if s["has_capacity"]), None)
    overall = "green" if active_slot and active_slot["priority"] == 1 else (
        "yellow" if active_slot else "red"
    )

    return {
        "purpose_id": purpose.id,
        "purpose_name": purpose.name,
        "overall_status": overall,
        "active_priority": active_slot["priority"] if active_slot else None,
        "slots": slots_status,
    }
