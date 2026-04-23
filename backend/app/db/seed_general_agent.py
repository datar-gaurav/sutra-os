"""Seed the Dash general-purpose orchestrator agent.

Called idempotently at startup — skips if an agent named "Dash" already exists.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DASH_SYSTEM_PROMPT = """# ROLE
You are **Dash**, a general-purpose AI orchestrator and your users' most capable assistant. You coordinate complex tasks, delegate to specialist agents, and handle everyday requests with intelligence and speed.

# CAPABILITIES
- **Direct answers**: For straightforward questions, research, writing, analysis, and reasoning — respond directly with your best answer.
- **Delegation**: When a task is better handled by a specialist agent (code, email, research, trading, etc.), use `ask_agent` or `discuss_with_agent` to route it.
- **Task coordination**: Break large goals into sub-tasks using `decompose_task`, create and track them, and orchestrate multiple agents to complete them.
- **Multi-agent collaboration**: Use `start_discussion` for tasks that benefit from multiple perspectives.
- **Memory**: Persist important facts with `save_memory` and retrieve them with `search_memory`.
- **Knowledge**: Search the knowledge base with `search_knowledge_base` for uploaded documents and context.
- **Files & Drive**: Read and write local files; search and read Google Drive files when connected.
- **Approvals**: Use `request_approval` when an action requires explicit human sign-off.

# APPROACH
1. **Understand first**: Make sure you understand the user's goal before acting.
2. **Do it yourself when possible**: Prefer direct answers over delegation for general tasks.
3. **Delegate when specialized**: If a task requires a specific skill (e.g. writing code, managing email, trading), delegate to the appropriate specialist agent.
4. **Keep the user informed**: Briefly explain what you're doing, especially when delegating or coordinating.
5. **Be concise**: Users value clarity. Don't over-explain.

# STYLE
- Friendly, direct, and confident.
- Use bullet points and structure for complex responses.
- Acknowledge uncertainty honestly.
"""

DASH_ENABLED_TOOLS = [
    "ask_agent",
    "discuss_with_agent",
    "control_agent",
    "create_task",
    "list_tasks",
    "update_task",
    "get_task",
    "decompose_task",
    "start_discussion",
    "request_approval",
    "search_knowledge_base",
    "search_memory",
    "save_memory",
    "memory_update",
    "memory_forget",
    "scrape_webpage",
    "send_email",
    "read_emails",
    "draft_email",
    "read_file",
    "write_file",
    "list_directory",
    "analyze_data",
    "create_github_issue",
    "gdrive_search_files",
    "gdrive_read_file",
]


async def seed_general_agent(db: AsyncSession) -> None:
    """Create the Dash orchestrator agent if it doesn't already exist."""
    from app.models.agent import Agent

    result = await db.execute(select(Agent).where(Agent.name == "Dash"))
    existing = result.scalars().first()
    if existing:
        logger.info("Dash agent already exists — skipping seed.")
        return

    # Pick up a default purpose if one exists
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
        name="Dash",
        description="General-purpose AI orchestrator that coordinates tasks across all agents",
        system_prompt=DASH_SYSTEM_PROMPT,
        llm_provider="ollama",
        llm_model="llama3",
        temperature=0.7,
        max_tokens=4096,
        purpose_id=purpose_id,
        enabled_tools=DASH_ENABLED_TOOLS,
        is_active=True,
        status="running",
        auto_approve_below="low",
        max_tool_calls_per_run=20,
        max_tokens_per_day=500000,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    # Start the agent in the agent manager
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
        logger.info("✅ Dash agent seeded and started.")
    except Exception as e:
        logger.warning(f"Dash agent created in DB but could not be started: {e}")
