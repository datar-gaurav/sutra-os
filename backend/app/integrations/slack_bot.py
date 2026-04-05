"""Slack Bot integration using Slack Bolt (Python)."""

import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.orchestrator import orchestrator

logger = logging.getLogger(__name__)

# Initialize Slack Bolt app (only if tokens are configured)
slack_app: AsyncApp | None = None

if settings.slack_bot_token and settings.slack_signing_secret:
    slack_app = AsyncApp(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )


def setup_slack_handlers(app: AsyncApp):
    """Register all Slack event handlers and slash commands."""

    # ─── Slash Commands ───────────────────────────────────────────────────────

    @app.command("/ask")
    async def handle_ask(ack, command, say):
        """Ask an agent a question: /ask [agent-name] <message>"""
        await ack()
        text = command.get("text", "").strip()
        if not text:
            await say("Usage: `/ask [agent-name] <your question>`")
            return

        # Parse agent name and message
        parts = text.split(maxsplit=1)
        
        agent_id = None
        agent_name = None
        message = ""

        # Check if the first word matches a running agent
        if len(parts) >= 1:
            potential_name = parts[0]
            for aid in agent_manager.get_running_agents():
                entry = agent_manager._running_agents.get(aid, {})
                config = entry.get("config", {})
                if config.get("name", "").lower() == potential_name.lower():
                    agent_id = aid
                    agent_name = config.get("name")
                    # If there's a second part, it's the message. Otherwise, the whole thing was just the agent name (which is an error, no question asked)
                    if len(parts) > 1:
                        message = parts[1]
                    break
        
        # If no agent matched the first word, treat the entire text as the message and use a default agent
        if not agent_id:
            running = agent_manager.get_running_agents()
            if not running:
                await say("❌ No agents are currently running. Start one from the dashboard.")
                return
            
            # First, try to find an agent named "James" (case-insensitive)
            for aid in running:
                entry = agent_manager._running_agents.get(aid, {})
                config = entry.get("config", {})
                if config.get("name", "").lower() == "james":
                    agent_id = aid
                    agent_name = config.get("name")
                    break
            
            # If "James" is not found, default to the first running agent
            if not agent_id:
                agent_id = running[0]
                entry = agent_manager._running_agents.get(agent_id, {})
                agent_name = entry.get("config", {}).get("name", "Default Agent")
                
            message = text # The whole text is the message

        if not message:
             await say(f"Usage: `/ask {agent_name} <your question>`")
             return

        # Post initial message
        result_msg = await say(f"🤖 *{agent_name}* is thinking...")

        # Get response
        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=message,
        )

        # Update the message with the response
        try:
            await app.client.chat_update(
                channel=command["channel_id"],
                ts=result_msg["ts"],
                text=f"🤖 *{agent_name}*:\n\n{response['output']}",
            )
        except Exception as e:
            logger.error(f"Failed to update Slack message: {e}")
            await say(f"🤖 *{agent_name}*:\n\n{response['output']}")

    @app.command("/agents")
    async def handle_agents(ack, command, say):
        """List all running agents: /agents"""
        await ack()
        running = agent_manager.get_running_agents()

        if not running:
            await say("No agents are currently running. Start one from the dashboard.")
            return

        lines = ["*Running Agents:*\n"]
        for aid in running:
            entry = agent_manager._running_agents.get(aid, {})
            config = entry.get("config", {})
            name = config.get("name", "Unknown")
            model = config.get("llm_model", "Unknown")
            lines.append(f"• 🟢 *{name}* — `{model}`")

        await say("\n".join(lines))

    @app.command("/status")
    async def handle_status(ack, command, say):
        """Show system status: /status"""
        await ack()
        running_count = len(agent_manager.get_running_agents())
        await say(
            f"*Sutra Status*\n"
            f"• Running agents: {running_count}\n"
            f"• Status: 🟢 Operational"
        )

    # ─── Direct Messages ──────────────────────────────────────────────────────

    @app.event("message")
    async def handle_dm(event, say):
        """Handle direct messages — route to the default agent."""
        # Skip bot messages
        if event.get("bot_id") or event.get("subtype"):
            return

        text = event.get("text", "").strip()
        if not text:
            return

        # Find the first running agent as default
        running = agent_manager.get_running_agents()
        if not running:
            await say("No agents are running. Please start one from the dashboard.")
            return

        agent_id = running[0]
        entry = agent_manager._running_agents.get(agent_id, {})
        agent_name = entry.get("config", {}).get("name", "Agent")

        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=text,
        )

        await say(
            text=f"🤖 *{agent_name}*:\n\n{response['output']}",
            thread_ts=event.get("ts"),  # Reply in thread
        )

    # ─── App Mention ──────────────────────────────────────────────────────────

    @app.event("app_mention")
    async def handle_mention(event, say):
        """Handle @sutra mentions in channels."""
        text = event.get("text", "")
        # Remove the bot mention
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not text:
            await say("Hi! Use `/ask <agent-name> <question>` or DM me.", thread_ts=event["ts"])
            return

        running = agent_manager.get_running_agents()
        if not running:
            await say("No agents are running.", thread_ts=event["ts"])
            return

        agent_id = running[0]
        entry = agent_manager._running_agents.get(agent_id, {})
        agent_name = entry.get("config", {}).get("name", "Agent")

        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=text,
        )

        await say(
            text=f"🤖 *{agent_name}*:\n\n{response['output']}",
            thread_ts=event["ts"],
        )


async def start_slack_bot():
    """Start the Slack bot in Socket Mode."""
    if not slack_app:
        logger.warning("Slack bot not configured. Set SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET.")
        return

    if not settings.slack_app_token:
        logger.warning("SLACK_APP_TOKEN not set. Socket Mode requires an app-level token.")
        return

    setup_slack_handlers(slack_app)

    handler = AsyncSocketModeHandler(slack_app, settings.slack_app_token)
    logger.info("Starting Slack bot in Socket Mode...")
    await handler.start_async()
