"""MCP servers work with both mcp 1.x and 2.x client APIs, and their tools reach agents."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core import mcp_manager as mm
from app.tools import registry

SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
    "required": ["query"],
}


def _fake_session_cls(schema_attr: str):
    class _FakeSession:
        def __init__(self, read, write):
            self.streams = (read, write)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            pass

        async def list_tools(self):
            tool = SimpleNamespace(
                name="recall", description="Recall memories", **{schema_attr: SCHEMA}
            )
            return SimpleNamespace(tools=[tool])

    return _FakeSession


# mcp 2.x: client yields (read, write), Tool.input_schema
# mcp 1.x: client yields (read, write, get_session_id), Tool.inputSchema
@pytest.mark.parametrize(
    "yielded,schema_attr",
    [(("r", "w"), "input_schema"), (("r", "w", lambda: "sid"), "inputSchema")],
    ids=["mcp2", "mcp1"],
)
async def test_streamable_http_session_discovers_tools(yielded, schema_attr):
    seen = {}

    @asynccontextmanager
    async def fake_client(url, http_client):
        seen["url"] = url
        seen["auth"] = http_client.headers.get("Authorization")
        yield yielded

    server = SimpleNamespace(
        id="c43480e9-0000-0000-0000-000000000000",
        name="Engram",
        transport_type="streamable_http",
        url="http://host.docker.internal:8100/mcp",
        headers={"Authorization": "Bearer t0ken"},
    )
    manager = mm.MCPManager()
    with (
        patch.object(mm, "streamable_http_client", fake_client),
        patch.object(mm, "ClientSession", _fake_session_cls(schema_attr)),
    ):
        task = asyncio.create_task(manager._run_sse_session(server))
        for _ in range(100):
            if manager._tools.get(server.id):
                break
            await asyncio.sleep(0.01)
        assert manager._tools[server.id] == [
            {"name": "recall", "description": "Recall memories", "input_schema": SCHEMA}
        ]
        assert manager._sessions[server.id].streams == ("r", "w")

        # The catalog id the UI stores on an agent must resolve to a LangChain tool.
        [meta] = manager.get_all_mcp_tools_metadata()
        assert meta["id"] == "mcp_c43480e9_recall"
        with patch.object(registry, "mcp_manager", manager):
            [tool] = registry.get_tools_by_ids([meta["id"]])
        assert tool.name == "mcp_c43480e9_recall"
        assert set(tool.args) == {"query", "limit"}

        manager._sessions.pop(server.id)  # ends the keep-alive loop
        await asyncio.wait_for(task, 5)

    assert seen == {"url": "http://host.docker.internal:8100/mcp", "auth": "Bearer t0ken"}
    assert server.id not in manager._tools


# ─── Start / stop lifecycle (no backend restart needed) ─────────────────────


def _row(**kw):
    base = dict(
        id="srv-2",
        name="Engram",
        transport_type="streamable_http",
        command=None,
        args=None,
        url="http://host.docker.internal:8100/mcp",
        env_vars=None,
        headers={"Authorization": "Bearer t0ken"},
        is_active=False,
        status="stopped",
        tools=[],
    )
    return SimpleNamespace(**{**base, **kw})


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.commits = 0

    async def get(self, model, server_id):
        return self.row if server_id == self.row.id else None

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self.row = SimpleNamespace(id=None)


def _patched_manager(fail=False):
    manager = mm.MCPManager()
    starts = []

    async def fake_session(server):
        starts.append(server.id)
        if fail:
            raise ConnectionError("refused")
        manager._sessions[server.id] = object()
        manager._tools[server.id] = [
            {"name": "recall", "description": "Recall", "input_schema": {}}
        ]
        try:
            while server.id in manager._sessions:
                await asyncio.sleep(0.01)
        finally:
            manager._sessions.pop(server.id, None)
            manager._tools.pop(server.id, None)

    manager._run_sse_session = fake_session
    return manager, starts


async def test_start_connects_now_and_stop_disconnects():
    from app.api.routes import mcp_servers as routes

    manager, starts = _patched_manager()
    db = _FakeDB(_row())
    with patch.object(routes, "mcp_manager", manager):
        out = await routes.start_mcp_server("srv-2", db)
        assert out["status"] == "running"
        assert db.row.is_active and db.row.status == "running"
        assert db.row.tools == [{"name": "recall", "description": "Recall"}]
        assert manager.get_all_mcp_tools_metadata()[0]["id"] == "mcp_srv-2_recall"

        await routes.start_mcp_server("srv-2", db)  # second Start reuses the session
        assert starts == ["srv-2"]

        out = await routes.stop_mcp_server("srv-2", db)
        assert out["status"] == "stopped" and not db.row.is_active
        assert manager.get_all_mcp_tools_metadata() == []
        assert "srv-2" not in manager._tasks


async def test_start_reports_connection_failure():
    from app.api.routes import mcp_servers as routes

    manager, _ = _patched_manager(fail=True)
    db = _FakeDB(_row())
    with patch.object(routes, "mcp_manager", manager):
        out = await routes.start_mcp_server("srv-2", db)
    assert out["status"] == "error" and db.row.status == "error" and db.row.tools == []
