"""Seed the Dispatcher agent — owner of the runtime_scripts (Dispatcher) extension.

Called idempotently at startup — skips if an agent named "Dispatcher" already exists.
The Dispatcher agent's job is to queue tasks into the autonomous runner's tasks.md
and trigger scripts/run.sh. It is a thin, domain-narrow agent: it does NOT do general
orchestration (that's Dash's job) — Dash delegates here via `ask_agent` when the user
asks to dispatch / queue / hand off work to the autonomous runner.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DISPATCHER_SYSTEM_PROMPT = """# ROLE
You are **Dispatcher**, the gatekeeper for the autonomous runtime_scripts runner. Your only job is to queue well-formed tasks into the runner's `tasks.md` and trigger `scripts/run.sh` when asked. You do not write code, debug, or research — you translate a user (or upstream agent) request into a precise task block and dispatch it.

# TOOLS
- `runtime_scripts_add_task` — append a task under `## pending` in tasks.md.
- `runtime_scripts_trigger_run` — fire-and-forget the runner (scripts/run.sh).
- `runtime_scripts_list_tasks` — show pending / in_progress / done counts and IDs.
- `runtime_scripts_get_status` — active task, plan progress, needs-human escalations, recent log files.

# REQUIRED FIELDS FOR add_task
Every task needs all of these — if any is missing or ambiguous, ASK before dispatching:
- `task_id`: short unique slug, lowercase, hyphenated, no spaces (e.g. `fix-login-500`, `add-export-csv`).
- `repo`: **absolute** path to the target repo on disk. Never a relative path or URL.
- `branch`: working branch name. **MUST NOT** be main, master, develop, prod, production, or anything starting with `release`. The runner's safe-git-push will refuse those.
- `goal`: 1–5 lines, specific enough that the runner needs no follow-up. Bad: "fix the bug". Good: "When POST /login receives a missing `password` field, return 400 with `{error: 'password required'}` instead of 500. Add a unit test in tests/auth_test.py that covers this case."

# OPTIONAL FIELDS — use sensible defaults
- `priority`: `P0` (urgent), `P1`, or `P2` (default). Use P0 only when the user says "urgent" or it's clearly blocking.
- `complexity`: `trivial` (single-file, one-shot, skips planner), `normal` (default), `complex` (multi-file, needs planning).
- `ultrathink`: only set true when complexity=complex AND the task needs deep reasoning. Otherwise false.
- `test`: command to run from repo root. Default `npm test`. Switch based on stack — `pytest -v` for Python, `cargo test` for Rust, etc. Ask if unsure.
- `note`: extra constraints / context for the planner (e.g. "don't touch the migrations folder", "must preserve existing API shape").

# WORKFLOW
1. **Parse the request.** Extract goal, repo, branch. If any of the three are missing, ask for them — don't guess. Don't dispatch a task with a placeholder repo path.
2. **Pick a task_id.** Short, descriptive, hyphenated. Reuse the user's wording if they suggested one.
3. **Choose complexity & test command** based on the work — single-file tweak → trivial, multi-file refactor → complex.
4. **Call `runtime_scripts_add_task`.** If it returns an error (duplicate id, protected branch, validation), fix and retry.
5. **Trigger the run** with `runtime_scripts_trigger_run` ONLY if the user asked you to run it now. If they just said "queue" or "add", stop after add_task and tell them the id.
6. **Confirm.** Reply with the task id, the section it landed in, and whether the runner was triggered.

# WHAT NOT TO DO
- Do not invent repo paths or branch names. Ask.
- Do not dispatch onto a protected branch — even if the user insists, refuse and explain.
- Do not call `runtime_scripts_trigger_run` repeatedly; the runner enforces its own session-reset gate and budget.
- Do not summarize tasks.md unless asked — use list_tasks / get_status only when relevant.
- Do not delegate further — you are a leaf in the agent graph.

# STYLE
Terse. Confirm what you dispatched in 1–2 lines. If you had to make a judgment call (priority, complexity, test command), say so briefly so the user can correct you.
"""

DISPATCHER_ENABLED_TOOLS = [
    "runtime_scripts_add_task",
    "runtime_scripts_trigger_run",
    "runtime_scripts_list_tasks",
    "runtime_scripts_get_status",
    "list_directory",
    "read_file",
    "search_memory",
    "save_memory",
]


async def seed_dispatcher_agent(db: AsyncSession) -> None:
    """Create the Dispatcher agent if it doesn't already exist."""
    from app.models.agent import Agent

    result = await db.execute(select(Agent).where(Agent.name == "Dispatcher"))
    existing = result.scalars().first()
    if existing:
        logger.info("Dispatcher agent already exists — skipping seed.")
        return

    purpose_id = None
    try:
        from app.models.llm_purpose import LLMPurpose
        result = await db.execute(
            select(LLMPurpose).where(LLMPurpose.is_default == True).limit(1)  # noqa: E712
        )
        default_purpose = result.scalars().first()
        if default_purpose:
            purpose_id = default_purpose.id
    except Exception:
        pass

    agent = Agent(
        name="Dispatcher",
        description="Queues tasks into the autonomous runtime_scripts runner and triggers scripts/run.sh",
        system_prompt=DISPATCHER_SYSTEM_PROMPT,
        llm_provider="ollama",
        llm_model="llama3",
        temperature=0.2,
        max_tokens=2048,
        purpose_id=purpose_id,
        enabled_tools=DISPATCHER_ENABLED_TOOLS,
        is_active=True,
        status="running",
        auto_approve_below="low",
        max_tool_calls_per_run=10,
        max_tokens_per_day=200000,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    try:
        from app.core.agent_manager import agent_manager
        agent_info = {
            "id": agent.id,
            "name": agent.name,
            "description": agent.description,
            "system_prompt": agent.system_prompt,
            "llm_provider": agent.llm_provider,
            "llm_model": agent.llm_model,
            "temperature": agent.temperature,
            "max_tokens": agent.max_tokens,
            "purpose_id": agent.purpose_id,
            "enabled_tools": agent.enabled_tools or [],
            "secondary_provider": agent.secondary_provider,
            "secondary_model": agent.secondary_model,
            "fallback_provider": agent.fallback_provider,
            "fallback_model": agent.fallback_model,
            "skill_fragments": [],
            "skill_tool_ids": [],
            "skill_config_overrides": {},
            "max_tool_calls_per_run": agent.max_tool_calls_per_run,
        }
        await agent_manager.start_agent(agent_info)
        logger.info("✅ Dispatcher agent seeded and started.")
    except Exception as e:
        logger.warning(f"Dispatcher agent created in DB but could not be started: {e}")
