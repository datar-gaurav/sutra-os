"""CodeExecutor contract: who actually does Forge's coding work.

Forge owns the request (what to build, where, its status and log). An executor
owns doing the work. Every Forge entry point (API routes, the nightly queue,
agent tools, Telegram) goes through the selected executor:

    builtin   today's in-process pipeline: clone → plan → (review) → code → test → PR
    shakha    optional plugin: hands the request to Shakha through the fleet
              worker on the Mac; Shakha plans, reviews and opens the draft PR
    disabled  refuses to run code

Executors report progress by updating the ForgeRequest row (status, coding_log,
pr_url, error_log) and broadcasting ``forge_update`` events.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CodeExecutorUnavailable(RuntimeError):
    """The selected executor cannot take work (disabled or not configured)."""


class CodeExecutor(ABC):
    #: Short identifier, matches the CODE_EXECUTOR setting.
    name: str = ""
    #: True when Sutra shows the plan for approval before coding starts.
    #: False when the executor plans and asks for approval itself.
    reviews_plan: bool = False

    def availability(self) -> tuple[bool, str]:
        """(ok, reason). Cheap and side-effect free; reason explains a False."""
        return True, ""

    def require_available(self) -> None:
        ok, reason = self.availability()
        if not ok:
            raise CodeExecutorUnavailable(reason)

    @abstractmethod
    async def start(self, forge_id: str, *, feedback: str = "", wait: bool = False) -> None:
        """Begin work on a request (from queued, failed, or after plan feedback).

        ``feedback`` carries the user's plan feedback when re-planning.
        ``wait`` blocks until this executor's first phase finishes (the nightly
        queue uses it to stay serial); otherwise the work runs in the background.
        """

    async def execute(self, forge_id: str) -> None:
        """Continue after the user approved Sutra's plan. Only if ``reviews_plan``."""
        raise CodeExecutorUnavailable(f"The {self.name} executor has no Sutra-side plan approval")

    @abstractmethod
    async def cancel(self, forge_id: str) -> None:
        """Stop work and release resources. The caller has already marked it cancelled."""


# ─── Shared helpers for executors and Forge entry points ─────────────────────


def append_log(req, event: str, message: str) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "message": message,
    }
    req.coding_log = list(req.coding_log or []) + [entry]


def broadcast_forge(forge_id: str, status: str) -> None:
    """Fire-and-forget ``forge_update`` to subscribed WebSocket clients."""

    async def _do():
        try:
            from app.api.websocket import ws_manager

            await ws_manager.broadcast(
                {"type": "forge_update", "forge_request_id": forge_id, "status": status}
            )
        except Exception:
            pass

    try:
        asyncio.get_running_loop().create_task(_do())
    except RuntimeError:
        pass  # no running loop (sync context); nothing to notify
