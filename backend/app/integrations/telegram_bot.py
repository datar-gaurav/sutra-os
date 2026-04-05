"""Telegram Bot integration using python-telegram-bot."""
import logging
import re
import asyncio
from typing import Any
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from sqlalchemy import select

# ConversationHandler states for forge feedback collection
FORGE_FEEDBACK = 1

from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.orchestrator import orchestrator
from app.db.session import async_session_factory
from app.models.conversation import Conversation, Message
from app.core.conversation_window import get_windowed_history

logger = logging.getLogger(__name__)


async def get_telegram_bot_token() -> str:
    """Return the Telegram bot token, preferring the DB vault over the .env setting."""
    try:
        from app.db.session import async_session_factory
        from app.models.env_var import EnvVar
        from app.core.vault import decrypt_secret
        async with async_session_factory() as db:
            row = await db.get(EnvVar, "TELEGRAM_BOT_TOKEN")
            if row and row.value:
                return decrypt_secret(row.value)
    except Exception:
        pass
    return settings.telegram_bot_token

def escape_markdown(text: str | Any) -> str:
    """Escape Telegram MarkdownV2 special characters.
    The following characters must be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if not text:
        return ""
    text_str = str(text)
    # The following characters must be escaped: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # We use a negative lookbehind to avoid escaping already escaped characters
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    pattern = f"(?<!\\\\)([{re.escape(escape_chars)}])"
    return re.sub(pattern, r"\\\1", text_str)

# Global reference to the application for outbound messages
_application: Any = None

def _find_agent_by_name(name: str) -> tuple[str | None, str | None]:
    """Find a running agent by name (case-insensitive). Returns (agent_id, agent_name)."""
    for aid in agent_manager.get_running_agents():
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        if config.get("name", "").lower() == name.lower():
            return aid, config.get("name")
    return None, None


async def _find_agent_by_chat_id(chat_id: str) -> tuple[str | None, str | None]:
    """Find a running agent whose telegram_chat_id matches this chat. Returns (agent_id, agent_name)."""
    from app.models.agent import Agent
    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.telegram_chat_id == chat_id,
                Agent.telegram_enabled == True,  # noqa: E712
            )
        )
        agent = result.scalar_one_or_none()
        if agent and agent_manager.is_running(agent.id):
            return agent.id, agent.name
    return None, None

def _get_default_agent() -> tuple[str | None, str | None]:
    """Get the default agent (prioritizing 'Dash', else the first running agent). Returns (agent_id, agent_name)."""
    running = agent_manager.get_running_agents()
    if not running:
        return None, None
        
    # First, look for Dash
    for aid in running:
        entry = agent_manager._running_agents.get(aid, {})
        name = entry.get("config", {}).get("name", "")
        if name.lower() == "dash":
            return aid, name

    # Fallback to the first running agent
    aid = running[0]
    entry = agent_manager._running_agents.get(aid, {})
    name = entry.get("config", {}).get("name", "Agent")
    return aid, name

async def _route_with_history(
    agent_id: str, agent_name: str, message: str, chat_id: str,
    project_id: str | None = None,
) -> dict:
    """Route a message to an agent with persistent conversation history and memory.

    Mirrors the chat API pattern: persists messages, loads windowed history,
    passes db for memory injection, and fires auto-extract memories.
    """
    async with async_session_factory() as db:
        # Get or create conversation for this chat+agent+project combination
        query = (
            select(Conversation)
            .where(
                Conversation.agent_id == agent_id,
                Conversation.source == "telegram",
                Conversation.source_id == str(chat_id),
            )
        )
        if project_id:
            query = query.where(Conversation.project_id == project_id)
        else:
            query = query.where(Conversation.project_id.is_(None))

        result = await db.execute(query.order_by(Conversation.updated_at.desc()).limit(1))
        conversation = result.scalar_one_or_none()
        if not conversation:
            title_parts = [f"Telegram: {agent_name}"]
            if project_id:
                from app.models.project import Project
                proj = await db.get(Project, project_id)
                if proj:
                    title_parts.append(f"[{proj.name}]")
            conversation = Conversation(
                agent_id=agent_id,
                title=" ".join(title_parts),
                source="telegram",
                source_id=str(chat_id),
                project_id=project_id,
            )
            db.add(conversation)
            await db.flush()

        # Save user message
        user_msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=message,
        )
        db.add(user_msg)
        await db.flush()

        # Load windowed history (excludes the message we just added)
        chat_history = await get_windowed_history(db, conversation.id, exclude_last=True)

        # Route to agent with history and db (enables memory injection)
        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=message,
            chat_history=chat_history,
            db=db,
        )

        # Save assistant response
        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response["output"],
            tool_calls=(
                {"steps": response.get("intermediate_steps", [])}
                if response.get("intermediate_steps")
                else None
            ),
        )
        db.add(assistant_msg)

        # Update conversation timestamp
        conversation.updated_at = datetime.now(timezone.utc)
        conv_id = conversation.id
        await db.commit()

    # Fire-and-forget: auto-extract memories
    try:
        info = agent_manager.get_info(agent_id) or {}
        asyncio.create_task(_auto_extract_memories_bg(
            agent_id=agent_id,
            user_message=message,
            assistant_response=response["output"],
            llm_provider=info.get("llm_provider", ""),
            llm_model=info.get("llm_model", ""),
            project_id=project_id,
            conversation_id=conv_id,
        ))
    except Exception:
        pass

    return response


async def _auto_extract_memories_bg(
    agent_id: str, user_message: str, assistant_response: str,
    llm_provider: str, llm_model: str,
    project_id: str | None = None,
    conversation_id: str | None = None,
):
    """Background: extract key facts from a conversation exchange."""
    try:
        from app.core.memory_service import memory_service
        async with async_session_factory() as db:
            await memory_service.auto_extract(
                db=db,
                agent_id=agent_id,
                user_message=user_message,
                assistant_response=assistant_response,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            # Auto-extract project decisions if project is active
            if project_id:
                try:
                    from app.core.project_memory_service import auto_extract_decisions
                    await auto_extract_decisions(
                        db=db,
                        project_id=project_id,
                        agent_id=agent_id,
                        user_message=user_message,
                        assistant_response=assistant_response,
                        llm_provider=llm_provider,
                        llm_model=llm_model,
                        conversation_id=conversation_id,
                    )
                except Exception:
                    pass
            await db.commit()
    except Exception as e:
        logger.warning(f"Memory auto-extract failed for agent {agent_id}: {e}")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Welcome to Sutra AI Telegram Bot!\n\n"
        "You can talk to authorized AI agents here.\n\n"
        "Commands:\n"
        "/switch [agent] - Switch active agent (keeps history per agent)\n"
        "/connect [agent] - Link this chat to an agent (persists to DB)\n"
        "/disconnect - Unlink this chat from its agent\n"
        "/agents - List running agents\n"
        "/ask [agent] [message] - Ask a specific agent\n"
        "/project [name] - Set active project context\n"
        "/project list - List available projects\n"
        "/newchat - Start a fresh conversation\n"
        "/status - Check system status\n"
        "/forge [description] - Build a feature autonomously\n\n"
        "Quick start: use /connect <agent-name> to link this chat to an agent, "
        "then just type normally to talk."
    )

async def agents_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /agents command."""
    running = agent_manager.get_running_agents()
    if not running:
        await update.message.reply_text("❌ No agents are currently running.")
        return

    text = "🟢 *Running Agents:*\n\n"
    for aid in running:
        entry = agent_manager._running_agents.get(aid, {})
        config = entry.get("config", {})
        name = escape_markdown(config.get("name", "Unknown"))
        model = escape_markdown(config.get("llm_model", "Unknown"))
        text += f"• *{name}* — `{model}`\n"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")

