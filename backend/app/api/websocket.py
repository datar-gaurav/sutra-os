"""WebSocket handler for real-time agent status and chat streaming."""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.agent_manager import agent_manager
from app.core.security import decode_token

logger = logging.getLogger(__name__)

# Rate limit: max messages per connection per window
_WS_RATE_LIMIT = 30        # messages
_WS_RATE_WINDOW = 10.0     # seconds


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
    """Main WebSocket endpoint for real-time updates.

    Requires a valid JWT token passed as a query parameter: /ws?token=<jwt>
    """
    # ── Authenticate before accepting the connection ──
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
    except Exception:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    await ws_manager.connect(websocket)

    try:
        # Send initial state
        running = agent_manager.get_running_agents()
        await ws_manager.send_to(websocket, {
            "type": "init",
            "running_agents": running,
        })

        # Listen for messages (rate-limited)
        msg_timestamps: list[float] = []
        while True:
            data = await websocket.receive_text()

            # Sliding-window rate limit
            now = time.monotonic()
            msg_timestamps = [t for t in msg_timestamps if now - t < _WS_RATE_WINDOW]
            if len(msg_timestamps) >= _WS_RATE_LIMIT:
                await ws_manager.send_to(websocket, {"type": "error", "message": "Rate limit exceeded"})
                continue
            msg_timestamps.append(now)

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
