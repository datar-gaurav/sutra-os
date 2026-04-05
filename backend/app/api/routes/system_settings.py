"""System settings API — runtime configuration management."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.system_settings import sys_settings
from app.db.session import get_db

router = APIRouter(prefix="/settings/system", tags=["settings"])


class SystemSettingsUpdate(BaseModel):
    updates: dict  # key → value (or null to reset)


@router.get("/")
async def get_system_settings():
    """Get all system settings with schema, current values, and override status."""
    return sys_settings.get_schema()


@router.patch("/")
async def update_system_settings(
    payload: SystemSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update system setting overrides. Pass null to reset a key to its default."""
    new_values = await sys_settings.update(db, payload.updates)
    return {"updated": list(payload.updates.keys()), "values": new_values}


@router.delete("/reset")
async def reset_all_settings(db: AsyncSession = Depends(get_db)):
    """Reset all settings to their defaults (remove all overrides)."""
    from app.models.system_config import SystemConfig
    from sqlalchemy import select

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.id == "default")
    )
    config = result.scalars().first()
    if config:
        config.overrides = {}
        await db.flush()

    sys_settings._overrides.clear()
    return {"status": "ok", "values": sys_settings.get_all()}
