"""WebSocket handler for real-time agent status and event delivery.

Delivery is scoped per connection. A client receives an event only if it has
subscribed to that event type, optionally narrowed by a filter:

    {"type": "subscribe", "events": ["forge_update"], "filter": {"forge_request_id": "f1"}}
    {"type": "unsubscribe", "events": ["forge_update"]}

The wildcard event "*" (every event) is limited to owner and admin roles.
Connections are closed when the access token they were opened with expires,
so a leaked token cannot listen indefinitely; clients reconnect with a fresh one.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.agent_manager import agent_manager
from app.core.security import decode_token

logger = logging.getLogger(__name__)

# Rate limit: max messages per connection per window
_WS_RATE_LIMIT = 30        # messages
_WS_RATE_WINDOW = 10.0     # seconds

WILDCARD = "*"
_WILDCARD_ROLES = {"owner", "admin"}
_MAX_SUBSCRIPTIONS = 100   # per connection

# Close codes (4000–4999 are application-defined)
CLOSE_MISSING_TOKEN = 4001
CLOSE_INVALID_TOKEN = 4003
CLOSE_TOKEN_EXPIRED = 4401


@dataclass
class Connection:
    websocket: WebSocket
    user_id: str
    role: str
    expires_at: float  # unix timestamp of the access token's exp
    # event type -> filters; None in the list means "no filter" (all of that type)
    subscriptions: dict[str, list[dict[str, Any] | None]] = field(default_factory=dict)

    def subscribe(self, event: str, filter_: dict[str, Any] | None) -> None:
        filters = self.subscriptions.setdefault(event, [])
        if filter_ not in filters:
            filters.append(filter_)

    def unsubscribe(self, event: str) -> None:
        self.subscriptions.pop(event, None)

    def subscription_count(self) -> int:
        return sum(len(f) for f in self.subscriptions.values())

    def wants(self, message: dict[str, Any]) -> bool:
        event = message.get("type")
        filters = self.subscriptions.get(event, []) + self.subscriptions.get(WILDCARD, [])
        return any(f is None or _matches(f, message) for f in filters)


def _matches(filter_: dict[str, Any], message: dict[str, Any]) -> bool:
    """Every filter key must equal the message's value, top level or under "data"."""
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    for key, expected in filter_.items():
        actual = message[key] if key in message else data.get(key)
        if actual != expected:
            return False
    return True


class ConnectionManager:
    """Tracks WebSocket connections and their subscriptions."""

    def __init__(self):
        self.connections: dict[WebSocket, Connection] = {}

    async def connect(self, conn: Connection):
        await conn.websocket.accept()
        self.connections[conn.websocket] = conn
        logger.info("WebSocket connected. Total: %d", len(self.connections))

    def disconnect(self, websocket: WebSocket):
        if self.connections.pop(websocket, None) is not None:
            logger.info("WebSocket disconnected. Total: %d", len(self.connections))

    async def broadcast(self, message: dict[str, Any]):
        """Send an event to every connection subscribed to its type."""
        data = json.dumps(message)
        for conn in list(self.connections.values()):
            if not conn.wants(message):
                continue
            try:
                await conn.websocket.send_text(data)
            except Exception:
                self.disconnect(conn.websocket)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]):
        """Send a message to a specific client."""
        await websocket.send_text(json.dumps(message))


ws_manager = ConnectionManager()


async def _authenticate(token: str | None) -> tuple[str, str, float] | int:
    """Return (user_id, role, exp) for a valid access token, or a close code."""
    if not token:
        return CLOSE_MISSING_TOKEN
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
    except Exception:
        return CLOSE_INVALID_TOKEN

    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.user import User

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if not user or not user.is_active:
        return CLOSE_INVALID_TOKEN
    return user.id, user.role.value, float(payload["exp"])


async def handle_client_message(conn: Connection, message: dict[str, Any]) -> dict[str, Any] | None:
    """Apply one client message and return the reply to send, if any."""
    kind = message.get("type")

    if kind == "ping":
        return {"type": "pong"}

    if kind in ("subscribe", "unsubscribe"):
        events = message.get("events")
        if not isinstance(events, list) or not all(isinstance(e, str) and e for e in events):
            return {"type": "error", "message": "events must be a list of event names"}

        if kind == "unsubscribe":
            for event in events:
                conn.unsubscribe(event)
            return {"type": "unsubscribed", "events": events}

        filter_ = message.get("filter")
        if filter_ is not None and not isinstance(filter_, dict):
            return {"type": "error", "message": "filter must be an object"}
        if WILDCARD in events and conn.role not in _WILDCARD_ROLES:
            return {"type": "error", "message": "Subscribing to all events requires owner or admin"}
        if conn.subscription_count() + len(events) > _MAX_SUBSCRIPTIONS:
            return {"type": "error", "message": "Too many subscriptions"}
        for event in events:
            conn.subscribe(event, filter_ or None)
        return {"type": "subscribed", "events": events, "filter": filter_ or None}

    if kind == "subscribe_agent":
        agent_id = message.get("agent_id")
        return {
            "type": "agent_status",
            "agent_id": agent_id,
            "status": agent_manager.get_agent_status(agent_id),
        }

    return None


async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time updates.

    Requires a valid JWT access token as a query parameter: /ws?token=<jwt>
    """
    auth = await _authenticate(websocket.query_params.get("token"))
    if isinstance(auth, int):
        reason = "Missing authentication token" if auth == CLOSE_MISSING_TOKEN else "Invalid or expired token"
        await websocket.close(code=auth, reason=reason)
        return

    user_id, role, expires_at = auth
    conn = Connection(websocket=websocket, user_id=user_id, role=role, expires_at=expires_at)
    await ws_manager.connect(conn)

    try:
        await ws_manager.send_to(websocket, {
            "type": "init",
            "running_agents": agent_manager.get_running_agents(),
        })

        msg_timestamps: list[float] = []
        while True:
            remaining = conn.expires_at - time.time()
            if remaining <= 0:
                await websocket.close(code=CLOSE_TOKEN_EXPIRED, reason="Token expired")
                break
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except asyncio.TimeoutError:
                continue  # loop re-checks expiry and closes

            # Sliding-window rate limit
            now = time.monotonic()
            msg_timestamps = [t for t in msg_timestamps if now - t < _WS_RATE_WINDOW]
            if len(msg_timestamps) >= _WS_RATE_LIMIT:
                await ws_manager.send_to(websocket, {"type": "error", "message": "Rate limit exceeded"})
                continue
            msg_timestamps.append(now)

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await ws_manager.send_to(websocket, {"type": "error", "message": "Invalid JSON"})
                continue
            if not isinstance(message, dict):
                continue

            reply = await handle_client_message(conn, message)
            if reply is not None:
                await ws_manager.send_to(websocket, reply)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        ws_manager.disconnect(websocket)


async def broadcast_agent_event(event_type: str, agent_id: str, data: dict | None = None):
    """Send an agent event to clients subscribed to that event type."""
    await ws_manager.broadcast({
        "type": event_type,
        "agent_id": agent_id,
        "data": data or {},
    })
