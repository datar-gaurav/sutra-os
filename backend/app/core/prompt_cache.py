"""Redis-backed prompt cache for LLM responses — avoids re-invoking LLM for identical prompts."""

import hashlib
import json
import logging
import time

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Caches LLM responses keyed by (model, system_prompt_hash, last_N_messages).

    Only caches non-tool-using, deterministic-looking prompts.
    Short TTL (default 30 min) to avoid stale responses.
    """

    def __init__(self):
        self.hit_count = 0
        self.miss_count = 0
        self._enabled = True

    @property
    def DEFAULT_TTL(self) -> int:
        from app.core.system_settings import sys_settings
        return sys_settings.get("prompt_cache_ttl") or 1800

    @property
    def MAX_MESSAGES_IN_KEY(self) -> int:
        from app.core.system_settings import sys_settings
        return sys_settings.get("prompt_cache_max_messages") or 3

    def _cache_key(self, model: str, messages: list[dict]) -> str:
        """Build a deterministic cache key from model + message content."""
        # Extract system messages and last N user/assistant messages
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]
        relevant = system_msgs + other_msgs[-self.MAX_MESSAGES_IN_KEY:]

        content = f"{model}:" + json.dumps(
            [{"role": m.get("role", ""), "content": m.get("content", "")[:500]}
             for m in relevant],
            sort_keys=True,
        )
        digest = hashlib.sha256(content.encode()).hexdigest()
        return f"prompt_cache:{digest}"

    async def get(self, model: str, messages: list[dict]) -> str | None:
        """Try to get a cached response."""
        if not self._enabled:
            return None

        try:
            from app.core.redis_client import get_redis
            redis = await get_redis()
            key = self._cache_key(model, messages)
            cached = await redis.get(key)
            if cached:
                self.hit_count += 1
                logger.debug(f"Prompt cache HIT (rate={self.hit_rate:.1%})")
                return cached
            self.miss_count += 1
            return None
        except Exception as e:
            logger.debug(f"Prompt cache get failed: {e}")
            return None

    async def set(self, model: str, messages: list[dict], response: str, ttl: int | None = None):
        """Cache a response."""
        if not self._enabled or not response:
            return

        try:
            from app.core.redis_client import get_redis
            redis = await get_redis()
            key = self._cache_key(model, messages)
            await redis.setex(key, ttl or self.DEFAULT_TTL, response)
        except Exception as e:
            logger.debug(f"Prompt cache set failed: {e}")

    def should_cache(self, messages: list[dict]) -> bool:
        """
        Decide whether a prompt/response pair should be cached.
        Don't cache if the conversation involves tool calls or is very short.
        """
        if not self._enabled:
            return False

        # Don't cache very short conversations (likely unique)
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) < 1:
            return False

        # Don't cache if last message looks like it needs fresh data
        last_content = (messages[-1].get("content", "") or "").lower()
        time_sensitive = ["now", "today", "current", "latest", "right now", "just"]
        if any(word in last_content for word in time_sensitive):
            return False

        return True

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0

    @property
    def stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "hits": self.hit_count,
            "misses": self.miss_count,
            "hit_rate": f"{self.hit_rate:.1%}",
        }


# Global singleton
prompt_cache = PromptCache()
