"""Pick the CodeExecutor that runs Forge's coding work (CODE_EXECUTOR setting)."""

from __future__ import annotations

from app.config import settings
from app.core.code_executor.base import (
    CodeExecutor,
    CodeExecutorUnavailable,
    append_log,
    broadcast_forge,
)

EXECUTORS = ("builtin", "shakha", "disabled")


class DisabledExecutor(CodeExecutor):
    name = "disabled"
    reviews_plan = False

    def availability(self) -> tuple[bool, str]:
        return False, "Code execution is disabled (CODE_EXECUTOR=disabled)."

    async def start(self, forge_id: str, *, feedback: str = "", wait: bool = False) -> None:
        self.require_available()

    async def cancel(self, forge_id: str) -> None:
        return None


def get_executor(name: str | None = None) -> CodeExecutor:
    """Return the configured executor. An unknown name fails closed (disabled)."""
    choice = (name if name is not None else settings.code_executor or "builtin").strip().lower()
    if choice == "builtin":
        from app.core.code_executor.builtin import BuiltinExecutor

        return BuiltinExecutor()
    if choice == "shakha":
        from app.core.code_executor.shakha import ShakhaExecutor

        return ShakhaExecutor()
    return DisabledExecutor()


async def cancel_everywhere(forge_id: str) -> None:
    """Stop a request's work under every executor that may hold some.

    The setting can change while a request is in flight, so cancelling only
    through the current executor could leave a Shakha job or a local
    workspace behind. Both cancels are idempotent and need no configuration.
    """
    from app.core.code_executor.builtin import BuiltinExecutor
    from app.core.code_executor.shakha import ShakhaExecutor

    for executor in (BuiltinExecutor(), ShakhaExecutor()):
        try:
            await executor.cancel(forge_id)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "cancel via %s failed for %s", executor.name, forge_id, exc_info=True
            )


__all__ = [
    "cancel_everywhere",
    "EXECUTORS",
    "CodeExecutor",
    "CodeExecutorUnavailable",
    "DisabledExecutor",
    "append_log",
    "broadcast_forge",
    "get_executor",
]
