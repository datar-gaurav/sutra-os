"""API routes for MCP Server management."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MCPServerCreate, MCPServerResponse, MCPServerUpdate
from app.db.session import get_db
from app.models.mcp_server import MCPServer

router = APIRouter(prefix="/mcp-servers", tags=["MCP Servers"])


@router.get("/", response_model=List[MCPServerResponse])
async def list_mcp_servers(db: AsyncSession = Depends(get_db)):
    """List all MCP servers."""
    result = await db.execute(select(MCPServer).order_by(MCPServer.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=MCPServerResponse)
async def create_mcp_server(server_in: MCPServerCreate, db: AsyncSession = Depends(get_db)):
    """Register a new MCP server."""
    server = MCPServer(**server_in.model_dump())
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific MCP server."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")
    return server


@router.put("/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(server_id: str, server_in: MCPServerUpdate, db: AsyncSession = Depends(get_db)):
    """Update a specific MCP server."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    update_data = server_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)

    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}")
async def delete_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a specific MCP server."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    await db.delete(server)
    await db.commit()
    return {"message": "MCP Server deleted successfully"}


@router.post("/{server_id}/start")
async def start_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Start an MCP server (mark as active)."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    server.is_active = True
    server.status = "running"
    await db.commit()
    await db.refresh(server)
    return {"message": f"MCP Server '{server.name}' started", "status": "running"}


@router.post("/{server_id}/stop")
async def stop_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Stop an MCP server (mark as inactive)."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    server.is_active = False
    server.status = "stopped"
    await db.commit()
    await db.refresh(server)
    return {"message": f"MCP Server '{server.name}' stopped", "status": "stopped"}
