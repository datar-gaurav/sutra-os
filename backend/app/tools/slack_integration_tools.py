"""Slack integration tools — post messages and list channels via the Slack API.

Note: This is separate from the Slack bot integration (socket mode) used for inbound
messages from Slack. These tools allow agents to programmatically post to Slack channels
using a stored integration credential.
"""

from __future__ import annotations

import json
import logging

import httpx
from langchain_core.tools import tool

from app.core.vault import decrypt_secret

logger = logging.getLogger(__name__)

SLACK_INTEGRATION_TOOL_IDS = {"slack_post_message", "slack_list_channels"}


async def _get_slack_creds(agent_id: str) -> tuple[dict, dict]:
    from app.db.session import async_session_factory
    from app.models.integration import Integration
    from sqlalchemy import select, nullslast

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "slack", Integration.is_active == True)
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row or not row.credentials_enc:
        raise ValueError("No active Slack integration found")
    creds = json.loads(decrypt_secret(row.credentials_enc))
    return creds, row.extra_config or {}


def create_slack_integration_tools(agent_id: str):
    @tool
    async def slack_post_message(
        message: str,
        channel: str = "",
    ) -> str:
        """Post a message to a Slack channel.

        Args:
            message: The message text (supports Slack mrkdwn formatting).
            channel: Channel ID or name (e.g. '#general' or 'C0123456'). Falls back to integration default.
        """
        creds, cfg = await _get_slack_creds(agent_id)
        ch = channel or cfg.get("default_channel", "")
        if not ch:
            raise ValueError("channel is required (or set a default_channel in the integration config)")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {creds['bot_token']}",
                    "Content-Type": "application/json",
                },
                json={"channel": ch, "text": message},
            )
            resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Slack error: {data.get('error', 'unknown')}")
        ts = data.get("ts", "")
        return f"Message posted to {ch} (ts: {ts})"

    @tool
    async def slack_list_channels(
        limit: int = 50,
        types: str = "public_channel",
    ) -> str:
        """List available Slack channels.

        Args:
            limit: Maximum number of channels to return.
            types: Channel types to include: 'public_channel', 'private_channel', 'mpim', 'im'.
        """
        creds, _ = await _get_slack_creds(agent_id)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://slack.com/api/conversations.list",
                headers={"Authorization": f"Bearer {creds['bot_token']}"},
                params={"limit": limit, "types": types},
            )
            resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise ValueError(f"Slack error: {data.get('error', 'unknown')}")
        channels = data.get("channels", [])
        lines = []
        for ch in channels:
            name = ch.get("name", ch.get("id", "?"))
            ch_id = ch.get("id", "")
            members = ch.get("num_members", "?")
            is_private = ch.get("is_private", False)
            lines.append(f"#{name} (id: {ch_id}, members: {members}{'🔒' if is_private else ''})")
        return "\n".join(lines) if lines else "No channels found."

    return [slack_post_message, slack_list_channels]
