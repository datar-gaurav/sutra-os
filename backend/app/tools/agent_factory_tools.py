"""Agent factory tools — allow agents to create, list templates, and archive other agents."""

import json
import logging
from datetime import datetime, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

FACTORY_TOOL_IDS = {"create_agent_from_template", "list_agent_templates", "archive_agent"}


def create_factory_tools(creator_agent_id: str):
    """Create agent factory tools bound to the requesting agent's ID."""

    @tool
    async def create_agent_from_template(
        template_name: str,
        agent_name: str,
        custom_instructions: str = "",
        llm_provider: str = "",
        llm_model: str = "",
    ) -> str:
        """Create a new agent from a named template. Provide the template name (e.g. 'Software Engineer'),
        a unique agent name, and optional custom instructions to append to the template's system prompt.
        Optionally override llm_provider and llm_model. Returns the new agent's ID and name."""
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from app.models.agent_template import AgentTemplate

        try:
            async with async_session_factory() as db:
                # Find template by name (case-insensitive)
                result = await db.execute(
                    select(AgentTemplate).where(
                        AgentTemplate.name.ilike(f"%{template_name}%")
                    )
                )
                tpl = result.scalars().first()
                if not tpl:
                    return json.dumps({"error": f"No template found matching '{template_name}'. Use list_agent_templates to see available templates."})

                # Check name uniqueness
                existing = await db.execute(select(Agent).where(Agent.name == agent_name))
                if existing.scalars().first():
                    return json.dumps({"error": f"An agent named '{agent_name}' already exists. Choose a different name."})

                # Build system prompt
                system_prompt = tpl.system_prompt
                if custom_instructions:
                    system_prompt = f"{system_prompt}\n\nAdditional Instructions:\n{custom_instructions}"

                agent = Agent(
                    name=agent_name,
                    description=tpl.description,
                    system_prompt=system_prompt,
                    temperature=tpl.temperature,
                    max_tokens=4096,
                    llm_provider=llm_provider or tpl.default_llm_provider,
                    llm_model=llm_model or tpl.default_llm_model,
                    enabled_tools=tpl.default_tools,
                    template_id=tpl.id,
                )
                db.add(agent)
                await db.flush()
                await db.refresh(agent)

                # Increment usage count
                tpl.usage_count = (tpl.usage_count or 0) + 1
                await db.commit()

                return json.dumps({
                    "success": True,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "template_used": tpl.name,
                    "message": f"Agent '{agent_name}' created successfully from template '{tpl.name}'. You can now start it via the UI or using the control_agent tool."
                })
        except Exception as e:
            logger.error(f"create_agent_from_template error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def list_agent_templates(category: str = "") -> str:
        """List available agent templates. Optionally filter by category.
        Available categories: leadership, management, engineering, marketing, finance,
        research, operations, security, data, general, custom.
        Returns a list of templates with their names, descriptions, and categories."""
        from sqlalchemy import select
        from app.db.session import async_session_factory
        from app.models.agent_template import AgentTemplate

        try:
            async with async_session_factory() as db:
                q = select(AgentTemplate).order_by(
                    AgentTemplate.is_builtin.desc(),
                    AgentTemplate.usage_count.desc()
                )
                if category:
                    q = q.where(AgentTemplate.category == category)
                result = await db.execute(q)
                templates = result.scalars().all()

                return json.dumps({
                    "templates": [
                        {
                            "name": t.name,
                            "description": t.description,
                            "category": t.category,
                            "default_tools": t.default_tools,
                            "default_llm": f"{t.default_llm_provider}/{t.default_llm_model}",
                            "is_builtin": t.is_builtin,
                            "usage_count": t.usage_count,
                            "tags": t.tags,
                        }
                        for t in templates
                    ],
                    "total": len(templates),
                })
        except Exception as e:
            logger.error(f"list_agent_templates error: {e}")
            return json.dumps({"error": str(e)})

    @tool
    async def archive_agent(agent_id: str, reason: str) -> str:
        """Archive (retire) an agent by its ID. The agent will be stopped, marked as archived,
        and hidden from normal listings. All history is preserved. Provide a reason for archival.
        Use this for agents that are no longer needed or underperforming."""
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from app.core.agent_manager import agent_manager

        try:
            async with async_session_factory() as db:
                agent = await db.get(Agent, agent_id)
                if not agent:
                    return json.dumps({"error": f"Agent '{agent_id}' not found."})

                if agent.id == creator_agent_id:
                    return json.dumps({"error": "An agent cannot archive itself."})

                # Stop if running
                if agent_manager.is_running(agent_id):
                    await agent_manager.stop_agent(agent_id)

                agent.is_archived = True
                agent.archived_at = datetime.now(timezone.utc)
                agent.archived_reason = reason
                agent.status = "stopped"
                agent.is_active = False
                await db.commit()

                return json.dumps({
                    "success": True,
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "message": f"Agent '{agent.name}' has been archived. Reason: {reason}",
                })
        except Exception as e:
            logger.error(f"archive_agent error: {e}")
            return json.dumps({"error": str(e)})

    return [create_agent_from_template, list_agent_templates, archive_agent]
