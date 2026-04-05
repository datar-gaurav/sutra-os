"""Browser session manager — persistent Playwright sessions for interactive automation."""

import asyncio
import contextvars
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Context variable for conversation scoping ──────────────────────────────
# Set in chat.py before agent invocation; read by browser tools at call time.
current_conversation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_conversation_id", default=""
)

SESSION_TIMEOUT_SECONDS = 300  # 5 minutes of inactivity
MAX_CONCURRENT_SESSIONS = 10
CLEANUP_INTERVAL_SECONDS = 60


@dataclass
class SessionEntry:
    """A single browser session scoped to an agent + conversation."""

    context: object  # playwright BrowserContext
    page: object  # playwright Page
    agent_id: str
    conversation_id: str
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    # Recording state
    recording: bool = False
    recording_name: str = ""
    recording_description: str = ""
    action_log: list = field(default_factory=list)

    def touch(self):
        self.last_used = time.time()

    def start_recording(self, name: str, description: str = ""):
        self.recording = True
        self.recording_name = name
        self.recording_description = description
        self.action_log = []

    def stop_recording(self) -> list:
        self.recording = False
        log = self.action_log.copy()
        self.action_log = []
        name = self.recording_name
        desc = self.recording_description
        self.recording_name = ""
        self.recording_description = ""
        return {"name": name, "description": desc, "actions": log}

    def log_action(self, tool: str, args: dict, result_summary: str):
        if self.recording:
            self.action_log.append({
                "tool": tool,
                "args": args,
                "result_summary": result_summary,
                "timestamp": time.time(),
            })


class BrowserSessionManager:
    """Singleton managing persistent Playwright browser sessions.

    Sessions are keyed by ``{agent_id}:{conversation_id}``.  A single shared
    Chromium process hosts all sessions via isolated BrowserContexts.
    """

    def __init__(self):
        self._sessions: dict[str, SessionEntry] = {}
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    def _key(self, agent_id: str, conversation_id: str) -> str:
        return f"{agent_id}:{conversation_id or 'default'}"

    async def _ensure_browser(self):
        """Lazy-start Playwright and the shared Chromium browser."""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Playwright browser launched.")

        # Start the periodic cleanup task if not running
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def get_or_create_session(
        self, agent_id: str, conversation_id: str
    ) -> SessionEntry:
        """Return an existing session or create a new one."""
        key = self._key(agent_id, conversation_id)

        async with self._lock:
            if key in self._sessions:
                entry = self._sessions[key]
                entry.touch()
                return entry

            await self._ensure_browser()

            # Evict oldest idle session if at capacity
            if len(self._sessions) >= MAX_CONCURRENT_SESSIONS:
                oldest_key = min(
                    self._sessions, key=lambda k: self._sessions[k].last_used
                )
                logger.warning(
                    "Max sessions reached (%d). Evicting %s.",
                    MAX_CONCURRENT_SESSIONS,
                    oldest_key,
                )
                await self._close_session_unsafe(oldest_key)

            context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            entry = SessionEntry(
                context=context,
                page=page,
                agent_id=agent_id,
                conversation_id=conversation_id,
            )
            self._sessions[key] = entry
            logger.info("Browser session created: %s", key)
            return entry

    async def close_session(self, agent_id: str, conversation_id: str):
        """Explicitly close a single session."""
        key = self._key(agent_id, conversation_id)
        async with self._lock:
            await self._close_session_unsafe(key)

    async def close_all_for_agent(self, agent_id: str):
        """Close every session belonging to an agent (called on agent stop)."""
        async with self._lock:
            keys_to_close = [
                k for k, v in self._sessions.items() if v.agent_id == agent_id
            ]
            for key in keys_to_close:
                await self._close_session_unsafe(key)
            if keys_to_close:
                logger.info(
                    "Closed %d browser session(s) for agent %s.",
                    len(keys_to_close),
                    agent_id,
                )

    async def shutdown(self):
        """Close all sessions and the browser process (called on app shutdown)."""
        async with self._lock:
            for key in list(self._sessions):
                await self._close_session_unsafe(key)

            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                self._cleanup_task = None

            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Browser session manager shut down.")

    # ── Internal helpers ────────────────────────────────────────────────────

    async def _close_session_unsafe(self, key: str):
        """Close a session without acquiring the lock (caller must hold it)."""
        entry = self._sessions.pop(key, None)
        if entry is None:
            return
        try:
            await entry.page.close()
            await entry.context.close()
        except Exception as exc:
            logger.warning("Error closing browser session %s: %s", key, exc)

    async def _cleanup_loop(self):
        """Periodically close idle sessions."""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_idle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Browser cleanup error: %s", exc)

    async def _cleanup_idle(self):
        """Close sessions that have been idle too long."""
        now = time.time()
        async with self._lock:
            idle_keys = [
                k
                for k, v in self._sessions.items()
                if (now - v.last_used) > SESSION_TIMEOUT_SECONDS
            ]
            for key in idle_keys:
                logger.info("Closing idle browser session: %s", key)
                await self._close_session_unsafe(key)

        # If no sessions remain, shut down the browser process to free resources
        async with self._lock:
            if not self._sessions and self._browser:
                await self._browser.close()
                self._browser = None
                if self._playwright:
                    await self._playwright.stop()
                    self._playwright = None
                logger.info("No active sessions — browser process closed.")


# Module-level singleton
browser_session_manager = BrowserSessionManager()
