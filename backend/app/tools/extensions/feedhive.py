"""FeedHive extension for Sutra OS.

Drop this file into backend/app/tools/extensions/ and configure
via the Integrations page with your FeedHive API key.

Obtain your API key from FeedHive Settings > Account (starts with fh_).

Provides two tools:
  - feedhive_list_triggers: List all available FeedHive triggers/automations
  - feedhive_run_trigger:   Execute a specific trigger by its ID with arguments
"""

import json
from typing import Any

import httpx
from langchain_core.tools import tool

EXTENSION_MANIFEST = {
    "id": "feedhive",
    "name": "FeedHive",
    "description": "List and execute FeedHive social media triggers and automations via MCP",
    "icon": "rss",
    "version": "1.0.0",
    "author": "Sutra Community",
    "credential_fields": [
        {
            "key": "api_key",
            "label": "API Key",
            "secret": True,
            "placeholder": "fh_...",
        },
    ],
    "config_fields": [],
    "tool_ids": [
        "feedhive_list_triggers",
        "feedhive_run_trigger",
    ],
}

_MCP_URL = "https://mcp.feedhive.com"
_MCP_PROTOCOL = "2024-11-05"


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def _mcp_request(api_key: str, method: str, params: dict | None = None) -> Any:
    headers = _build_headers(api_key)

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Initialize session
        init_resp = await client.post(
            _MCP_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "sutra-os", "version": "1.0"},
                },
            },
        )
        init_resp.raise_for_status()

        # 2. Attach session ID to all subsequent requests (required by Streamable HTTP spec)
        session_id = init_resp.headers.get("Mcp-Session-Id")
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        # 3. Confirm initialization (server won't process tool calls without this)
        await client.post(
            _MCP_URL,
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

        # 4. Make the actual request
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params

        resp = await client.post(_MCP_URL, headers=headers, json=payload)
        resp.raise_for_status()

    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"FeedHive MCP error {body['error'].get('code')}: {body['error'].get('message')}")
    return body.get("result")


def create_tools(agent_id: str):
    from app.tools.extensions._helpers import get_extension_creds

    async def _api_key() -> str:
        creds, _ = await get_extension_creds("feedhive", agent_id)
        return creds["api_key"]

    @tool
    async def feedhive_list_triggers() -> str:
        """List all available FeedHive triggers and automations.

        Returns a table of trigger IDs and descriptions that can be passed
        to feedhive_run_trigger to execute them.
        """
        key = await _api_key()
        result = await _mcp_request(key, "tools/list")
        tools_list = result.get("tools", [])
        if not tools_list:
            return "No FeedHive triggers found."

        lines = [f"Found {len(tools_list)} trigger(s):\n"]
        for t in tools_list:
            name = t.get("name", "")
            trigger_id = name.removeprefix("trigger_")
            desc = t.get("description") or "(no description)"
            # Summarise required input fields
            props = t.get("inputSchema", {}).get("properties", {})
            req = t.get("inputSchema", {}).get("required", [])
            field_summary = ", ".join(
                f"{k}{'*' if k in req else ''}" for k in props
            )
            lines.append(f"• ID: {trigger_id}")
            lines.append(f"  Description: {desc}")
            if field_summary:
                lines.append(f"  Fields (* = required): {field_summary}")
            lines.append("")
        return "\n".join(lines)

    @tool
    async def feedhive_run_trigger(trigger_id: str, arguments: str = "{}") -> str:
        """Execute a FeedHive trigger/automation by its ID.

        Args:
            trigger_id: The trigger ID (from feedhive_list_triggers, without the 'trigger_' prefix).
            arguments: JSON string of arguments required by the trigger schema, e.g. '{"key": "value"}'.
        """
        key = await _api_key()
        try:
            args = json.loads(arguments)
        except json.JSONDecodeError as e:
            return f"Invalid arguments JSON: {e}"

        tool_name = f"trigger_{trigger_id}"
        result = await _mcp_request(
            key,
            "tools/call",
            {"name": tool_name, "arguments": args},
        )

        content = result.get("content", [])
        if not content:
            return f"Trigger '{trigger_id}' executed with no output."

        parts = []
        for item in content:
            if item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item))
        return "\n".join(parts) or f"Trigger '{trigger_id}' executed successfully."

    return [feedhive_list_triggers, feedhive_run_trigger]


async def test_connection(creds: dict, config: dict) -> dict:
    """Validate FeedHive credentials by listing available triggers."""
    api_key = creds.get("api_key", "")
    if not api_key.startswith("fh_"):
        return {"ok": False, "detail": "API key must start with 'fh_'. Get yours from FeedHive Settings > Account."}
    try:
        result = await _mcp_request(api_key, "tools/list")
        count = len(result.get("tools", []))
        return {"ok": True, "detail": f"Connected — {count} trigger(s) available."}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"ok": False, "detail": "Invalid API key — 401 Unauthorized."}
        return {"ok": False, "detail": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "detail": f"Connection failed: {e}"}
