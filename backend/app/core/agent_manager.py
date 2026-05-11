"""Agent lifecycle manager — start, stop, restart agents.

What's cached per running agent:
    shell:  AgentShell  — LLM + base prompt + base tool IDs (built once)
    config: dict        — the original DB-shaped config (for budget/voice/etc.)

Skills are NOT cached here. The orchestrator fetches the agent's attached
skills (AgentSkill rows) per turn and passes them through the router →
build_executor_for_turn — so attaching/detaching a skill takes effect on the
next turn without restarting the agent.
"""

import asyncio
import logging
from typing import Any

from app.agents.factory import AgentShell, build_agent_shell
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
        """Build and register an agent as running."""
        agent_id = agent_config["id"]
        async with self._get_lock(agent_id):
            if agent_id in self._running_agents:
                return {"status": "already_running", "agent_id": agent_id}

            try:
                shell = build_agent_shell(agent_config)
                self._running_agents[agent_id] = {
                    "shell": shell,
                    "config": agent_config,
                    "status": "running",
                }
                logger.info(f"Agent '{agent_config['name']}' started successfully.")
                watchdog.register(agent_id)

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
        async with self._get_lock(agent_id):
            if agent_id not in self._running_agents:
                return {"status": "not_running", "agent_id": agent_id}

            del self._running_agents[agent_id]
            watchdog.unregister(agent_id)

            try:
                from app.core.browser_session_manager import browser_session_manager
                await browser_session_manager.close_all_for_agent(agent_id)
            except Exception as exc:
                logger.warning("Failed to close browser sessions for %s: %s", agent_id, exc)

            logger.info(f"Agent {agent_id} stopped.")
            return {"status": "stopped", "agent_id": agent_id}

    async def restart_agent(self, agent_config: dict) -> dict:
        agent_id = agent_config["id"]
        await self.stop_agent(agent_id)
        return await self.start_agent(agent_config)

    def get_shell(self, agent_id: str) -> AgentShell | None:
        entry = self._running_agents.get(agent_id)
        return entry.get("shell") if entry else None

    def get_info(self, agent_id: str) -> dict | None:
        """Get the config dict for a running agent (includes budget fields)."""
        entry = self._running_agents.get(agent_id)
        return entry.get("config") if entry else None

    def is_running(self, agent_id: str) -> bool:
        return agent_id in self._running_agents

    def get_running_agents(self) -> list[str]:
        return list(self._running_agents.keys())

    def get_agent_status(self, agent_id: str) -> str:
        entry = self._running_agents.get(agent_id)
        return entry.get("status", "unknown") if entry else "stopped"

    async def restore_running_agents(self, db: AsyncSession):
        """Query the database for agents that should be running and start them.

        Skills are NOT hydrated here — the orchestrator fetches them per turn.
        """
        from app.models.agent import Agent

        result = await db.execute(select(Agent).where(Agent.status == "running"))
        active_agents = result.scalars().all()

        if not active_agents:
            logger.info("No active agents found to restore.")
            return

        logger.info(f"Restoring {len(active_agents)} active agents...")
        for agent in active_agents:
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
                "auto_approve_below": agent.auto_approve_below,
                "max_tool_calls_per_run": agent.max_tool_calls_per_run or 0,
                "max_tokens_per_day": agent.max_tokens_per_day or 0,
                "skill_routing_enabled": getattr(agent, "skill_routing_enabled", None),
            }
            try:
                await self.start_agent(config)
            except Exception as e:
                logger.error(f"Failed to restore agent {agent.name}: {e}")


# Global singleton
agent_manager = AgentManager()
