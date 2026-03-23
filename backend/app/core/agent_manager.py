"""Agent lifecycle manager — start, stop, restart agents."""

import asyncio
import logging
from typing import Any

from app.agents.factory import build_agent
from app.core.llm_registry import llm_registry
from app.core.watchdog import watchdog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages the lifecycle of running agent instances."""

    def __init__(self):
        self._running_agents: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._locks:
            self._locks[agent_id] = asyncio.Lock()
        return self._locks[agent_id]

    async def start_agent(self, agent_config: dict) -> dict:
        """Build and register an agent as running.

        Args:
            agent_config: Dict with agent configuration from DB.

        Returns:
            Status dict.
        """
        agent_id = agent_config["id"]
        async with self._get_lock(agent_id):
            if agent_id in self._running_agents:
                return {"status": "already_running", "agent_id": agent_id}

            try:
                executor = build_agent(agent_config)
                self._running_agents[agent_id] = {
                    "executor": executor,
                    "config": agent_config,
                    "status": "running",
                }
                logger.info(f"Agent '{agent_config['name']}' started successfully.")
                watchdog.register(agent_id)

                # If Telegram is enabled, Chat ID is set, and online notification is enabled, send status update
                if (agent_config.get("telegram_enabled") and 
                    agent_config.get("telegram_chat_id") and 
                    agent_config.get("online_notification_enabled")):
                    from app.integrations.telegram_bot import send_telegram_message
                    asyncio.create_task(send_telegram_message(
                        chat_id=agent_config["telegram_chat_id"],
                        text=f"🟢 *Agent Online*: {agent_config['name']}\nModel: `{agent_config['llm_model']}`"
                    ))

                return {"status": "running", "agent_id": agent_id}
            except Exception as e:
                logger.error(f"Failed to start agent '{agent_config.get('name')}': {e}")
                return {"status": "error", "agent_id": agent_id, "error": str(e)}

    async def stop_agent(self, agent_id: str) -> dict:
        """Stop a running agent."""
        async with self._get_lock(agent_id):
            if agent_id not in self._running_agents:
                return {"status": "not_running", "agent_id": agent_id}

            del self._running_agents[agent_id]
            watchdog.unregister(agent_id)
            logger.info(f"Agent {agent_id} stopped.")
            return {"status": "stopped", "agent_id": agent_id}

    async def restart_agent(self, agent_config: dict) -> dict:
        """Restart an agent with (potentially updated) configuration."""
        agent_id = agent_config["id"]
        await self.stop_agent(agent_id)
        return await self.start_agent(agent_config)

    def get_executor(self, agent_id: str):
        """Get the AgentExecutor for a running agent."""
        entry = self._running_agents.get(agent_id)
        if entry:
            return entry["executor"]
        return None

    def get_info(self, agent_id: str) -> dict | None:
        """Get the config dict for a running agent (includes budget fields)."""
        entry = self._running_agents.get(agent_id)
        if entry:
            return entry.get("config")
        return None

    def is_running(self, agent_id: str) -> bool:
        return agent_id in self._running_agents

    def get_running_agents(self) -> list[str]:
        return list(self._running_agents.keys())

    def get_agent_status(self, agent_id: str) -> str:
        entry = self._running_agents.get(agent_id)
        if entry:
            return entry.get("status", "unknown")
        return "stopped"

    async def restore_running_agents(self, db: AsyncSession):
        """Query the database for agents that should be running and start them."""
        from app.models.agent import Agent
        
        result = await db.execute(select(Agent).where(Agent.status == "running"))
        active_agents = result.scalars().all()
        
        if not active_agents:
            logger.info("No active agents found to restore.")
            return

        from app.models.skill import AgentSkill
        from sqlalchemy.orm import selectinload

        logger.info(f"Restoring {len(active_agents)} active agents...")
        for agent in active_agents:
            # Load attached active skills
            skill_result = await db.execute(
                select(AgentSkill)
                .options(selectinload(AgentSkill.skill))
                .where(AgentSkill.agent_id == agent.id, AgentSkill.is_active == True)  # noqa: E712
                .order_by(AgentSkill.priority)
            )
            skill_rows = skill_result.scalars().all()
            skill_fragments = [row.skill.prompt_fragment for row in skill_rows]
            skill_tool_ids = []
            skill_config_overrides: dict = {}
            for row in skill_rows:
                skill_tool_ids.extend(row.skill.required_tool_ids or [])
                skill_config_overrides.update(row.config_overrides or {})

            config = {
                "id": agent.id,
                "name": agent.name,
                "system_prompt": agent.system_prompt,
                "purpose_id": agent.purpose_id,
                "llm_provider": agent.llm_provider,
                "llm_model": agent.llm_model,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "enabled_tools": agent.enabled_tools or [],
                "secondary_provider": agent.secondary_provider,
                "secondary_model": agent.secondary_model,
                "fallback_provider": agent.fallback_provider,
                "fallback_model": agent.fallback_model,
                "telegram_enabled": agent.telegram_enabled,
                "telegram_chat_id": agent.telegram_chat_id,
                "online_notification_enabled": agent.online_notification_enabled,
                "skill_fragments": skill_fragments,
                "skill_tool_ids": list(dict.fromkeys(skill_tool_ids)),
                "skill_config_overrides": skill_config_overrides,
                "auto_approve_below": agent.auto_approve_below,
                "max_tool_calls_per_run": agent.max_tool_calls_per_run or 0,
                "max_tokens_per_day": agent.max_tokens_per_day or 0,
            }
            try:
                await self.start_agent(config)
            except Exception as e:
                logger.error(f"Failed to restore agent {agent.name}: {e}")


# Global singleton
agent_manager = AgentManager()
