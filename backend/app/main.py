"""Sutra Backend — FastAPI Application Entry Point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import agents, auth, chat, llms, memory, system, tools, workflows, jobs, mcp_servers, monitor
from app.api.routes import approvals, audit, discussions, traces, tasks, roles, teams
from app.api.routes import goals, triggers, financials
from app.api.routes import batch_jobs as batch_jobs_routes
from app.api.routes import knowledge
from app.api.routes import agent_templates
from app.api.routes import analytics as analytics_routes
from app.api.routes import email as email_routes
from app.api.routes import webhooks as webhooks_routes
from app.api.routes import auth_google
from app.api.routes import webhooks as webhooks_routes
from app.api.routes import skills as skills_routes
from app.api.routes import integrations as integrations_routes
from app.api.routes import forge as forge_routes
from app.api.routes import evolve as evolve_routes
from app.api.routes import alerts as alerts_routes
from app.api.routes import social_pulse as social_pulse_routes
from app.api.routes import system_settings as system_settings_routes
from app.api.routes import projects as projects_routes
from app.api.routes import env_vars as env_vars_routes
from app.api.routes import rate_limits as rate_limits_routes
from app.api.routes import purposes as purposes_routes
from app.api.routes import job_applications as job_applications_routes
from app.api.websocket import websocket_endpoint
from app.config import settings
from app.core.logging_config import configure_logging
from app.core.rate_limiter import limiter
from app.core.security import get_current_user
from app.core.startup_checks import run_startup_checks
from app.db.session import engine
from app.middleware.correlation import CorrelationMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.models.base import Base
import app.models.audit   # ensure AuditLog table is registered  # noqa: F401
import app.models.job  # ensure Job table is registered with Base.metadata  # noqa: F401
import app.models.mcp_server  # ensure MCPServer table is registered  # noqa: F401
import app.models.trace   # ensure ExecutionTrace table is registered  # noqa: F401
import app.models.user  # ensure User table is registered  # noqa: F401
import app.models.memory  # ensure Memory table is registered  # noqa: F401
import app.models.approval_request  # ensure ApprovalRequest table is registered  # noqa: F401
import app.models.discussion  # ensure Discussion table is registered  # noqa: F401
import app.models.project  # ensure Project table is registered  # noqa: F401
import app.models.task  # ensure Task table is registered  # noqa: F401
import app.models.role  # ensure AgentRole table is registered  # noqa: F401
import app.models.team  # ensure Team table is registered  # noqa: F401
import app.models.goal  # ensure AgentGoal table is registered  # noqa: F401
import app.models.checkin  # ensure AgentCheckIn table is registered  # noqa: F401
import app.models.initiative  # ensure AgentInitiative table is registered  # noqa: F401
import app.models.trigger  # ensure AgentTrigger table is registered  # noqa: F401
import app.models.budget   # ensure Budget table is registered  # noqa: F401
import app.models.pricing  # ensure ModelPricing table is registered  # noqa: F401
import app.models.knowledge_base  # ensure KnowledgeBase/Document/DocumentChunk tables are registered  # noqa: F401
import app.models.agent_template  # ensure AgentTemplate table is registered  # noqa: F401
import app.models.workflow  # ensure Workflow table is registered  # noqa: F401
import app.models.email  # ensure EmailConfig/EmailWhitelist tables are registered  # noqa: F401
import app.models.webhook  # ensure WebhookSubscription/WebhookDelivery tables are registered  # noqa: F401
import app.models.skill  # ensure Skill/AgentSkill/RoleSkill tables are registered  # noqa: F401
import app.models.integration  # ensure Integration table is registered  # noqa: F401
import app.models.forge  # ensure ForgeRequest table is registered  # noqa: F401
import app.models.api_key  # ensure ApiKey table is registered  # noqa: F401
import app.models.social_pulse  # ensure SocialPulse/TrendKeyword/PulseNiche tables are registered  # noqa: F401
import app.models.batch_job  # ensure BatchJob/BatchJobRun tables are registered  # noqa: F401
import app.models.system_config  # ensure SystemConfig table is registered  # noqa: F401
import app.models.evolve  # ensure EvolveSuggestion/EvolveRun tables are registered  # noqa: F401
import app.models.alert_record  # ensure AlertRule/AlertRecord tables are registered  # noqa: F401
import app.models.project_decision  # ensure ProjectDecision table is registered  # noqa: F401
import app.models.project_file  # ensure ProjectFile table is registered  # noqa: F401
import app.models.env_var  # ensure EnvVar table is registered  # noqa: F401
import app.models.rate_limit  # ensure ModelRateLimit table is registered  # noqa: F401
import app.models.llm_purpose  # ensure LLMPurpose table is registered  # noqa: F401
import app.models.error_log  # ensure ErrorLog table is registered  # noqa: F401
import app.models.job_application  # ensure JobApplication table is registered  # noqa: F401
from app.core.scheduler import start_scheduler, scheduler

configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    logger.info("🚀 Starting Sutra AI Orchestrator...")

    # Security startup checks (strict=True in production)
    run_startup_checks(strict=not settings.debug)

    # Create database tables (dev mode — use Alembic migrations in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables created/verified.")

    # Run lightweight schema migrations (add missing columns)
    try:
        from app.core.db_migrations import run_migrations
        from app.db.session import async_session_factory
        async with async_session_factory() as db:
            ok, skipped = await run_migrations(db)
        logger.info(f"✅ Schema migrations: {ok} applied, {skipped} skipped.")
    except Exception as e:
        logger.warning(f"Schema migrations skipped: {e}")

    # Load runtime system settings from DB
    try:
        from app.core.system_settings import sys_settings
        from app.db.session import async_session_factory
        async with async_session_factory() as db:
            await sys_settings.load(db)
        logger.info("✅ System settings loaded.")
    except Exception as e:
        logger.warning(f"System settings load skipped: {e}")

    # Start APScheduler
    logger.info("⏰ Starting APScheduler...")
    start_scheduler()
    logger.info("✅ APScheduler started.")

    # Create performance indexes
    try:
        from app.core.db_indexes import ensure_indexes
        from app.db.session import async_session_factory
        async with async_session_factory() as db:
            await ensure_indexes(db)
        logger.info("✅ Database indexes verified.")
    except Exception as e:
        logger.warning(f"Index creation skipped: {e}")

    # Restore env vars from DB into os.environ (lost across restarts)
    try:
        import os as _os
        from app.core.vault import decrypt_secret
        from app.db.session import async_session_factory
        from app.models.env_var import EnvVar
        from sqlalchemy import select as sa_select
        async with async_session_factory() as db:
            result = await db.execute(sa_select(EnvVar))
            for row in result.scalars().all():
                if row.is_secret:
                    try:
                        _os.environ.setdefault(row.key, decrypt_secret(row.value))
                    except Exception:
                        pass
                else:
                    _os.environ.setdefault(row.key, row.value)
        logger.info("✅ Env vars restored from DB.")
    except Exception as e:
        logger.warning(f"Non-secret env var restore skipped: {e}")

    # Load LLM providers from DB into registry (needed before agents are restored)
    try:
        from app.core.llm_registry import llm_registry
        from app.core.vault import decrypt_secret
        from app.db.session import async_session_factory
        from app.models.llm_provider import LLMProvider
        from sqlalchemy import select as sa_select
        async with async_session_factory() as db:
            result = await db.execute(sa_select(LLMProvider).where(LLMProvider.is_enabled == True))  # noqa: E712
            for p in result.scalars().all():
                api_key = ""
                if p.api_key_encrypted:
                    try:
                        api_key = decrypt_secret(p.api_key_encrypted)
                    except Exception:
                        pass
                llm_registry.register_provider(
                    name=p.provider_type,
                    provider_type=p.provider_type,
                    api_key=api_key,
                    base_url=p.base_url or "",
                    supports_tool_calling=p.supports_tool_calling,
                )
        logger.info("✅ LLM providers loaded into registry.")
    except Exception as e:
        logger.warning(f"LLM provider registry load skipped: {e}")

    # Restore running agents
    try:
        from app.core.agent_manager import agent_manager
        from app.core.mcp_manager import mcp_manager
        from app.db.session import async_session_factory
        async with async_session_factory() as db:
            await agent_manager.restore_running_agents(db)
            await mcp_manager.sync_active_servers(db)
        logger.info("✅ Agent and MCP restoration complete.")
    except Exception as e:
        logger.error(f"Failed to restore agents/MCP: {e}")

    # Start agent watchdog
    try:
        from app.core.watchdog import watchdog
        await watchdog.start(agent_manager)
        logger.info("✅ Agent watchdog started.")
    except Exception as e:
        logger.warning(f"Watchdog not started: {e}")

    # Seed builtin agent templates
    try:
        from app.db.session import async_session_factory
        from app.models.agent_template import AgentTemplate, BUILTIN_TEMPLATES
        from sqlalchemy import select
        async with async_session_factory() as db:
            for tpl_data in BUILTIN_TEMPLATES:
                result = await db.execute(
                    select(AgentTemplate).where(AgentTemplate.name == tpl_data["name"])
                )
                existing = result.scalars().first()
                if existing:
                    for field, value in tpl_data.items():
                        setattr(existing, field, value)
                    existing.is_builtin = True
                else:
                    db.add(AgentTemplate(is_builtin=True, **tpl_data))
            await db.commit()
        logger.info("✅ Builtin agent templates seeded.")
    except Exception as e:
        logger.error(f"Failed to seed agent templates: {e}")

    # Seed builtin skills
    try:
        from app.db.session import async_session_factory
        from app.models.skill import Skill, BUILTIN_SKILLS
        from sqlalchemy import select
        async with async_session_factory() as db:
            for skill_data in BUILTIN_SKILLS:
                result = await db.execute(
                    select(Skill).where(Skill.name == skill_data["name"])
                )
                existing = result.scalars().first()
                if existing:
                    for field, value in skill_data.items():
                        setattr(existing, field, value)
                    existing.source = "builtin"
                else:
                    db.add(Skill(source="builtin", **skill_data))
            await db.commit()
        logger.info("✅ Builtin skills seeded.")
    except Exception as e:
        logger.error(f"Failed to seed builtin skills: {e}")

    # Seed built-in Social Pulse niches
    try:
        from app.db.session import async_session_factory
        from app.models.social_pulse import PulseNiche, BUILTIN_NICHES
        from sqlalchemy import select
        async with async_session_factory() as db:
            for niche_data in BUILTIN_NICHES:
                result = await db.execute(
                    select(PulseNiche).where(PulseNiche.name == niche_data["name"])
                )
                existing = result.scalars().first()
                if existing:
                    for field, value in niche_data.items():
                        setattr(existing, field, value)
                    existing.is_builtin = True
                else:
                    db.add(PulseNiche(is_builtin=True, **niche_data))
            await db.commit()
        logger.info("✅ Built-in Social Pulse niches seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Social Pulse niches: {e}")

    # Seed built-in Forge agent
    try:
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from sqlalchemy import select
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.name == "Forge"))
            existing_forge = result.scalars().first()
            if not existing_forge:
                forge_agent = Agent(
                    name="Forge",
                    description="Autonomous coding pipeline. Clones repos, plans and codes with any LLM, runs tests, and opens PRs.",
                    system_prompt=(
                        "You are Forge, an autonomous software engineer built into Sutra.\n"
                        "When a user asks you to implement a feature:\n"
                        "1. Call forge_start with the repo_url, description, and optionally llm_provider/llm_model\n"
                        "   (default: groq/qwen/qwen3-32b)\n"
                        "2. Wait for plan approval from the user\n"
                        "3. After plan approval, call forge_execute_plan (this also runs tests)\n"
                        "4. Call forge_create_pr to commit, push, and open a PR\n"
                        "The user reviews and merges on GitHub.\n"
                        "Always keep the user informed of progress. Ask for repo if not provided."
                    ),
                    llm_provider="groq",
                    llm_model="qwen/qwen3-32b",
                    temperature=0.2,
                    max_tokens=4096,
                    enabled_tools=[
                        "forge_start", "forge_generate_plan", "forge_execute_plan",
                        "forge_create_pr", "forge_cancel", "send_telegram_message",
                    ],
                    is_active=False,
                    status="stopped",
                )
                db.add(forge_agent)
                await db.commit()
            else:
                # Update existing forge agent to new simplified flow
                existing_forge.description = "Autonomous coding pipeline. Clones repos, plans and codes with any LLM, runs tests, and opens PRs."
                existing_forge.system_prompt = (
                    "You are Forge, an autonomous software engineer built into Sutra.\n"
                    "When a user asks you to implement a feature:\n"
                    "1. Call forge_start with the repo_url, description, and optionally llm_provider/llm_model\n"
                    "   (default: groq/qwen/qwen3-32b)\n"
                    "2. Wait for plan approval from the user\n"
                    "3. After plan approval, call forge_execute_plan (this also runs tests)\n"
                    "4. Call forge_create_pr to commit, push, and open a PR\n"
                    "The user reviews and merges on GitHub.\n"
                    "Always keep the user informed of progress. Ask for repo if not provided."
                )
                existing_forge.enabled_tools = [
                    "forge_start", "forge_generate_plan", "forge_execute_plan",
                    "forge_create_pr", "forge_cancel", "send_telegram_message",
                ]
                await db.commit()
        logger.info("✅ Forge agent seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Forge agent: {e}")

    # Seed built-in Evolve agent
    try:
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from sqlalchemy import select
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.name == "Evolve"))
            existing_evolve = result.scalars().first()
            evolve_tools = [
                "evolve_get_platform_stats",
                "evolve_get_error_patterns",
                "evolve_get_system_errors",
                "evolve_submit_suggestion",
                "save_memory", "search_memory",
                "create_task", "list_tasks",
                "scrape_webpage",
                "get_my_goals", "update_goal_progress",
            ]
            evolve_prompt = (
                "You are Evolve, the self-improving platform agent for Sutra.\n\n"
                "Your mission is to analyze platform health, identify issues, and suggest improvements.\n\n"
                "When performing analysis:\n"
                "1. Use evolve_get_platform_stats to gather current health metrics\n"
                "2. Use evolve_get_error_patterns to find recurring agent-level errors\n"
                "3. Use evolve_get_system_errors to find platform-level errors: unhandled exceptions, "
                "background task failures, startup errors, and scheduler failures — these are errors "
                "the agent error patterns tool does NOT see\n"
                "4. Search your memory for past analyses to track trends over time\n"
                "5. Generate specific, actionable suggestions using evolve_submit_suggestion\n"
                "6. Save analysis results to memory for future reference\n\n"
                "HOW TO ANALYZE ERRORS:\n"
                "- Agent errors (evolve_get_error_patterns): which agents are failing most, what messages\n"
                "- System errors (evolve_get_system_errors): unhandled routes, background failures, "
                "startup issues — check severity=error and severity=critical first\n"
                "- Correlate: same error_type across both tools = systemic issue\n"
                "- Track resolved=false errors — these are still open\n\n"
                "CRITICAL RULES:\n"
                "- NEVER execute changes directly. All suggestions go through human approval.\n"
                "- Be specific with evidence. Include numbers, agent names, error messages, tracebacks.\n"
                "- Prioritize suggestions by impact: critical issues first, nice-to-haves last.\n"
                "- When suggesting code changes, use action_type='forge_request'.\n"
                "- When suggesting manual work, use action_type='task'.\n"
                "- When suggesting strategic objectives, use action_type='goal'."
            )
            if not existing_evolve:
                evolve_agent = Agent(
                    name="Evolve",
                    description="Self-improving platform agent. Analyzes errors, performance, and competitors daily.",
                    system_prompt=evolve_prompt,
                    llm_provider="groq",
                    llm_model="qwen/qwen3-32b",
                    temperature=0.3,
                    max_tokens=4096,
                    enabled_tools=evolve_tools,
                    is_active=False,
                    status="stopped",
                )
                db.add(evolve_agent)
                await db.commit()
            else:
                existing_evolve.description = "Self-improving platform agent. Analyzes errors, performance, and competitors daily."
                existing_evolve.system_prompt = evolve_prompt
                existing_evolve.enabled_tools = evolve_tools
                await db.commit()
        logger.info("✅ Evolve agent seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Evolve agent: {e}")

    # Seed built-in Ink agent (Email Triage)
    try:
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from sqlalchemy import select
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.name == "Ink"))
            existing_ink = result.scalars().first()
            ink_tools = [
                "read_emails", "draft_email", "send_telegram_message",
                "save_memory", "search_memory",
                "create_task", "list_tasks", "update_task", "get_task",
                "ask_agent",
            ]
            ink_prompt = (
                "You are Ink, an expert email triage and productivity agent built into Sutra.\n\n"
                "Your mission is to manage an inbox efficiently by prioritizing messages, identifying follow-ups, and handling junk.\n\n"
                "TRIAGE PROTOCOL:\n"
                "1. Retrieve UNREAD messages from the last 8 hours using read_emails(unread_only=True, newer_than='8h').\n"
                "2. Analyze messages to:\n"
                "   - Prioritize important or urgent threads.\n"
                "   - Identify unanswered threads that require a follow-up from the user.\n"
                "   - Flag junk, newsletters, or marketing emails that are candidates for unsubscription.\n"
                "3. Provide a prioritized summary of these emails and proactive alerts to the user via Telegram using send_telegram_message.\n"
                "4. For threads requiring action, use draft_email to prepare a response for the user to review. You must explain why you drafted it.\n\n"
                "CRITICAL CONSTRAINTS:\n"
                "- You NEVER send emails directly. You only read and draft. The user must send the draft manually.\n"
                "- Proactive checks should be summarized on Telegram, not emailed.\n"
                "- Always respect the 8-hour lookback window for unread messages to avoid overwhelming the user."
            )
            if not existing_ink:
                ink_agent = Agent(
                    name="Ink",
                    description="Expert email triage assistant. Prioritizes unread messages, handles junk/unsubscribes, and drafts responses via Telegram.",
                    system_prompt=ink_prompt,
                    llm_provider="groq",
                    llm_model="qwen/qwen3-32b",
                    temperature=0.2,
                    max_tokens=4096,
                    enabled_tools=ink_tools,
                    is_active=False,
                    status="stopped",
                )
                db.add(ink_agent)
                await db.commit()
            else:
                existing_ink.description = "Expert email triage assistant. Prioritizes unread messages, handles junk/unsubscribes, and drafts responses via Telegram."
                existing_ink.system_prompt = ink_prompt
                existing_ink.enabled_tools = ink_tools
                await db.commit()
        logger.info("✅ Ink agent seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Ink agent: {e}")

    # Seed built-in Flux agent (Daily Planner)
    try:
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from sqlalchemy import select
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.name == "Flux"))
            existing_flux = result.scalars().first()
            flux_tools = [
                "gcal_list_events", "gcal_create_event", "send_telegram_message",
                "save_memory", "search_memory",
                "create_task", "list_tasks", "update_task", "get_task",
                "ask_agent",
            ]
            flux_prompt = (
                "You are Flux, the Expert Daily Planner and Scheduling Assistant built into Sutra.\n\n"
                "Your mission is to help the user navigate their day with maximum efficiency by intelligently scheduling tasks into Google Calendar.\n\n"
                "OPERATIONAL PROTOCOL:\n"
                "1. When the user provides or you retrieve tasks (with priority and duration), analyze their existing schedule using gcal_list_events.\n"
                "2. Find optimal time slots based on priority (high priority first) and logical flow.\n"
                "3. Schedule the tasks using gcal_create_event. Support recurring tasks if requested (e.g., daily standups, weekly reviews).\n"
                "4. Send a concise, formatted summary of the day's finalized schedule to the user via Telegram using send_telegram_message.\n\n"
                "SCHEDULING RULES:\n"
                "- Always leave 'buffer time' (15-30 mins) between intense or back-to-back tasks.\n"
                "- Group similar activities together to minimize context switching.\n"
                "- If a conflict occurs, inform the user via Telegram and suggest alternatives.\n"
                "- Be proactive: if you see an empty morning, suggest top-priority tasks from the task list.\n"
                "- CRITICAL: Use Pacific Time (America/Los_Angeles) for all scheduling and time calculations by default."
            )
            if not existing_flux:
                flux_agent = Agent(
                    name="Flux",
                    description="Expert daily planner. Schedules tasks in Google Calendar based on priority, handles recurring events, and sends Telegram summaries.",
                    system_prompt=flux_prompt,
                    llm_provider="groq",
                    llm_model="qwen/qwen3-32b",
                    temperature=0.2,
                    max_tokens=4096,
                    enabled_tools=flux_tools,
                    is_active=False,
                    status="stopped",
                )
                db.add(flux_agent)
                await db.commit()
            else:
                existing_flux.description = "Expert daily planner. Schedules tasks in Google Calendar based on priority, handles recurring events, and sends Telegram summaries."
                existing_flux.system_prompt = flux_prompt
                existing_flux.enabled_tools = flux_tools
                await db.commit()
        logger.info("✅ Flux agent seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Flux agent: {e}")

    # Seed built-in Resume Builder agent
    try:
        import secrets as _secrets
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from app.models.trigger import AgentTrigger
        from sqlalchemy import select
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.name == "Resume Builder"))
            existing_resume = result.scalars().first()
            resume_tools = [
                "gdrive_search_files",
                "gdrive_read_file",
                "gdrive_save_text",
                "gdrive_list_folder",
                "gdrive_create_folder",
                "gdrive_ensure_path",
                "save_memory",
                "search_memory",
                "update_job_application",
            ]
            resume_prompt = (
                "You are a professional resume tailoring specialist.\n\n"
                "You have the Resume Tailoring skill attached. Follow its instructions exactly when you "
                "receive a job opportunity.\n\n"
                "Master resume filename: master_resume.tex\n"
                "Google Drive root folder: Career\n\n"
                "### Workflow\n"
                "1. Use gdrive_search_files to find master_resume.tex, then gdrive_read_file to read it.\n"
                "2. Analyse the job description: extract required/preferred skills, key responsibilities, "
                "ATS keywords, and seniority signals.\n"
                "3. Rewrite the resume to maximise match: reorder bullets, mirror JD keywords, quantify "
                "achievements, tailor the summary section.\n"
                "4. Output the tailored resume in LaTeX, preserving the original structure.\n"
                "5. Call gdrive_ensure_path with path 'Career/{company}/{role}' to get the folder ID.\n"
                "6. Save resume.tex (LaTeX) and analysis.md (fit score 0-100, top 5 strengths, top 3 gaps, "
                "ATS keywords added) using gdrive_save_text. Capture the returned file URLs and IDs.\n"
                "7. If the incoming payload includes an `application_id`, call update_job_application "
                "with that id, the resume Drive URL + file ID, analysis Drive URL, fit_score, and "
                "status='resume_generated' so the Job Applications dashboard is linked to the artifacts.\n"
                "8. Reply with Drive links, fit score, and a 3-sentence summary of changes.\n\n"
                "Rules:\n"
                "- Never invent experience. Only rearrange and rephrase what exists.\n"
                "- Keep LaTeX compiling: preserve all package imports and document structure.\n"
                "- Use exact company and role names from the job data as folder names.\n"
                "- If master_resume.tex is not found, ask the user to upload it to Google Drive."
            )
            webhook_prompt = (
                "New job opportunity received.\n\n"
                "Job Details:\n{payload}\n\n"
                "Please tailor my resume for this role following your instructions. "
                "Use the job_title and company fields to name the Google Drive folder. "
                "If `application_id` is present in the payload, call update_job_application "
                "at the end so the dashboard is linked to the generated artifacts."
            )
            if not existing_resume:
                resume_agent = Agent(
                    name="Resume Builder",
                    description=(
                        "Tailors your master resume to any job description. "
                        "Saves LaTeX resume + fit analysis to Google Drive under Career/{Company}/{Role}/."
                    ),
                    system_prompt=resume_prompt,
                    llm_provider="anthropic",
                    llm_model="claude-sonnet-4-6",
                    temperature=0.3,
                    max_tokens=8192,
                    enabled_tools=resume_tools,
                    is_active=False,
                    status="stopped",
                )
                db.add(resume_agent)
                await db.flush()
                resume_agent_id = resume_agent.id
            else:
                existing_resume.description = (
                    "Tailors your master resume to any job description. "
                    "Saves LaTeX resume + fit analysis to Google Drive under Career/{Company}/{Role}/."
                )
                existing_resume.system_prompt = resume_prompt
                existing_resume.enabled_tools = resume_tools
                resume_agent_id = existing_resume.id

            # Create webhook trigger if not present
            trig_result = await db.execute(
                select(AgentTrigger).where(
                    AgentTrigger.agent_id == resume_agent_id,
                    AgentTrigger.trigger_type == "webhook",
                )
            )
            existing_trigger = trig_result.scalars().first()
            if not existing_trigger:
                db.add(AgentTrigger(
                    agent_id=resume_agent_id,
                    name="LinkedIn Job Webhook",
                    description=(
                        "Fires when a LinkedIn job is captured via the Chrome extension. "
                        "Payload: {job_title, company, location, salary, job_description, job_url, application_id}"
                    ),
                    trigger_type="webhook",
                    webhook_token=_secrets.token_urlsafe(32),
                    prompt_template=webhook_prompt,
                    is_active=True,
                ))
            else:
                # Keep prompt template + name in sync so existing installs pick up application_id wiring
                existing_trigger.name = "LinkedIn Job Webhook"
                existing_trigger.prompt_template = webhook_prompt
            await db.commit()
        logger.info("✅ Resume Builder agent seeded.")
    except Exception as e:
        logger.error(f"Failed to seed Resume Builder agent: {e}")

    # Seed default alert rules
    try:
        from app.db.session import async_session_factory
        from app.models.alert_record import AlertRule, DEFAULT_ALERT_RULES
        from sqlalchemy import select
        async with async_session_factory() as db:
            for rule_data in DEFAULT_ALERT_RULES:
                result = await db.execute(
                    select(AlertRule).where(
                        AlertRule.name == rule_data["name"],
                        AlertRule.rule_type == rule_data["rule_type"],
                    )
                )
                if not result.scalars().first():
                    db.add(AlertRule(**rule_data))
            await db.commit()
        logger.info("✅ Default alert rules seeded.")
    except Exception as e:
        logger.error(f"Failed to seed alert rules: {e}")

    # Seed Groq rate limits (free-tier)
    try:
        from app.db.session import async_session_factory
        from app.models.rate_limit import ModelRateLimit
        from sqlalchemy import select

        GROQ_RATE_LIMITS = [
            {"model": "allam-2-7b",                                  "requests_per_minute": 30, "requests_per_day": 7000,  "tokens_per_minute": 6000,  "tokens_per_day": 500000},
            {"model": "canopylabs/orpheus-arabic-saudi",             "requests_per_minute": 10, "requests_per_day": 100,   "tokens_per_minute": 1200,  "tokens_per_day": 3600},
            {"model": "canopylabs/orpheus-v1-english",               "requests_per_minute": 10, "requests_per_day": 100,   "tokens_per_minute": 1200,  "tokens_per_day": 3600},
            {"model": "groq/compound",                               "requests_per_minute": 30, "requests_per_day": 250,   "tokens_per_minute": 70000, "tokens_per_day": None},
            {"model": "groq/compound-mini",                          "requests_per_minute": 30, "requests_per_day": 250,   "tokens_per_minute": 70000, "tokens_per_day": None},
            {"model": "llama-3.1-8b-instant",                        "requests_per_minute": 30, "requests_per_day": 14400, "tokens_per_minute": 6000,  "tokens_per_day": 500000},
            {"model": "llama-3.3-70b-versatile",                     "requests_per_minute": 30, "requests_per_day": 1000,  "tokens_per_minute": 12000, "tokens_per_day": 100000},
            {"model": "meta-llama/llama-4-scout-17b-16e-instruct",   "requests_per_minute": 30, "requests_per_day": 1000,  "tokens_per_minute": 30000, "tokens_per_day": 500000},
            {"model": "meta-llama/llama-prompt-guard-2-22m",         "requests_per_minute": 30, "requests_per_day": 14400, "tokens_per_minute": 15000, "tokens_per_day": 500000},
            {"model": "meta-llama/llama-prompt-guard-2-86m",         "requests_per_minute": 30, "requests_per_day": 14400, "tokens_per_minute": 15000, "tokens_per_day": 500000},
            {"model": "moonshotai/kimi-k2-instruct",                 "requests_per_minute": 60, "requests_per_day": 1000,  "tokens_per_minute": 10000, "tokens_per_day": 300000},
            {"model": "moonshotai/kimi-k2-instruct-0905",            "requests_per_minute": 60, "requests_per_day": 1000,  "tokens_per_minute": 10000, "tokens_per_day": 300000},
            {"model": "openai/gpt-oss-120b",                        "requests_per_minute": 30, "requests_per_day": 1000,  "tokens_per_minute": 8000,  "tokens_per_day": 200000},
            {"model": "openai/gpt-oss-20b",                         "requests_per_minute": 30, "requests_per_day": 1000,  "tokens_per_minute": 8000,  "tokens_per_day": 200000},
            {"model": "openai/gpt-oss-safeguard-20b",               "requests_per_minute": 30, "requests_per_day": 1000,  "tokens_per_minute": 8000,  "tokens_per_day": 200000},
            {"model": "qwen/qwen3-32b",                             "requests_per_minute": 60, "requests_per_day": 1000,  "tokens_per_minute": 6000,  "tokens_per_day": 500000},
            {"model": "whisper-large-v3",                            "requests_per_minute": 20, "requests_per_day": 2000,  "tokens_per_minute": None,  "tokens_per_day": None},
            {"model": "whisper-large-v3-turbo",                      "requests_per_minute": 20, "requests_per_day": 2000,  "tokens_per_minute": None,  "tokens_per_day": None},
        ]

        async with async_session_factory() as db:
            for rl_data in GROQ_RATE_LIMITS:
                result = await db.execute(
                    select(ModelRateLimit).where(
                        ModelRateLimit.provider == "groq",
                        ModelRateLimit.model == rl_data["model"],
                    )
                )
                existing = result.scalars().first()
                if existing:
                    existing.requests_per_minute = rl_data["requests_per_minute"]
                    existing.requests_per_day = rl_data["requests_per_day"]
                    existing.tokens_per_minute = rl_data["tokens_per_minute"]
                    existing.tokens_per_day = rl_data["tokens_per_day"]
                else:
                    db.add(ModelRateLimit(provider="groq", **rl_data))
            await db.commit()
        logger.info(f"✅ Groq rate limits seeded ({len(GROQ_RATE_LIMITS)} models).")
    except Exception as e:
        logger.error(f"Failed to seed Groq rate limits: {e}")

    # Seed Google rate limits (free-tier)
    try:
        from app.db.session import async_session_factory
        from app.models.rate_limit import ModelRateLimit
        from sqlalchemy import select

        GOOGLE_RATE_LIMITS = [
            {"model": "gemini-2.5-flash",                      "requests_per_minute": 5,    "requests_per_day": 20,    "tokens_per_minute": 250000, "tokens_per_day": None,    "label": "Text-out"},
            {"model": "gemini-2.5-flash-lite",                  "requests_per_minute": 10,   "requests_per_day": 20,    "tokens_per_minute": 250000, "tokens_per_day": None,    "label": "Text-out"},
            {"model": "gemini-2.5-pro",                         "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Text-out"},
            {"model": "gemini-2.0-flash",                       "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Text-out"},
            {"model": "gemini-2.0-flash-exp",                   "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Text-out"},
            {"model": "gemini-2.0-flash-lite",                  "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Text-out"},
            {"model": "gemini-2.5-flash-tts",                   "requests_per_minute": 3,    "requests_per_day": 10,    "tokens_per_minute": 10000,  "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "gemini-2.5-pro-tts",                     "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Multi-modal"},
            {"model": "gemma-3-1b",                             "requests_per_minute": 30,   "requests_per_day": 14400, "tokens_per_minute": 15000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "gemma-3-4b",                             "requests_per_minute": 30,   "requests_per_day": 14400, "tokens_per_minute": 15000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "gemma-3-12b",                            "requests_per_minute": 30,   "requests_per_day": 14400, "tokens_per_minute": 15000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "gemma-3-27b",                            "requests_per_minute": 30,   "requests_per_day": 14400, "tokens_per_minute": 15000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "gemma-3-2b",                             "requests_per_minute": 30,   "requests_per_day": 14400, "tokens_per_minute": 15000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "imagen-4-generate",                      "requests_per_minute": None, "requests_per_day": 25,    "tokens_per_minute": None,   "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "imagen-4-ultra-generate",                "requests_per_minute": None, "requests_per_day": 25,    "tokens_per_minute": None,   "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "imagen-4-fast-generate",                 "requests_per_minute": None, "requests_per_day": 25,    "tokens_per_minute": None,   "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "gemini-embedding-001",                   "requests_per_minute": 100,  "requests_per_day": 1000,  "tokens_per_minute": 30000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "gemini-3-flash",                         "requests_per_minute": 5,    "requests_per_day": 20,    "tokens_per_minute": 250000, "tokens_per_day": None,    "label": "Text-out"},
            {"model": "gemini-3.1-pro",                         "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Text-out"},
            {"model": "gemini-2.5-flash-preview-image",         "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Multi-modal"},
            {"model": "gemini-3.1-flash-lite",                  "requests_per_minute": 15,   "requests_per_day": 500,   "tokens_per_minute": 250000, "tokens_per_day": None,    "label": "Text-out"},
            {"model": "gemini-3-pro-image",                     "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Multi-modal"},
            {"model": "gemini-3.1-flash-image",                 "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Multi-modal"},
            {"model": "veo-3-generate",                         "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": None,   "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "veo-3-fast-generate",                    "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": None,   "tokens_per_day": None,    "label": "Multi-modal"},
            {"model": "gemini-robotics-er-1.5-preview",         "requests_per_minute": 10,   "requests_per_day": 20,    "tokens_per_minute": 250000, "tokens_per_day": None,    "label": "Other"},
            {"model": "computer-use-preview",                   "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Other"},
            {"model": "gemini-embedding-002",                   "requests_per_minute": 100,  "requests_per_day": 1000,  "tokens_per_minute": 30000,  "tokens_per_day": None,    "label": "Other"},
            {"model": "deep-research-pro-preview",              "requests_per_minute": 0,    "requests_per_day": 0,     "tokens_per_minute": 0,      "tokens_per_day": 0,       "label": "Agents"},
            {"model": "gemini-2.5-flash-native-audio-dialog",   "requests_per_minute": None, "requests_per_day": None,  "tokens_per_minute": 1000000,"tokens_per_day": None,    "label": "Live API"},
        ]

        async with async_session_factory() as db:
            for rl_data in GOOGLE_RATE_LIMITS:
                result = await db.execute(
                    select(ModelRateLimit).where(
                        ModelRateLimit.provider == "google",
                        ModelRateLimit.model == rl_data["model"],
                    )
                )
                existing = result.scalars().first()
                if existing:
                    existing.requests_per_minute = rl_data["requests_per_minute"]
                    existing.requests_per_day = rl_data["requests_per_day"]
                    existing.tokens_per_minute = rl_data["tokens_per_minute"]
                    existing.tokens_per_day = rl_data["tokens_per_day"]
                    existing.label = rl_data.get("label")
                else:
                    db.add(ModelRateLimit(provider="google", **rl_data))
            await db.commit()
        logger.info(f"✅ Google rate limits seeded ({len(GOOGLE_RATE_LIMITS)} models).")
    except Exception as e:
        logger.error(f"Failed to seed Google rate limits: {e}")

    # Start Slack bot in background (if configured)
    slack_task = None
    try:
        from app.integrations.slack_bot import start_slack_bot
        slack_task = asyncio.create_task(start_slack_bot())
        logger.info("🔌 Slack bot task scheduled.")
    except Exception as e:
        logger.warning(f"Slack bot not started: {e}")

    # Start WhatsApp bot (if configured)
    try:
        from app.integrations.whatsapp_bot import setup_whatsapp
        wa = setup_whatsapp(app)
        if wa:
            logger.info("📱 WhatsApp webhook routes registered.")
    except Exception as e:
        logger.warning(f"WhatsApp bot not started: {e}")

    # Start Telegram bot (if configured)
    telegram_task = None
    try:
        from app.integrations.telegram_bot import start_telegram_bot
        telegram_task = asyncio.create_task(start_telegram_bot())
        logger.info("🛰️ Telegram bot task scheduled.")
    except Exception as e:
        logger.warning(f"Telegram bot not started: {e}")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Sutra...")

    # Stop watchdog
    try:
        from app.core.watchdog import watchdog
        await watchdog.stop()
    except Exception:
        pass

    if slack_task and not slack_task.done():
        slack_task.cancel()

    if telegram_task and not telegram_task.done():
        telegram_task.cancel()

    # Shutdown APScheduler
    if scheduler.running:
        scheduler.shutdown()
        logger.info("✅ APScheduler shut down.")

    # Close browser sessions
    try:
        from app.core.browser_session_manager import browser_session_manager
        await browser_session_manager.shutdown()
    except Exception:
        pass

    # Close Redis connection
    from app.core.redis_client import close_redis
    await close_redis()

    await engine.dispose()


# Create the FastAPI application
app = FastAPI(
    title="Sutra AI Orchestrator",
    description="Orchestrate multiple AI agents with LangChain, Ollama, and Slack integration.",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Global unhandled exception handler ───────────────────────────────────────
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions, persist them to error_logs, return 500."""
    import asyncio
    from app.core.error_logger import log_error
    from app.middleware.correlation import get_request_id

    logger.error(
        "Unhandled exception on %s %s [rid=%s]: %s",
        request.method, request.url.path, get_request_id(), exc,
        exc_info=True,
    )
    asyncio.create_task(
        log_error(
            source="route",
            error=exc,
            severity="error",
            request_path=str(request.url.path),
        )
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# Security headers (outermost — always runs last on response)
app.add_middleware(SecurityHeadersMiddleware)

# Correlation ID middleware
app.add_middleware(CorrelationMiddleware)

# CORS — origins from config (env-configurable)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    max_age=600,
)