async def chatid_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /chatid — show the current chat's ID."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Chat ID: `{chat_id}`", parse_mode="MarkdownV2")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    running_count = len(agent_manager.get_running_agents())
    await update.message.reply_text(
        f"📊 *Sutra Status*\n"
        f"• Status: 🟢 Operational\n"
        f"• Running Agents: {running_count}",
        parse_mode="MarkdownV2"
    )

async def switch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /switch <agent-name> — switch the active agent for this chat (soft, no DB changes)."""
    if not context.args:
        # Show current active agent
        active_id = context.chat_data.get("active_agent_id") if context.chat_data else None
        active_name = context.chat_data.get("active_agent_name") if context.chat_data else None
        if active_id:
            safe = escape_markdown(active_name or active_id)
            await update.message.reply_text(
                f"🔀 Active agent: *{safe}*\n\nUse `/switch <agent\\-name>` to change\\.",
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(
                "No agent selected\\. Use `/switch <agent\\-name>` to pick one\\.\n"
                "Use `/agents` to see available agents\\.",
                parse_mode="MarkdownV2",
            )
        return

    query = " ".join(context.args).strip()

    # Find agent by name
    agent_id, agent_name = _find_agent_by_name(query)
    if not agent_id:
        for aid in agent_manager.get_running_agents():
            entry = agent_manager._running_agents.get(aid, {})
            config = entry.get("config", {})
            name = config.get("name", "")
            if name.lower().startswith(query.lower()):
                agent_id = aid
                agent_name = name
                break

    if not agent_id:
        safe = escape_markdown(query)
        await update.message.reply_text(
            f"❌ Agent '{safe}' not found or not running\\. Use `/agents` to list available agents\\.",
            parse_mode="MarkdownV2",
        )
        return

    context.chat_data["active_agent_id"] = agent_id
    context.chat_data["active_agent_name"] = agent_name

    safe = escape_markdown(agent_name)
    await update.message.reply_text(
        f"🔀 Switched to *{safe}*\\. All messages in this chat now go to this agent\\.\n"
        f"Conversation history is preserved per agent — switching back will resume where you left off\\.",
        parse_mode="MarkdownV2",
    )


async def connect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /connect <agent-name> — link this Telegram chat to an agent."""
    if not context.args:
        # Show current connection
        chat_id = str(update.effective_chat.id)
        agent_id, agent_name = await _find_agent_by_chat_id(chat_id)
        if agent_id:
            safe = escape_markdown(agent_name)
            await update.message.reply_text(
                f"🔗 This chat is connected to *{safe}*\\.\n\n"
                f"Use `/connect <agent\\-name>` to switch or `/disconnect` to unlink\\.",
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(
                "This chat is not connected to any agent\\.\n"
                "Use `/connect <agent\\-name>` to link one\\.\n"
                "Use `/agents` to see available agents\\.",
                parse_mode="MarkdownV2",
            )
        return

    query = " ".join(context.args).strip()
    chat_id = str(update.effective_chat.id)

    # Find the agent by name (case-insensitive, then prefix match)
    agent_id, agent_name = _find_agent_by_name(query)
    if not agent_id:
        for aid in agent_manager.get_running_agents():
            entry = agent_manager._running_agents.get(aid, {})
            config = entry.get("config", {})
            name = config.get("name", "")
            if name.lower().startswith(query.lower()):
                agent_id = aid
                agent_name = name
                break

    if not agent_id:
        # Also try finding by name in DB (agent might not be running yet)
        from app.models.agent import Agent
        async with async_session_factory() as db:
            result = await db.execute(
                select(Agent).where(Agent.name.ilike(query)).limit(1)
            )
            agent = result.scalar_one_or_none()
            if not agent:
                result = await db.execute(
                    select(Agent).where(Agent.name.ilike(f"{query}%")).limit(1)
                )
                agent = result.scalar_one_or_none()
            if agent:
                agent_id = agent.id
                agent_name = agent.name

    if not agent_id:
        safe = escape_markdown(query)
        await update.message.reply_text(f"❌ Agent '{safe}' not found\\. Use `/agents` to list available agents\\.", parse_mode="MarkdownV2")
        return

    # Check if another agent already uses this chat_id
    existing_id, existing_name = await _find_agent_by_chat_id(chat_id)
    if existing_id and existing_id != agent_id:
        # Unlink the old agent
        from app.models.agent import Agent
        async with async_session_factory() as db:
            old_agent = await db.get(Agent, existing_id)
            if old_agent:
                old_agent.telegram_chat_id = None
                old_agent.telegram_enabled = False
                await db.commit()

    # Link agent to this chat
    from app.models.agent import Agent
    async with async_session_factory() as db:
        agent = await db.get(Agent, agent_id)
        if agent:
            agent.telegram_chat_id = chat_id
            agent.telegram_enabled = True
            await db.commit()

    safe = escape_markdown(agent_name)
    await update.message.reply_text(
        f"🔗 Connected\\! This chat is now linked to *{safe}*\\.\n\n"
        f"All messages here will auto\\-route to this agent\\. "
        f"Use `/disconnect` to unlink\\.",
        parse_mode="MarkdownV2",
    )


async def disconnect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /disconnect — unlink the current chat from its agent."""
    chat_id = str(update.effective_chat.id)
    agent_id, agent_name = await _find_agent_by_chat_id(chat_id)

    if not agent_id:
        await update.message.reply_text("This chat is not connected to any agent\\.", parse_mode="MarkdownV2")
        return

    from app.models.agent import Agent
    async with async_session_factory() as db:
        agent = await db.get(Agent, agent_id)
        if agent:
            agent.telegram_chat_id = None
            agent.telegram_enabled = False
            await db.commit()

    safe = escape_markdown(agent_name)
    await update.message.reply_text(
        f"🔗 Disconnected from *{safe}*\\. Messages will now go to the default agent\\.",
        parse_mode="MarkdownV2",
    )


async def project_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /project [name] — set or show the active project for this chat."""
    if not context.args:
        # Show current project
        current = context.chat_data.get("project_id") if context.chat_data else None
        current_name = context.chat_data.get("project_name") if context.chat_data else None
        if current:
            safe = escape_markdown(current_name or current)
            await update.message.reply_text(f"📁 Active project: *{safe}*\n\nUse `/project <name>` to switch or `/project clear` to unset\\.", parse_mode="MarkdownV2")
        else:
            await update.message.reply_text("No active project\\. Use `/project <name>` to set one\\.", parse_mode="MarkdownV2")
        return

    query = " ".join(context.args).strip()

    # Clear project
    if query.lower() == "clear":
        context.chat_data["project_id"] = None
        context.chat_data["project_name"] = None
        # Also clear the agent's active project
        chat_id = str(update.effective_chat.id)
        agent_id, _ = await _find_agent_by_chat_id(chat_id)
        if not agent_id:
            agent_id, _ = _get_default_agent()
        if agent_id:
            try:
                from app.core.project_memory_service import set_active_project
                async with async_session_factory() as db:
                    await set_active_project(db, agent_id, None)
                    await db.commit()
            except Exception:
                pass
        await update.message.reply_text("📁 Project cleared\\. Messages will use the default context\\.", parse_mode="MarkdownV2")
        return

    # List projects
    if query.lower() == "list":
        from app.models.project import Project, ProjectStatus
        async with async_session_factory() as db:
            result = await db.execute(
                select(Project).where(Project.status == ProjectStatus.active.value).order_by(Project.name)
            )
            projects = result.scalars().all()
        if not projects:
            await update.message.reply_text("No active projects found\\.", parse_mode="MarkdownV2")
            return
        lines = ["📁 *Active Projects:*\n"]
        for p in projects:
            safe_name = escape_markdown(p.name)
            safe_slug = escape_markdown(p.slug or "")
            lines.append(f"• *{safe_name}* — `{safe_slug}`")
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")
        return

    # Find project by name or slug
    from app.models.project import Project, ProjectStatus
    async with async_session_factory() as db:
        # Try slug first, then name (case-insensitive)
        result = await db.execute(
            select(Project).where(
                Project.status == ProjectStatus.active.value,
                (Project.slug == query.lower()) | (Project.name.ilike(query)),
            ).limit(1)
        )
        project = result.scalar_one_or_none()

        # Fuzzy: try prefix match
        if not project:
            result = await db.execute(
                select(Project).where(
                    Project.status == ProjectStatus.active.value,
                    Project.name.ilike(f"{query}%"),
                ).limit(1)
            )
            project = result.scalar_one_or_none()

    if not project:
        safe = escape_markdown(query)
        await update.message.reply_text(f"❌ Project '{safe}' not found\\. Use `/project list` to see available projects\\.", parse_mode="MarkdownV2")
        return

    context.chat_data["project_id"] = project.id
    context.chat_data["project_name"] = project.name

    # Also update the agent's active project so orchestrator memory injection picks it up
    chat_id = str(update.effective_chat.id)
    agent_id, _ = await _find_agent_by_chat_id(chat_id)
    if not agent_id:
        agent_id, _ = _get_default_agent()
    if agent_id:
        try:
            from app.core.project_memory_service import set_active_project
            async with async_session_factory() as db:
                await set_active_project(db, agent_id, project.id)
                await db.commit()
        except Exception:
            pass

    safe = escape_markdown(project.name)
    await update.message.reply_text(f"📁 Active project set to *{safe}*\\. All messages in this chat will now use this project context\\.", parse_mode="MarkdownV2")


async def newchat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /newchat — start a fresh conversation (new Conversation record)."""
    chat_id = str(update.effective_chat.id)
    project_id = context.chat_data.get("project_id") if context.chat_data else None

    # Find the agent for this chat
    agent_id, agent_name = await _find_agent_by_chat_id(chat_id)
    if not agent_id:
        agent_id, agent_name = _get_default_agent()

    if not agent_id:
        await update.message.reply_text("❌ No agent available\\.", parse_mode="MarkdownV2")
        return

    # Create a new conversation explicitly
    async with async_session_factory() as db:
        title_parts = [f"Telegram: {agent_name}"]
        if project_id:
            from app.models.project import Project
            proj = await db.get(Project, project_id)
            if proj:
                title_parts.append(f"[{proj.name}]")
        conv = Conversation(
            agent_id=agent_id,
            title=" ".join(title_parts),
            source="telegram",
            source_id=chat_id,
            project_id=project_id,
        )
        db.add(conv)
        await db.commit()

    safe_name = escape_markdown(agent_name)
    await update.message.reply_text(f"🆕 New conversation started with *{safe_name}*\\. Previous history will not be carried over\\.", parse_mode="MarkdownV2")


async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask [agent] [message]."""
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: `/ask [agent-name] <question>`", parse_mode="MarkdownV2")
        return

    query = context.args[0]
    message = " ".join(context.args[1:])

    agent_id, agent_name = _find_agent_by_name(query)
    
    if not agent_id:
        # Try finding the agent by prefix
        for aid in agent_manager.get_running_agents():
            entry = agent_manager._running_agents.get(aid, {})
            config = entry.get("config", {})
            name = config.get("name", "")
            if name.lower().startswith(query.lower()):
                agent_id = aid
                agent_name = name
                break

    if not agent_id:
        await update.message.reply_text(f"❌ Agent '{query}' not found or not running.")
        return

    if not message:
        safe_name = escape_markdown(agent_name)
        await update.message.reply_text(f"What would you like to ask *{safe_name}*?", parse_mode="MarkdownV2")
        return

    # Thinking...
    safe_name = escape_markdown(agent_name)
    chat_id = str(update.effective_chat.id)
    think_msg = await update.message.reply_text(f"🤖 *{safe_name}* is thinking\.\.\.", parse_mode="MarkdownV2")

    project_id = context.chat_data.get("project_id") if context.chat_data else None
    try:
        response = await _route_with_history(agent_id, agent_name, message, chat_id, project_id=project_id)
        safe_response = escape_markdown(response['output'])
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=think_msg.message_id,
            text=f"🤖 *{safe_name}*:\n\n{safe_response}",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Telegram /ask error: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=think_msg.message_id,
            text="⚠️ An error occurred while processing your request."
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    chat_id = str(update.effective_chat.id)
    agent_id, agent_name = None, None
    message = text

    # Check for @AgentName prefix
    match = re.match(r"@(\S+)\s+(.*)", text, re.DOTALL)
    if match:
        query = match.group(1)
        agent_id, agent_name = _find_agent_by_name(query)
        if agent_id:
            message = match.group(2).strip()

    # Check chat_data for /switch selection
    if not agent_id and context.chat_data and context.chat_data.get("active_agent_id"):
        switched_id = context.chat_data["active_agent_id"]
        switched_name = context.chat_data.get("active_agent_name", "Agent")
        if agent_manager.is_running(switched_id):
            agent_id, agent_name = switched_id, switched_name

    # Try to find agent by chat_id (dedicated chat per agent)
    if not agent_id:
        agent_id, agent_name = await _find_agent_by_chat_id(chat_id)

    # Fall back to default
    if not agent_id:
        agent_id, agent_name = _get_default_agent()

    if not agent_id:
        await update.message.reply_text("❌ No agents are currently running\\. Start one from the dashboard\\.", parse_mode="MarkdownV2")
        return

    # Thinking...
    safe_name = escape_markdown(agent_name)
    project_id = context.chat_data.get("project_id") if context.chat_data else None
    think_msg = await update.message.reply_text(f"🤖 *{safe_name}* is thinking\.\.\.", parse_mode="MarkdownV2")

    try:
        response = await _route_with_history(agent_id, agent_name, message, chat_id, project_id=project_id)
        safe_response = escape_markdown(response['output'])
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=think_msg.message_id,
            text=f"🤖 *{safe_name}*:\n\n{safe_response}",
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Telegram message error: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=think_msg.message_id,
            text="⚠️ An error occurred while processing your request."
        )

