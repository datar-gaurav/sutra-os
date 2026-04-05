"""System health and status routes."""

import logging
import os
import pathlib
import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import HealthResponse
from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.llm_registry import llm_registry
from app.core.security import get_current_user
from app.models.user import User, UserRole

router = APIRouter(prefix="/system", tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with real DB and Redis connectivity tests."""
    from sqlalchemy import text

    from app.db.session import async_session_factory
    from app.core.redis_client import get_redis

    ollama_connected = await llm_registry.check_ollama_connection()

    # Real database check
    db_connected = False
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            db_connected = True
    except Exception:
        logger.warning("Health check: database unreachable")

    # Real Redis check
    redis_connected = False
    try:
        redis = await get_redis()
        await redis.ping()
        redis_connected = True
    except Exception:
        logger.warning("Health check: Redis unreachable")

    status = "healthy" if (db_connected and redis_connected) else "degraded"

    return HealthResponse(
        status=status,
        version="0.1.0",
        ollama_connected=ollama_connected,
        db_connected=db_connected,
        redis_connected=redis_connected,
    )


@router.get("/status")
async def system_status():
    """Detailed system status."""
    running_agents = agent_manager.get_running_agents()
    ollama_connected = await llm_registry.check_ollama_connection()

    return {
        "running_agents_count": len(running_agents),
        "running_agent_ids": running_agents,
        "ollama_connected": ollama_connected,
        "ollama_url": settings.ollama_base_url,
    }


@router.post("/restart")
async def restart_backend(current_user: User = Depends(get_current_user)):
    """Restart the backend by triggering uvicorn's --reload watcher.

    Requires admin or owner role. Touches a Python file so uvicorn detects
    a change and restarts the application.
    """
    if current_user.role not in (UserRole.admin, UserRole.owner):
        raise HTTPException(status_code=403, detail="Only admins can restart the backend")
    logger.info("Restart requested via API by user=%s — triggering uvicorn reload", current_user.id)
    # Touch a .py file to trigger uvicorn's file-watcher reload
    trigger = pathlib.Path(__file__).resolve()
    trigger.write_bytes(trigger.read_bytes())
    return {"status": "restarting"}
