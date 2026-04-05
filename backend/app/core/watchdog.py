"""Agent watchdog — monitors running agents and auto-restarts unresponsive ones."""

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.agent_manager import AgentManager

logger = logging.getLogger(__name__)


class AgentWatchdog:
    """
    Background task that periodically checks agent health.
    If an agent hasn't sent a heartbeat within 3 × check_interval,
    it is considered unresponsive and restarted.
    """

    def __init__(self):
        self._heartbeats: dict[str, float] = {}  # agent_id → last heartbeat timestamp
        self._restart_counts: dict[str, int] = {}  # agent_id → consecutive restart count
        self._task: asyncio.Task | None = None

    @property
    def check_interval(self) -> int:
        from app.core.system_settings import sys_settings
        return sys_settings.get("watchdog_check_interval") or 60

    @property
    def timeout_multiplier(self) -> int:
        from app.core.system_settings import sys_settings
        return sys_settings.get("watchdog_timeout_multiplier") or 3

    @property
    def _max_restarts(self) -> int:
        from app.core.system_settings import sys_settings
        return sys_settings.get("watchdog_max_restarts") or 3

    def heartbeat(self, agent_id: str):
        """Record a heartbeat for an agent. Called after each successful invocation."""
        self._heartbeats[agent_id] = time.monotonic()
        # Reset restart count on successful heartbeat
        self._restart_counts.pop(agent_id, None)

    def register(self, agent_id: str):
        """Register a newly started agent with an initial heartbeat."""
        self._heartbeats[agent_id] = time.monotonic()
        self._restart_counts.pop(agent_id, None)

    def unregister(self, agent_id: str):
        """Remove an agent from monitoring (on intentional stop)."""
        self._heartbeats.pop(agent_id, None)
        self._restart_counts.pop(agent_id, None)

    async def start(self, agent_manager: "AgentManager"):
        """Start the watchdog background loop."""
        self._task = asyncio.create_task(self._run(agent_manager))
        logger.info(f"Watchdog started (interval={self.check_interval}s)")

    async def stop(self):
        """Stop the watchdog."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    async def _run(self, agent_manager: "AgentManager"):
        """Main watchdog loop."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_agents(agent_manager)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying

    async def _check_agents(self, agent_manager: "AgentManager"):
        """Check all running agents for responsiveness."""
        now = time.monotonic()
        timeout = self.check_interval * self.timeout_multiplier
        running = agent_manager.get_running_agents()

        for agent_id in running:
            last_beat = self._heartbeats.get(agent_id)
            if last_beat is None:
                # Agent started before watchdog — give it a grace period
                self._heartbeats[agent_id] = now
                continue

            elapsed = now - last_beat
            if elapsed <= timeout:
                continue

            # Agent is unresponsive
            restarts = self._restart_counts.get(agent_id, 0)
            if restarts >= self._max_restarts:
                logger.error(
                    f"Agent {agent_id} unresponsive after {restarts} restart attempts. "
                    f"Giving up — manual intervention required."
                )
                continue

            logger.warning(
                f"Agent {agent_id} unresponsive ({elapsed:.0f}s since last heartbeat). "
                f"Attempting restart ({restarts + 1}/{self._max_restarts})..."
            )

            config = agent_manager.get_info(agent_id)
            if not config:
                logger.error(f"Cannot restart agent {agent_id}: no config found")
                continue

            try:
                result = await agent_manager.restart_agent(config)
                self._restart_counts[agent_id] = restarts + 1
                if result.get("status") == "running":
                    self._heartbeats[agent_id] = time.monotonic()
                    logger.info(f"Agent {agent_id} restarted successfully by watchdog")

                    # Record audit log (fire-and-forget)
                    try:
                        from app.core.audit import record_audit
                        from app.db.session import async_session_factory
                        async with async_session_factory() as db:
                            await record_audit(
                                db=db, actor="system", action="agent.auto_restart",
                                resource_type="agent", resource_id=agent_id,
                                details={"reason": "watchdog_timeout", "elapsed_seconds": int(elapsed)},
                            )
                            await db.commit()
                    except Exception:
                        pass
                else:
                    logger.error(f"Watchdog restart failed for {agent_id}: {result}")
            except Exception as e:
                self._restart_counts[agent_id] = restarts + 1
                logger.error(f"Watchdog restart exception for {agent_id}: {e}")

    @property
    def stats(self) -> dict:
        return {
            "monitored_agents": len(self._heartbeats),
            "restart_counts": dict(self._restart_counts),
        }


# Global singleton
watchdog = AgentWatchdog()