async def forge_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forge <description> — starts a new forge request."""
    if not context.args:
        await update.message.reply_text(
            "🔧 *Sutra Forge — Autonomous Feature Builder*\n\n"
            "Usage: `/forge <description>`\n\n"
            "Examples:\n"
            "`/forge Add dark mode toggle to settings page in owner/repo`\n"
            "`/forge Fix the login redirect bug in myorg/backend`\n\n"
            "Other commands:\n"
            "`/forge status` — list active forge requests",
            parse_mode="MarkdownV2",
        )
        return

    if context.args[0].lower() == "status":
        await _forge_status_handler(update, context)
        return

    description = " ".join(context.args)
    chat_id = str(update.effective_chat.id)

    think_msg = await update.message.reply_text("🔧 Starting Forge\\.\\.\\.", parse_mode="MarkdownV2")

    try:
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import make_branch_name, workspace_for, clone_repo, create_branch, generate_plan
        from app.config import settings
        from pathlib import Path

        # Extract repo from description if in "owner/repo" pattern
        repo_match = re.search(r"\b([\w.-]+/[\w.-]+)\b", description)
        repo_url = repo_match.group(1) if repo_match else ""

        async with async_session_factory() as db:
            req = ForgeRequest(
                title=description[:80],
                description=description,
                repo_url=repo_url,
                coding_engine=settings.forge_default_engine,
                deploy_mode="manual",
                status=ForgeStatus.planning.value,
                source_channel="telegram",
                telegram_chat_id=chat_id,
                coding_log=[],
                plan_feedback=[],
            )
            db.add(req)
            await db.flush()
            await db.refresh(req)

            if not repo_url:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=think_msg.message_id,
                    text=(
                        "❓ I couldn't detect a repo in your message\\.\n\n"
                        f"Forge request `{req.id[:8]}` created\\.\n"
                        "Please provide the repo in `owner/repo` format\\."
                    ),
                    parse_mode="MarkdownV2",
                )
                await db.commit()
                return

            branch = make_branch_name(description, req.id)
            workspace = workspace_for(req.id)
            req.branch_name = branch
            req.workspace_path = str(workspace)
            await db.commit()

        # Run planning in background and update user
        asyncio.create_task(_telegram_forge_plan(req.id, repo_url, description, chat_id, think_msg.message_id, context))

    except Exception as e:
        logger.error(f"Forge Telegram handler error: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=think_msg.message_id,
            text=f"⚠️ Error starting forge: {escape_markdown(str(e))}",
            parse_mode="MarkdownV2",
        )


async def _forge_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List active forge requests."""
    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest
    from sqlalchemy import select

    async with async_session_factory() as db:
        result = await db.execute(
            select(ForgeRequest)
            .where(ForgeRequest.telegram_chat_id == str(update.effective_chat.id))
            .order_by(ForgeRequest.created_at.desc())
            .limit(5)
        )
        requests = result.scalars().all()

    if not requests:
        await update.message.reply_text("📭 No forge requests found for this chat\\.", parse_mode="MarkdownV2")
        return

    lines = ["🔧 *Your Forge Requests:*\n"]
    for r in requests:
        status_emoji = {
            "planning": "🔵", "awaiting_plan_approval": "🟡", "coding": "⚙️",
            "pr_created": "🟢", "awaiting_merge_approval": "🟡", "merging": "⚙️",
            "completed": "✅", "failed": "❌", "cancelled": "⛔",
        }.get(r.status, "❓")
        lines.append(f"{status_emoji} `{r.id[:8]}` — {escape_markdown(r.title[:40])}")
        lines.append(f"   Status: {escape_markdown(r.status)}")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


