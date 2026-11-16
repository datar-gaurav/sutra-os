"""WebSocket delivery is scoped to each connection's subscriptions."""

from unittest.mock import AsyncMock, MagicMock

from app.api.websocket import Connection, ConnectionManager, handle_client_message


def _conn(role: str = "owner") -> Connection:
    ws = MagicMock()
    ws.send_text = AsyncMock()
    return Connection(websocket=ws, user_id="u1", role=role, expires_at=9e9)


async def _setup(*conns: Connection) -> ConnectionManager:
    mgr = ConnectionManager()
    for c in conns:
        mgr.connections[c.websocket] = c
    return mgr


async def test_unsubscribed_connection_receives_nothing():
    c = _conn()
    mgr = await _setup(c)
    await mgr.broadcast({"type": "approval_requested", "approval_id": "a1"})
    c.websocket.send_text.assert_not_called()


async def test_subscribed_event_type_is_delivered_others_are_not():
    c = _conn()
    await handle_client_message(c, {"type": "subscribe", "events": ["forge_update"]})
    mgr = await _setup(c)
    await mgr.broadcast({"type": "forge_update", "forge_request_id": "f1"})
    await mgr.broadcast({"type": "alert_fired", "data": {"id": "x"}})
    assert c.websocket.send_text.call_count == 1


async def test_filter_matches_top_level_and_data_fields():
    c = _conn()
    await handle_client_message(
        c, {"type": "subscribe", "events": ["forge_update"], "filter": {"forge_request_id": "f1"}}
    )
    await handle_client_message(
        c, {"type": "subscribe", "events": ["alert_fired"], "filter": {"agent_id": "a9"}}
    )
    mgr = await _setup(c)
    await mgr.broadcast({"type": "forge_update", "forge_request_id": "f2"})
    await mgr.broadcast({"type": "forge_update", "forge_request_id": "f1"})
    await mgr.broadcast({"type": "alert_fired", "data": {"agent_id": "a1"}})
    await mgr.broadcast({"type": "alert_fired", "data": {"agent_id": "a9"}})
    assert c.websocket.send_text.call_count == 2


async def test_wildcard_requires_owner_or_admin():
    op = _conn(role="operator")
    reply = await handle_client_message(op, {"type": "subscribe", "events": ["*"]})
    assert reply["type"] == "error"
    assert op.subscriptions == {}

    owner = _conn(role="owner")
    reply = await handle_client_message(owner, {"type": "subscribe", "events": ["*"]})
    assert reply["type"] == "subscribed"
    mgr = await _setup(owner)
    await mgr.broadcast({"type": "anything"})
    owner.websocket.send_text.assert_called_once()


async def test_unsubscribe_stops_delivery():
    c = _conn()
    await handle_client_message(c, {"type": "subscribe", "events": ["forge_update"]})
    await handle_client_message(c, {"type": "unsubscribe", "events": ["forge_update"]})
    mgr = await _setup(c)
    await mgr.broadcast({"type": "forge_update"})
    c.websocket.send_text.assert_not_called()


async def test_bad_subscribe_payload_rejected():
    c = _conn()
    assert (await handle_client_message(c, {"type": "subscribe", "events": "x"}))["type"] == "error"
    assert (
        await handle_client_message(c, {"type": "subscribe", "events": ["x"], "filter": [1]})
    )["type"] == "error"


async def test_failed_send_drops_connection_without_error():
    c = _conn()
    c.websocket.send_text = AsyncMock(side_effect=RuntimeError("gone"))
    await handle_client_message(c, {"type": "subscribe", "events": ["e"]})
    mgr = await _setup(c)
    await mgr.broadcast({"type": "e"})
    assert mgr.connections == {}
    mgr.disconnect(c.websocket)  # second disconnect is a no-op
