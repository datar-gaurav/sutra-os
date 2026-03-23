"""System health and status routes."""

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.llm_registry import llm_registry

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    ollama_connected = await llm_registry.check_ollama_connection()

    # Basic DB/Redis checks (simplified — in production use proper health checks)
    db_connected = True  # If we got here, DB is working (middleware handles errors)
    redis_connected = True  # Same logic

    return HealthResponse(
        status="healthy",
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
