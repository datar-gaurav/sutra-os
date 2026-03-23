"""Tool registry API routes."""

from fastapi import APIRouter

from app.api.schemas import ToolInfo
from app.tools.registry import get_tool_catalog

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/", response_model=list[ToolInfo])
async def list_tools():
    """List all available tools with metadata."""
    return get_tool_catalog()
