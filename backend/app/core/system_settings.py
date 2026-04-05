"""Runtime system settings service — DB overrides with in-memory cache.

Usage:
    from app.core.system_settings import sys_settings
    value = sys_settings.get("watchdog_check_interval")  # returns int
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Schema: key → (type, group, label, description)
# This is the canonical list of all settings configurable from the UI.
SETTINGS_SCHEMA: dict[str, dict] = {
    # ── Resilience ──────────────────────────────────────────────────────────
    "llm_retry_max_retries": {
        "type": "int", "group": "Resilience", "label": "LLM Retry Max Attempts",
        "description": "Maximum number of retries for failed LLM calls",
        "min": 0, "max": 10,
    },
    "llm_retry_base_delay": {
        "type": "float", "group": "Resilience", "label": "LLM Retry Base Delay (s)",
        "description": "Initial delay between retries in seconds",
        "min": 0.1, "max": 30.0,
    },
    "llm_retry_max_delay": {
        "type": "float", "group": "Resilience", "label": "LLM Retry Max Delay (s)",
        "description": "Maximum delay between retries in seconds",
        "min": 1.0, "max": 120.0,
    },
    "circuit_breaker_failure_threshold": {
        "type": "int", "group": "Resilience", "label": "Circuit Breaker Failure Threshold",
        "description": "Number of failures before circuit opens",
        "min": 1, "max": 50,
    },
    "circuit_breaker_window_seconds": {
        "type": "int", "group": "Resilience", "label": "Circuit Breaker Window (s)",
        "description": "Time window for counting failures",
        "min": 10, "max": 600,
    },
    "circuit_breaker_cooldown_seconds": {
        "type": "int", "group": "Resilience", "label": "Circuit Breaker Cooldown (s)",
        "description": "How long to wait before retrying after circuit opens",
        "min": 5, "max": 300,
    },

    # ── Watchdog ────────────────────────────────────────────────────────────
    "watchdog_check_interval": {
        "type": "int", "group": "Watchdog", "label": "Health Check Interval (s)",
        "description": "Seconds between agent health checks",
        "min": 10, "max": 600,
    },
    "watchdog_timeout_multiplier": {
        "type": "int", "group": "Watchdog", "label": "Timeout Multiplier",
        "description": "Agent is unresponsive after N × check_interval",
        "min": 2, "max": 10,
    },
    "watchdog_max_restarts": {
        "type": "int", "group": "Watchdog", "label": "Max Auto-Restarts",
        "description": "Stop restarting after this many consecutive failures",
        "min": 0, "max": 10,
    },

    # ── Cache ───────────────────────────────────────────────────────────────
    "prompt_cache_ttl": {
        "type": "int", "group": "Cache", "label": "Prompt Cache TTL (s)",
        "description": "How long to cache identical LLM responses",
        "min": 60, "max": 86400,
    },
    "prompt_cache_max_messages": {
        "type": "int", "group": "Cache", "label": "Cache Key Message Count",
        "description": "Number of recent messages used in cache key",
        "min": 1, "max": 10,
    },

    # ── Conversation ────────────────────────────────────────────────────────
    "conversation_window_size": {
        "type": "int", "group": "Conversation", "label": "Chat Window Size",
        "description": "Number of recent messages sent to LLM (older ones get summarized)",
        "min": 5, "max": 100,
    },
    "summary_llm_provider": {
        "type": "str", "group": "Conversation", "label": "Summary LLM Provider",
        "description": "LLM provider for conversation summarization",
    },
    "summary_llm_model": {
        "type": "str", "group": "Conversation", "label": "Summary LLM Model",
        "description": "Model used for conversation summarization",
    },
    "summary_cache_ttl": {
        "type": "int", "group": "Conversation", "label": "Summary Cache TTL (s)",
        "description": "How long to cache conversation summaries",
        "min": 300, "max": 86400,
    },

    # ── Memory ──────────────────────────────────────────────────────────────
    "memory_decay_half_life_days": {
        "type": "int", "group": "Memory", "label": "Decay Half-Life (days)",
        "description": "Memory importance halves every N days without access",
        "min": 1, "max": 90,
    },
    "memory_consolidation_age_days": {
        "type": "int", "group": "Memory", "label": "Consolidation Age (days)",
        "description": "Recall memories older than this are consolidation candidates",
        "min": 1, "max": 365,
    },
    "memory_consolidation_decay_threshold": {
        "type": "float", "group": "Memory", "label": "Consolidation Decay Threshold",
        "description": "Memories below this decay score get consolidated",
        "min": 0.01, "max": 1.0,
    },
    "memory_archival_delete_days": {
        "type": "int", "group": "Memory", "label": "Archival Delete After (days)",
        "description": "Archival memories are deleted after this many days if decay is very low",
        "min": 30, "max": 730,
    },
    "memory_core_max_tokens": {
        "type": "int", "group": "Memory", "label": "Core Memory Max Tokens",
        "description": "Approximate max tokens for core memories per agent",
        "min": 500, "max": 10000,
    },
    "memory_maintenance_cron": {
        "type": "str", "group": "Memory", "label": "Maintenance Schedule (cron)",
        "description": "Cron expression for daily memory decay + consolidation job",
    },

    # ── Embeddings ──────────────────────────────────────────────────────────
    "embedding_batch_size": {
        "type": "int", "group": "Embeddings", "label": "Batch Size",
        "description": "Number of embeddings to process in one API call",
        "min": 1, "max": 100,
    },
    "embedding_flush_interval": {
        "type": "float", "group": "Embeddings", "label": "Flush Interval (s)",
        "description": "Max wait time before flushing a partial embedding batch",
        "min": 0.05, "max": 5.0,
    },

    # ── Alerting ──────────────────────────────────────────────────────────
    "alert_evaluation_interval_minutes": {
        "type": "int", "group": "Alerting", "label": "Alert Evaluation Interval (min)",
        "description": "How often the scheduled alert evaluator runs (minutes)",
        "min": 5, "max": 120,
    },
    "alert_default_cooldown_minutes": {
        "type": "int", "group": "Alerting", "label": "Default Alert Cooldown (min)",
        "description": "Default time before a resolved alert can re-fire",
        "min": 5, "max": 1440,
    },
    "alert_auto_resolve_enabled": {
        "type": "str", "group": "Alerting", "label": "Auto-Resolve Alerts",
        "description": "Automatically resolve alerts when condition returns to normal (true/false)",
    },

    # ── Evolve ───────────────────────────────────────────────────────────────
    "evolve_competitor_repos": {
        "type": "str", "group": "Evolve", "label": "Competitor Repos",
        "description": "Comma-separated GitHub repos to monitor (e.g. 'owner/repo,owner2/repo2')",
    },

    # ── Rate Limits ─────────────────────────────────────────────────────────
    "rate_limit_chat": {
        "type": "str", "group": "Rate Limits", "label": "Chat Rate Limit",
        "description": "Rate limit for chat endpoints (e.g. '200/hour')",
    },
    "rate_limit_auth_login": {
        "type": "str", "group": "Rate Limits", "label": "Login Rate Limit",
        "description": "Rate limit for login endpoint",
    },
    "rate_limit_auth_register": {
        "type": "str", "group": "Rate Limits", "label": "Register Rate Limit",
        "description": "Rate limit for registration endpoint",
    },
    "rate_limit_auth_refresh": {
        "type": "str", "group": "Rate Limits", "label": "Token Refresh Rate Limit",
        "description": "Rate limit for token refresh endpoint",
    },
}


class SystemSettings:
    """
    Runtime system settings with DB-backed overrides.

    Lookup order:  DB overrides (in-memory cache)  →  config.py defaults  →  schema default
    """

    def __init__(self):
        self._overrides: dict[str, Any] = {}
        self._loaded = False

    def get(self, key: str) -> Any:
        """Get a setting value. Fast — reads from in-memory cache."""
        # 1. Check DB overrides (cached in memory)
        if key in self._overrides:
            return self._cast(key, self._overrides[key])

        # 2. Fall back to config.py (env vars)
        from app.config import settings
        val = getattr(settings, key, None)
        if val is not None:
            return val

        # 3. Fall back to schema default (shouldn't happen)
        schema = SETTINGS_SCHEMA.get(key)
        if schema and "default" in schema:
            return schema["default"]

        return None

    def get_all(self) -> dict[str, Any]:
        """Get all configurable settings with their current values."""
        result = {}
        for key in SETTINGS_SCHEMA:
            result[key] = self.get(key)
        return result

    def get_schema(self) -> dict:
        """Get schema with current values for the UI."""
        all_values = self.get_all()
        result = {}
        for key, schema in SETTINGS_SCHEMA.items():
            result[key] = {
                **schema,
                "value": all_values[key],
                "is_overridden": key in self._overrides,
            }
        return result

    async def load(self, db: AsyncSession):
        """Load overrides from DB into memory cache."""
        try:
            from app.models.system_config import SystemConfig
            result = await db.execute(
                select(SystemConfig).where(SystemConfig.id == "default")
            )
            config = result.scalars().first()
            if config and config.overrides:
                self._overrides = dict(config.overrides)
            self._loaded = True
            logger.info(f"System settings loaded ({len(self._overrides)} overrides)")
        except Exception as e:
            logger.warning(f"Failed to load system settings: {e}")

    async def update(self, db: AsyncSession, updates: dict[str, Any]) -> dict[str, Any]:
        """Update overrides in DB and memory cache. Returns the new values."""
        from app.models.system_config import SystemConfig

        # Validate keys
        for key in updates:
            if key not in SETTINGS_SCHEMA:
                raise ValueError(f"Unknown setting: {key}")

        # Load existing config row
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.id == "default")
        )
        config = result.scalars().first()

        if not config:
            config = SystemConfig(id="default", overrides={})
            db.add(config)

        # Merge updates
        new_overrides = dict(config.overrides or {})
        for key, value in updates.items():
            if value is None:
                # None means "reset to default"
                new_overrides.pop(key, None)
            else:
                new_overrides[key] = value

        config.overrides = new_overrides
        await db.flush()

        # Update in-memory cache
        self._overrides = dict(new_overrides)

        return self.get_all()

    def _cast(self, key: str, value: Any) -> Any:
        """Cast a value to the correct type based on schema."""
        schema = SETTINGS_SCHEMA.get(key)
        if not schema:
            return value
        try:
            t = schema.get("type", "str")
            if t == "int":
                return int(value)
            elif t == "float":
                return float(value)
            return str(value)
        except (ValueError, TypeError):
            return value


# Global singleton
sys_settings = SystemSettings()