async def _telegram_forge_plan(
    forge_id: str, repo_url: str, description: str,
    chat_id: str, message_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Background: clone + plan + send inline keyboard."""
    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest, ForgeStatus
    from app.core.forge_engine import clone_repo, create_branch, generate_plan, workspace_for
    from pathlib import Path

    async with async_session_factory() as db:
        req = await db.get(ForgeRequest, forge_id)
        if not req:
            return
        ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)

        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=f"🔧 Cloning `{escape_markdown(repo_url)}`\\.\\.\\.",
            parse_mode="MarkdownV2",
        )

        try:
            await clone_repo(repo_url, ws)
            await create_branch(ws, req.branch_name)
        except Exception as e:
            req.status = ForgeStatus.failed.value
            req.error_log = str(e)
            await db.commit()
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"❌ Clone failed: {escape_markdown(str(e))}",
                parse_mode="MarkdownV2",
            )
            return

        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text="🧠 Generating implementation plan\\.\\.\\.",
            parse_mode="MarkdownV2",
        )

        try:
            plan = await generate_plan(repo_url, description, ws)
            req.plan = plan
            req.status = ForgeStatus.awaiting_plan_approval.value
            await db.commit()
        except Exception as e:
            req.status = ForgeStatus.failed.value
            req.error_log = str(e)
            await db.commit()
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"❌ Plan generation failed: {escape_markdown(str(e))}",
                parse_mode="MarkdownV2",
            )
            return

    # Send the plan with approval keyboard
    plan = req.plan or {}
    steps = plan.get("steps", [])
    steps_text = "\n".join(
        f"{i+1}\\. \\[{escape_markdown(s.get('action','?').upper())}\\] `{escape_markdown(s.get('file','?'))}`: {escape_markdown(s.get('description',''))}"
        for i, s in enumerate(steps[:8])
    )
    summary = escape_markdown(plan.get("summary", ""))
    repo_escaped = escape_markdown(repo_url)

    text = (
        f"🔧 *Forge Plan Ready*\n"
        f"Repo: `{repo_escaped}`\n\n"
        f"📋 *Summary:* {summary}\n\n"
        f"*Steps:*\n{steps_text or '_(no steps generated)_'}\n\n"
        f"What would you like to do?"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Code", callback_data=f"forge_plan_{forge_id}_approve"),
            InlineKeyboardButton("✏️ Suggest Changes", callback_data=f"forge_plan_{forge_id}_feedback"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"forge_plan_{forge_id}_cancel"),
        ]
    ])

    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=message_id,
        text=text, parse_mode="MarkdownV2",
        reply_markup=keyboard,
    )


async def forge_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses for forge plan/merge approval."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # forge_plan_{id}_approve | forge_plan_{id}_feedback | forge_plan_{id}_cancel
    # forge_merge_{id}_approve | forge_merge_{id}_feedback | forge_merge_{id}_cancel
    match = re.match(r"forge_(plan|merge)_([a-f0-9-]+)_(approve|feedback|cancel)", data)
    if not match:
        return

    stage, forge_id, action = match.group(1), match.group(2), match.group(3)

    if action == "cancel":
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import cleanup_workspace, workspace_for
        from pathlib import Path
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if req:
                req.status = ForgeStatus.cancelled.value
                ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
                await db.commit()
                cleanup_workspace(ws)
        await query.edit_message_text("⛔ Forge request cancelled\\.", parse_mode="MarkdownV2")
        return

    if action == "feedback":
        # Store forge_id in user_data and ask for feedback text
        context.user_data["forge_feedback_id"] = forge_id
        context.user_data["forge_feedback_stage"] = stage
        await query.edit_message_text(
            "✏️ Please describe the changes you'd like to the plan\\.\\.\\.",
            parse_mode="MarkdownV2",
        )
        # Signal ConversationHandler to move to FORGE_FEEDBACK state
        return FORGE_FEEDBACK

    if action == "approve":
        if stage == "plan":
            await _approve_forge_plan(forge_id, query, context)
        else:
            await _approve_forge_merge(forge_id, query, context)


async def forge_feedback_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect feedback text after user pressed 'Suggest Changes'."""
    feedback = update.message.text.strip()
    forge_id = context.user_data.get("forge_feedback_id")

    if not forge_id:
        await update.message.reply_text("⚠️ No active forge feedback session\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    think_msg = await update.message.reply_text("🧠 Revising plan\\.\\.\\.", parse_mode="MarkdownV2")

    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest, ForgeStatus
    from app.core.forge_engine import generate_plan, workspace_for
    from pathlib import Path

    async with async_session_factory() as db:
        req = await db.get(ForgeRequest, forge_id)
        if not req:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=think_msg.message_id,
                text="⚠️ Forge request not found\\.", parse_mode="MarkdownV2",
            )
            return ConversationHandler.END

        rounds = list(req.plan_feedback or [])
        rounds.append({"round": len(rounds) + 1, "feedback": feedback})
        req.plan_feedback = rounds

        ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
        revised_desc = f"{req.description}\n\nUser feedback: {feedback}"

        try:
            plan = await generate_plan(req.repo_url, revised_desc, ws)
            req.plan = plan
            req.status = ForgeStatus.awaiting_plan_approval.value
            await db.commit()
        except Exception as e:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=think_msg.message_id,
                text=f"❌ Plan revision failed: {escape_markdown(str(e))}", parse_mode="MarkdownV2",
            )
            return ConversationHandler.END

    steps = plan.get("steps", [])
    steps_text = "\n".join(
        f"{i+1}\\. `{escape_markdown(s.get('file','?'))}`: {escape_markdown(s.get('description',''))}"
        for i, s in enumerate(steps[:8])
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve & Code", callback_data=f"forge_plan_{forge_id}_approve"),
            InlineKeyboardButton("✏️ Suggest Changes", callback_data=f"forge_plan_{forge_id}_feedback"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"forge_plan_{forge_id}_cancel"),
        ]
    ])
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, message_id=think_msg.message_id,
        text=(
            f"🔄 *Revised Plan:*\n\n"
            f"📋 {escape_markdown(plan.get('summary',''))}\n\n"
            f"{steps_text or '_(empty)_'}"
        ),
        parse_mode="MarkdownV2",
        reply_markup=keyboard,
    )
    return ConversationHandler.END