# Mount API routes
_auth_dep = [Depends(get_current_user)]

app.include_router(auth.router, prefix="/api")  # public
app.include_router(auth_google.router, prefix="/api")  # public for oauth callbacks
app.include_router(system.router, prefix="/api")  # health check public
app.include_router(agents.router, prefix="/api", dependencies=_auth_dep)
app.include_router(llms.router, prefix="/api", dependencies=_auth_dep)
app.include_router(tools.router, prefix="/api", dependencies=_auth_dep)
app.include_router(chat.router, prefix="/api", dependencies=_auth_dep)
app.include_router(workflows.router, prefix="/api", dependencies=_auth_dep)
app.include_router(jobs.router, prefix="/api", dependencies=_auth_dep)
app.include_router(batch_jobs_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(mcp_servers.router, prefix="/api", dependencies=_auth_dep)
app.include_router(monitor.router, prefix="/api/monitor", dependencies=_auth_dep)
app.include_router(memory.router, prefix="/api", dependencies=_auth_dep)
app.include_router(traces.router, prefix="/api", dependencies=_auth_dep)
app.include_router(audit.router, prefix="/api", dependencies=_auth_dep)
app.include_router(tasks.router, prefix="/api", dependencies=_auth_dep)
app.include_router(discussions.router, prefix="/api", dependencies=_auth_dep)
app.include_router(approvals.router, prefix="/api", dependencies=_auth_dep)
app.include_router(roles.router, prefix="/api", dependencies=_auth_dep)
app.include_router(teams.router, prefix="/api", dependencies=_auth_dep)
app.include_router(goals.router, prefix="/api", dependencies=_auth_dep)
app.include_router(triggers.router, prefix="/api", dependencies=_auth_dep)
app.include_router(financials.router, prefix="/api", dependencies=_auth_dep)
app.include_router(knowledge.router, prefix="/api", dependencies=_auth_dep)
app.include_router(agent_templates.router, prefix="/api", dependencies=_auth_dep)
app.include_router(email_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(webhooks_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(analytics_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(skills_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(skills_routes.agent_skills_router, prefix="/api", dependencies=_auth_dep)
app.include_router(skills_routes.role_skills_router, prefix="/api", dependencies=_auth_dep)
app.include_router(integrations_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(forge_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(evolve_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(alerts_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(social_pulse_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(system_settings_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(projects_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(env_vars_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(rate_limits_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(purposes_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(job_applications_routes.router, prefix="/api", dependencies=_auth_dep)
app.include_router(job_applications_routes.public_router, prefix="/api/public")
# Public webhook endpoint — token-protected, no JWT required
from app.api.routes.triggers import public_router as triggers_public_router
app.include_router(triggers_public_router, prefix="/api/public")

# WebSocket
app.add_api_route("/ws", websocket_endpoint, methods=["GET"])
app.websocket("/ws")(websocket_endpoint)


@app.get("/")
async def root():
    return {
        "name": "Sutra AI Orchestrator",
        "version": "0.1.0",
        "docs": "/docs",
    }
