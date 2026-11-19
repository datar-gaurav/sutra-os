"""Streamable HTTP MCP sessions work with both mcp 1.x and 2.x client APIs."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core import mcp_manager as mm


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
            name="recall", description="Recall memories", inputSchema={"type": "object"}
        )
        return SimpleNamespace(tools=[tool])


@pytest.mark.parametrize("yielded", [("r", "w"), ("r", "w", lambda: "sid")], ids=["mcp2", "mcp1"])
async def test_streamable_http_session_discovers_tools(yielded):
    seen = {}

    @asynccontextmanager
    async def fake_client(url, http_client):
        seen["url"] = url
        seen["auth"] = http_client.headers.get("Authorization")
        yield yielded

    server = SimpleNamespace(
        id="srv-1",
        name="Engram",
        transport_type="streamable_http",
        url="http://host.docker.internal:8100/mcp",
        headers={"Authorization": "Bearer t0ken"},
    )
    manager = mm.MCPManager()
    with (
        patch.object(mm, "streamable_http_client", fake_client),
        patch.object(mm, "ClientSession", _FakeSession),
    ):
        task = asyncio.create_task(manager._run_sse_session(server))
        for _ in range(100):
            if manager._tools.get("srv-1"):
                break
            await asyncio.sleep(0.01)
        assert [t["name"] for t in manager._tools["srv-1"]] == ["recall"]
        assert manager._sessions["srv-1"].streams == ("r", "w")
        manager._sessions.pop("srv-1")  # ends the keep-alive loop
        await asyncio.wait_for(task, 5)

    assert seen == {"url": "http://host.docker.internal:8100/mcp", "auth": "Bearer t0ken"}
    assert "srv-1" not in manager._tools