async def _approve_forge_plan(forge_id: str, query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kick off coding after plan approval."""
    await query.edit_message_text("⚙️ Plan approved\\! Starting coding engine\\.\\.\\.", parse_mode="MarkdownV2")

    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest, ForgeStatus

    async with async_session_factory() as db:
        req = await db.get(ForgeRequest, forge_id)
        if not req:
            return
        req.status = ForgeStatus.coding.value
        chat_id = req.telegram_chat_id
        await db.commit()

    asyncio.create_task(_telegram_forge_code_and_pr(forge_id, chat_id, context))


async def _approve_forge_merge(forge_id: str, query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Merge the PR after merge approval."""
    await query.edit_message_text("🔀 Merging PR\\.\\.\\.", parse_mode="MarkdownV2")

    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest, ForgeStatus, DeployMode
    from app.core.forge_engine import auto_deploy, cleanup_workspace, workspace_for
    from pathlib import Path

    async with async_session_factory() as db:
        req = await db.get(ForgeRequest, forge_id)
        if not req or not req.pr_number:
            await query.edit_message_text("⚠️ No PR found for this request\\.", parse_mode="MarkdownV2")
            return

        try:
            from github import Github
            from app.config import settings
            from app.core.env_utils import get_secret
            gh = Github(await get_secret("GITHUB_TOKEN", settings.github_token or ""))
            repo = gh.get_repo(req.repo_url)
            pr = repo.get_pull(req.pr_number)
            pr.merge(commit_message=f"Merge Sutra Forge PR: {req.title}")
        except Exception as e:
            req.status = ForgeStatus.failed.value
            req.error_log = str(e)
            await db.commit()
            await query.edit_message_text(
                f"❌ Merge failed: {escape_markdown(str(e))}", parse_mode="MarkdownV2"
            )
            return

        if req.deploy_mode == DeployMode.auto.value:
            req.status = ForgeStatus.deploying.value
            await db.commit()
            chat_id = req.telegram_chat_id
            await _application.bot.send_message(
                chat_id=chat_id,
                text="🚀 Auto\\-deploying\\.\\.\\.", parse_mode="MarkdownV2",
            )
            async for event in auto_deploy():
                if event["event"] == "error":
                    req.status = ForgeStatus.failed.value
                    req.error_log = event["message"]
                    await db.commit()
                    await _application.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Deploy failed: {escape_markdown(event['message'])}",
                        parse_mode="MarkdownV2",
                    )
                    return

        ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
        cleanup_workspace(ws)
        req.status = ForgeStatus.completed.value
        await db.commit()

    await query.edit_message_text(
        f"🎉 *Done\\!* PR merged and forge request completed\\.",
        parse_mode="MarkdownV2",
    )


