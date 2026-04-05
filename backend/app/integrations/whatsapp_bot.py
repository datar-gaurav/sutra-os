"""WhatsApp Bot integration using pywa (WhatsApp Cloud API wrapper)."""

import logging
import re

from pywa_async import WhatsApp
from pywa.types import Message as WAMessage

from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.orchestrator import orchestrator

logger = logging.getLogger(__name__)


def _find_agent_by_name(name: str) -> tuple[str | None, str | None]:
    """Find a running agent by name (case-insensitive). Returns (agent_id, agent_name)."""
    for aid in agent_manager.get_running_agents():
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        if config.get("name", "").lower() == name.lower():
            return aid, config.get("name")
    return None, None


def _get_default_agent() -> tuple[str | None, str | None]:
    """Get the first running agent. Returns (agent_id, agent_name)."""
    running = agent_manager.get_running_agents()
    if not running:
        return None, None
    aid = running[0]
    entry = agent_manager._running_agents.get(aid, {})
    name = entry.get("config", {}).get("name", "Agent")
    return aid, name


def setup_whatsapp(fastapi_app) -> WhatsApp | None:
    """Create and configure the WhatsApp client, attaching webhook routes to FastAPI."""
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        logger.warning(
            "WhatsApp not configured. Set WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID."
        )
        return None

    wa = WhatsApp(
        phone_id=settings.whatsapp_phone_number_id,
        token=settings.whatsapp_access_token,
        server=fastapi_app,
        verify_token=settings.whatsapp_verify_token,
        callback_url=None,
        webhook_endpoint="/api/whatsapp/webhook",
        app_id=None,
        app_secret=None,
        business_account_id=None,
        validate_updates=False,
    )

    # ─── Message Handler ──────────────────────────────────────────────────────

    @wa.on_message()
    async def handle_message(client: WhatsApp, msg: WAMessage):
        """Handle incoming WhatsApp messages."""
        text = (msg.text or "").strip()
        if not text:
            return

        is_group = msg.is_from_group if hasattr(msg, "is_from_group") else False

        if is_group:
            await _handle_group_message(client, msg, text)
        else:
            await _handle_dm(client, msg, text)

    async def _handle_dm(client: WhatsApp, msg: WAMessage, text: str):
        """Route DMs — supports @AgentName targeting or falls back to default agent."""
        agent_id, agent_name = None, None
        message = text

        # Check for @AgentName prefix
        match = re.match(r"@(\S+)\s+(.*)", text, re.DOTALL)
        if match:
            query = match.group(1)
            agent_id, agent_name = _find_agent_by_name(query)
            # Try partial match
            if not agent_id:
                for aid in agent_manager.get_running_agents():
                    entry = agent_manager._running_agents.get(aid, {})
                    config = entry.get("config", {})
                    name = config.get("name", "")
                    if name.lower().startswith(query.lower()):
                        agent_id = aid
                        agent_name = name
                        break
            if agent_id:
                message = match.group(2).strip()

        # Fall back to default agent if no @tag or agent not found
        if not agent_id:
            agent_id, agent_name = _get_default_agent()

        if not agent_id:
            await msg.reply_text("❌ No agents are currently running. Please start one from the dashboard.")
            return

        await msg.mark_as_read()

        try:
            response = await orchestrator.route_message(
                agent_id=agent_id,
                message=message,
            )
            reply = f"🤖 *{agent_name}*:\n\n{response['output']}"
        except Exception as e:
            logger.error(f"WhatsApp DM error: {e}")
            reply = f"⚠️ Something went wrong while processing your message."

        await msg.reply_text(reply)

    async def _handle_group_message(client: WhatsApp, msg: WAMessage, text: str):
        """Handle group messages — only respond when an agent is @mentioned."""
        # Look for @AgentName pattern at the start of the message
        match = re.match(r"@(\S+)\s+(.*)", text, re.DOTALL)
        if not match:
            return  # No @mention — ignore to avoid spamming the group

        agent_name_query = match.group(1)
        message = match.group(2).strip()

        if not message:
            return

        agent_id, agent_name = _find_agent_by_name(agent_name_query)
        if not agent_id:
            # Try partial match
            for aid in agent_manager.get_running_agents():
                entry = agent_manager._running_agents.get(aid, {})
                config = entry.get("config", {})
                name = config.get("name", "")
                if name.lower().startswith(agent_name_query.lower()):
                    agent_id = aid
                    agent_name = name
                    break

        if not agent_id:
            await msg.reply_text(
                f"❌ No running agent named *{agent_name_query}*.\n"
                f"Use @AgentName to tag a running agent."
            )
            return

        await msg.mark_as_read()

        try:
            response = await orchestrator.route_message(
                agent_id=agent_id,
                message=message,
            )
            reply = f"🤖 *{agent_name}*:\n\n{response['output']}"
        except Exception as e:
            logger.error(f"WhatsApp group error: {e}")
            reply = f"⚠️ Something went wrong while processing your message."

        await msg.reply_text(reply)

    logger.info("✅ WhatsApp webhook handlers registered.")
    return wa
