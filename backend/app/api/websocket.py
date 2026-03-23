"""WebSocket handler for real-time agent status and chat streaming."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.agent_manager import agent_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]):
        """Broadcast a message to all connected clients."""
        data = json.dumps(message)
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.active_connections.remove(conn)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]):
        """Send a message to a specific client."""
        await websocket.send_text(json.dumps(message))


ws_manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time updates."""
    await ws_manager.connect(websocket)

    try:
        # Send initial state
        running = agent_manager.get_running_agents()
        await ws_manager.send_to(websocket, {
            "type": "init",
            "running_agents": running,
        })

        # Listen for messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await ws_manager.send_to(websocket, {"type": "pong"})
            elif message.get("type") == "subscribe_agent":
                # Client wants updates for a specific agent
                agent_id = message.get("agent_id")
                status = agent_manager.get_agent_status(agent_id)
                await ws_manager.send_to(websocket, {
                    "type": "agent_status",
                    "agent_id": agent_id,
                    "status": status,
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


async def broadcast_agent_event(event_type: str, agent_id: str, data: dict | None = None):
    """Broadcast an agent event to all connected WebSocket clients."""
    await ws_manager.broadcast({
        "type": event_type,
        "agent_id": agent_id,
        "data": data or {},
    })
