"""Telegram Bot integration using python-telegram-bot."""
import logging
import re
import asyncio
from typing import Any

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

# ConversationHandler states for forge feedback collection
FORGE_FEEDBACK = 1

from app.config import settings
from app.core.agent_manager import agent_manager
from app.core.orchestrator import orchestrator

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

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Welcome to Sutra AI Telegram Bot!\n\n"
        "You can talk to authorized AI agents here.\n\n"
        "Commands:\n"
        "/agents - List running agents\n"
        "/ask [agent] [message] - Ask a specific agent\n"
        "/status - Check system status\n"
        "/forge [description] - Build a feature autonomously\n\n"
        "Or just message me to talk to the default agent."
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

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    running_count = len(agent_manager.get_running_agents())
    await update.message.reply_text(
        f"📊 *Sutra Status*\n"
        f"• Status: 🟢 Operational\n"
        f"• Running Agents: {running_count}",
        parse_mode="MarkdownV2"
    )

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
    think_msg = await update.message.reply_text(f"🤖 *{safe_name}* is thinking\.\.\.", parse_mode="MarkdownV2")

    try:
        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=message,
        )
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
    
    agent_id, agent_name = None, None
    message = text

    # Check for @AgentName prefix
    match = re.match(r"@(\S+)\s+(.*)", text, re.DOTALL)
    if match:
        query = match.group(1)
        agent_id, agent_name = _find_agent_by_name(query)
        if agent_id:
            message = match.group(2).strip()

    # Fall back to default
    if not agent_id:
        agent_id, agent_name = _get_default_agent()

    if not agent_id:
        await update.message.reply_text("❌ No agents are currently running\\. Start one from the dashboard\\.", parse_mode="MarkdownV2")
        return

    # Thinking...
    safe_name = escape_markdown(agent_name)
    think_msg = await update.message.reply_text(f"🤖 *{safe_name}* is thinking\.\.\.", parse_mode="MarkdownV2")

    try:
        response = await orchestrator.route_message(
            agent_id=agent_id,
            message=message,
        )
        # Handle long responses (Markdown v2 can be picky, using Markdown v2/classic)
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
        _application.add_handler(CommandHandler("status", status_handler))
        _application.add_handler(CommandHandler("ask", ask_handler))
        _application.add_handler(CommandHandler("forge", forge_handler))
        _application.add_handler(forge_conv_handler)
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
