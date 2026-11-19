"""API routes for MCP Server management."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MCPServerCreate, MCPServerResponse, MCPServerUpdate
from app.core.mcp_manager import mcp_manager
from app.db.session import get_db
from app.models.mcp_server import MCPServer

router = APIRouter(prefix="/mcp-servers", tags=["MCP Servers"])

# How long Start waits for the server to connect and list its tools.
CONNECT_TIMEOUT_S = 10.0


async def _connect(server: MCPServer) -> None:
    """Connect now and record the outcome (status + discovered tools) on the row."""
    await mcp_manager.connect_server(server)
    tools = await mcp_manager.wait_connected(server.id, CONNECT_TIMEOUT_S)
    if tools is not None:
        server.status = "running"
        server.tools = [{"name": t["name"], "description": t.get("description")} for t in tools]
    elif mcp_manager.is_connecting(server.id):
        server.status = "starting"  # still connecting; agents get its tools once it's up
    else:
        server.status = "error"
        server.tools = []


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
async def update_mcp_server(
    server_id: str, server_in: MCPServerUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a specific MCP server."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    update_data = server_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)

    if server.is_active:  # apply URL / header / command changes to the live session
        await mcp_manager.disconnect_server(server.id)
        await _connect(server)

    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}")
async def delete_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a specific MCP server."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    await mcp_manager.disconnect_server(server.id)
    await db.delete(server)
    await db.commit()
    return {"message": "MCP Server deleted successfully"}


@router.post("/{server_id}/start")
async def start_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Start an MCP server: mark it active and connect now (no backend restart needed)."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    server.is_active = True
    await _connect(server)
    await db.commit()
    await db.refresh(server)
    if server.status == "error":
        return {
            "message": f"MCP Server '{server.name}' failed to connect; check its URL, "
            "headers or command and the backend logs",
            "status": "error",
        }
    return {"message": f"MCP Server '{server.name}' {server.status}", "status": server.status}


@router.post("/{server_id}/stop")
async def stop_mcp_server(server_id: str, db: AsyncSession = Depends(get_db)):
    """Stop an MCP server: disconnect it and mark it inactive."""
    server = await db.get(MCPServer, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server not found")

    await mcp_manager.disconnect_server(server.id)
    server.is_active = False
    server.status = "stopped"
    await db.commit()
    await db.refresh(server)
    return {"message": f"MCP Server '{server.name}' stopped", "status": "stopped"}
