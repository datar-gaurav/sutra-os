"""Runtime helpers for reading env vars that may have been set via the UI.

The pydantic `settings` object is frozen at startup. When a user saves config
through the Settings → Environment Variables page:
  - Non-secrets are written to os.environ (picked up by get_config)
  - Secrets are stored encrypted in the env_vars DB table (picked up by get_secret)

Always call these at the point of use, not at module import time.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_config(env_key: str, fallback: str = "") -> str:
    """Return a non-secret config value, checking os.environ before the fallback."""
    return os.environ.get(env_key, "") or fallback


async def get_secret(env_key: str, fallback: str = "") -> str:
    """Return a secret value, checking the DB vault before the settings fallback."""
    try:
        from app.db.session import async_session_factory
        from app.models.env_var import EnvVar
        from app.core.vault import decrypt_secret
        async with async_session_factory() as db:
            row = await db.get(EnvVar, env_key)
            if row and row.value:
                return decrypt_secret(row.value)
    except Exception as exc:
        logger.debug("env_utils.get_secret(%s) DB lookup failed: %s", env_key, exc)
    return fallback