async def _telegram_forge_code_and_pr(
    forge_id: str, chat_id: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Background: run coding engine, commit, push, open PR, then ask for merge approval."""
    from app.db.session import async_session_factory
    from app.models.forge import ForgeRequest, ForgeStatus
    from app.core.forge_engine import (
        run_gemini_coding, run_claude_code,
        commit_all, push_branch, workspace_for, _get_semaphore,
    )
    from pathlib import Path
    from datetime import datetime, timezone

    semaphore = _get_semaphore()

    progress_msg = await _application.bot.send_message(
        chat_id=chat_id, text="⚙️ Coding in progress\\.\\.\\.", parse_mode="MarkdownV2"
    )
    last_update = ""

    async with semaphore:
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return
            ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
            engine = req.coding_engine
            plan = req.plan
            desc = req.description
            branch = req.branch_name

        log_entries = list(req.coding_log or [])
        error_msg = None

        stream = run_claude_code(ws, plan, desc) if engine == "claude_code" else run_gemini_coding(ws, plan, desc)
        step = 0

        async for event in stream:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event["event"],
                "message": event["message"],
            }
            log_entries.append(entry)
            step += 1

            # Throttle Telegram updates (every 3 events)
            if step % 3 == 0:
                short = escape_markdown(event["message"][:100])
                new_text = f"⚙️ *Coding* \\({step} steps\\)\\.\\.\\.\n_{short}_"
                if new_text != last_update:
                    try:
                        await _application.bot.edit_message_text(
                            chat_id=chat_id, message_id=progress_msg.message_id,
                            text=new_text, parse_mode="MarkdownV2",
                        )
                        last_update = new_text
                    except Exception:
                        pass

            async with async_session_factory() as db:
                req2 = await db.get(ForgeRequest, forge_id)
                if req2:
                    req2.coding_log = log_entries
                    await db.commit()

            if event["event"] == "error":
                error_msg = event["message"]
                break

    if error_msg:
        async with async_session_factory() as db:
            req3 = await db.get(ForgeRequest, forge_id)
            if req3:
                req3.status = ForgeStatus.failed.value
                req3.error_log = error_msg
                await db.commit()
        await _application.bot.edit_message_text(
            chat_id=chat_id, message_id=progress_msg.message_id,
            text=f"❌ Coding failed: {escape_markdown(error_msg)}", parse_mode="MarkdownV2",
        )
        return

    # Commit + push + PR
    await _application.bot.edit_message_text(
        chat_id=chat_id, message_id=progress_msg.message_id,
        text="📤 Committing and creating PR\\.\\.\\.", parse_mode="MarkdownV2",
    )

    async with async_session_factory() as db:
        req3 = await db.get(ForgeRequest, forge_id)
        if not req3:
            return
        try:
            plan_summary = (req3.plan or {}).get("summary", req3.title)
            await commit_all(ws, f"feat: {plan_summary}\n\nGenerated by Sutra Forge")
            await push_branch(ws, branch)

            from github import Github
            from app.config import settings
            from app.core.env_utils import get_secret
            gh = Github(await get_secret("GITHUB_TOKEN", settings.github_token or ""))
            repo = gh.get_repo(req3.repo_url)
            pr = repo.create_pull(
                title=f"feat: {req3.title}",
                body=f"## Summary\n{plan_summary}\n\n🤖 Generated by Sutra Forge",
                head=branch,
                base=repo.default_branch,
            )
            req3.pr_url = pr.html_url
            req3.pr_number = pr.number
            req3.status = ForgeStatus.awaiting_merge_approval.value
            await db.commit()

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔀 Merge", callback_data=f"forge_merge_{forge_id}_approve"),
                    InlineKeyboardButton("✏️ Request Changes", callback_data=f"forge_merge_{forge_id}_feedback"),
                    InlineKeyboardButton("❌ Close PR", callback_data=f"forge_merge_{forge_id}_cancel"),
                ]
            ])
            await _application.bot.edit_message_text(
                chat_id=chat_id, message_id=progress_msg.message_id,
                text=(
                    f"✅ *PR \\#{pr.number} ready\\!*\n"
                    f"{escape_markdown(pr.html_url)}\n\n"
                    f"What would you like to do?"
                ),
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
            )
        except Exception as e:
            req3.status = ForgeStatus.failed.value
            req3.error_log = str(e)
            await db.commit()
            await _application.bot.edit_message_text(
                chat_id=chat_id, message_id=progress_msg.message_id,
                text=f"❌ PR creation failed: {escape_markdown(str(e))}", parse_mode="MarkdownV2",
            )


async def notify_approval_via_telegram(
    approval_id: str,
    title: str,
    description: str,
    category: str,
    risk_level: str,
    agent_id: str,
):
    """Send an approval request notification to Telegram with inline approve/reject buttons."""
    global _application
    if not _application or not _application.bot:
        return

    # Determine which chat to notify: agent's telegram_chat_id or default
    # Note: we check telegram_chat_id regardless of telegram_enabled — an agent
    # might have a chat_id for receiving approval notifications even if it doesn't
    # listen for incoming Telegram messages.
    chat_id = None
    try:
        from app.models.agent import Agent
        async with async_session_factory() as db:
            agent = await db.get(Agent, agent_id)
            if agent and agent.telegram_chat_id:
                chat_id = str(agent.telegram_chat_id).strip()
                logger.debug("Using agent %s telegram_chat_id: %r", agent_id, chat_id)
    except Exception as e:
        logger.debug("Failed to look up agent telegram_chat_id: %s", e)

    if not chat_id:
        chat_id = str(settings.telegram_default_chat_id).strip() if settings.telegram_default_chat_id else None

    if not chat_id:
        logger.debug("No Telegram chat_id for approval notification (agent %s)", agent_id)
        return

    # Get agent name for display
    info = agent_manager.get_info(agent_id) or {}
    agent_name = info.get("name", "Unknown Agent")

    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(risk_level, "⚪")

    text = (
        f"🔔 *Approval Required*\n\n"
        f"*{escape_markdown(title)}*\n\n"
        f"{escape_markdown(description)}\n\n"
        f"Agent: {escape_markdown(agent_name)}\n"
        f"Category: {escape_markdown(category)} \\| Risk: {risk_emoji} {escape_markdown(risk_level)}\n"
        f"ID: `{escape_markdown(approval_id[:8])}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approval_{approval_id}_approve"),
            InlineKeyboardButton("❌ Reject", callback_data=f"approval_{approval_id}_reject"),
        ]
    ])

    try:
        # Telegram expects numeric chat_id for private/group chats
        resolved_chat_id = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        await _application.bot.send_message(
            chat_id=resolved_chat_id,
            text=text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )
        logger.info("Sent approval notification to Telegram chat %s for approval %s", chat_id, approval_id[:8])
    except Exception as e:
        logger.error("Failed to send Telegram approval notification to chat_id=%r: %s", chat_id, e)


async def approval_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses for approval approve/reject."""
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # Parse: approval_{uuid}_approve or approval_{uuid}_reject
    match = re.match(r"approval_([a-f0-9-]+)_(approve|reject)", data)
    if not match:
        return

    approval_id, action = match.group(1), match.group(2)
    telegram_user = update.effective_user
    telegram_user_name = telegram_user.full_name if telegram_user else "Telegram User"

    from app.models.approval_request import ApprovalRequest, ApprovalStatus

    async with async_session_factory() as db:
        req = await db.get(ApprovalRequest, approval_id)
        if not req:
            await query.edit_message_text("⚠️ Approval request not found\\.", parse_mode="MarkdownV2")
            return

        if req.status != ApprovalStatus.pending.value:
            status_display = escape_markdown(req.status)
            await query.edit_message_text(
                f"ℹ️ This request is already *{status_display}*\\.",
                parse_mode="MarkdownV2",
            )
            return

        # Find the owner user for reviewer_user_id
        reviewer_user_id = None
        try:
            from app.models.user import User
            result = await db.execute(
                select(User).order_by(User.created_at.asc()).limit(1)
            )
            owner = result.scalar_one_or_none()
            if owner:
                reviewer_user_id = owner.id
        except Exception:
            pass

        if action == "approve":
            req.status = ApprovalStatus.approved.value
            req.reviewer_note = f"Approved via Telegram by {telegram_user_name}"
            req.reviewer_user_id = reviewer_user_id
            req.decided_at = datetime.now(timezone.utc)
            await db.commit()

            # Execute deferred action if present
            if req.action_payload:
                try:
                    from app.api.routes.approvals import _execute_approved_action
                    await _execute_approved_action(req, db)
                except Exception as e:
                    logger.error("Failed to execute approved action for %s: %s", approval_id[:8], e)

            safe_title = escape_markdown(req.title)
            await query.edit_message_text(
                f"✅ *Approved* by {escape_markdown(telegram_user_name)}\n\n{safe_title}",
                parse_mode="MarkdownV2",
            )

        else:  # reject
            req.status = ApprovalStatus.rejected.value
            req.reviewer_note = f"Rejected via Telegram by {telegram_user_name}"
            req.reviewer_user_id = reviewer_user_id
            req.decided_at = datetime.now(timezone.utc)
            await db.commit()

            safe_title = escape_markdown(req.title)
            await query.edit_message_text(
                f"❌ *Rejected* by {escape_markdown(telegram_user_name)}\n\n{safe_title}",
                parse_mode="MarkdownV2",
            )

        # Broadcast WebSocket update
        try:
            from app.api.websocket import ws_manager
            await ws_manager.broadcast({
                "type": f"approval_{action}d",
                "approval_id": approval_id,
                "title": req.title,
                "reviewer_note": req.reviewer_note,
            })
        except Exception:
            pass

        # Dispatch webhook
        try:
            from app.core.webhook_dispatcher import dispatch_webhook
            await dispatch_webhook(f"approval.{action}d", {
                "approval_id": approval_id,
                "title": req.title,
                "status": req.status,
                "reviewer_note": req.reviewer_note,
            })
        except Exception:
            pass

    logger.info("Approval %s %sd via Telegram by %s", approval_id[:8], action, telegram_user_name)


async def start_telegram_bot():
    """Build and start the Telegram bot application."""
    token = await get_telegram_bot_token()
    if not token:
        logger.warning("Telegram bot not configured. Set TELEGRAM_BOT_TOKEN.")
        return

    logger.info("📡 Starting Telegram bot...")

    try:
        global _application
        _application = ApplicationBuilder().token(token).build()

        # Forge conversation handler (collects feedback text after inline button press)
        forge_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(forge_callback_handler, pattern=r"^forge_")],
            states={
                FORGE_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, forge_feedback_text_handler)],
            },
            fallbacks=[],
            per_chat=True,
        )

        # Add handlers
        _application.add_handler(CommandHandler("start", start_handler))
        _application.add_handler(CommandHandler("agents", agents_handler))
        _application.add_handler(CommandHandler("chatid", chatid_handler))
        _application.add_handler(CommandHandler("status", status_handler))
        _application.add_handler(CommandHandler("ask", ask_handler))
        _application.add_handler(CommandHandler("switch", switch_handler))
        _application.add_handler(CommandHandler("connect", connect_handler))
        _application.add_handler(CommandHandler("disconnect", disconnect_handler))
        _application.add_handler(CommandHandler("project", project_handler))
        _application.add_handler(CommandHandler("newchat", newchat_handler))
        _application.add_handler(CommandHandler("forge", forge_handler))
        _application.add_handler(forge_conv_handler)
        _application.add_handler(CallbackQueryHandler(approval_callback_handler, pattern=r"^approval_"))
        _application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

        # Initializing the application
        await _application.initialize()
        await _application.start()
        
        # Start matching the polling
        # We use a custom polling loop that can be cancelled
        # so it doesn't block the FastAPI application's main thread
        await _application.updater.start_polling()
        
        logger.info("✅ Telegram bot is online.")
        
        # This keeps the task alive
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"❌ Failed to start Telegram bot: {e}")
        raise e

async def send_telegram_message(chat_id: str, text: str):
    """Send a message to a specific chat ID."""
    global _application

    token = await get_telegram_bot_token()
    if not token:
        logger.warning("Telegram bot token not configured. cannot send message.")
        return

    try:
        safe_text = escape_markdown(text)
        # Try to use the running application if available
        if _application and _application.bot:
            await _application.bot.send_message(chat_id=chat_id, text=safe_text, parse_mode="MarkdownV2")
        else:
            # Fallback to standalone bot instance
            from telegram import Bot
            bot = Bot(token=token)
            async with bot:
                await bot.send_message(chat_id=chat_id, text=safe_text, parse_mode="MarkdownV2")
        logger.info(f"📤 Sent Telegram message to {chat_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram message to {chat_id}: {e}")
        raise e
