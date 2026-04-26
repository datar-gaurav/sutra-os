"""Idempotent seed for the runtime_scripts (Dispatcher bridge) integration row.

Called at startup (from main.py lifespan) after the Dispatcher agent is seeded.
Reads DISPATCHER_BRIDGE_TOKEN and DISPATCHER_BRIDGE_PORT from the environment
(which install.sh writes to backend/.env) and upserts the Integration row.

Three cases handled:
  1. No row → create with bridge_url + bridge_token (encrypted), is_active=True.
  2. Row exists but missing credentials_enc (current pre-bridge state) → update.
  3. Env vars unset → log warning, skip; nothing breaks.
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def seed_runtime_scripts_integration(db: AsyncSession) -> None:
    from app.core.vault import encrypt_secret
    from app.models.integration import Integration

    token = (os.environ.get("DISPATCHER_BRIDGE_TOKEN") or "").strip()
    port  = (os.environ.get("DISPATCHER_BRIDGE_PORT") or "7475").strip()

    if not token:
        logger.warning(
            "DISPATCHER_BRIDGE_TOKEN not set — skipping runtime_scripts integration seed. "
            "Re-run ./install.sh to generate the token."
        )
        return

    bridge_url = f"http://host.docker.internal:{port}"
    credentials_enc = encrypt_secret(json.dumps({"bridge_token": token}))

    result = await db.execute(
        select(Integration).where(Integration.type == "runtime_scripts")
    )
    existing = result.scalars().first()

    if existing:
        # Update in place — preserve id, agent_id, and is_active flag
        existing.credentials_enc = credentials_enc
        existing.extra_config = {"bridge_url": bridge_url}
        existing.name = "Dispatcher Bridge"
        await db.commit()
        logger.info("✅ runtime_scripts integration updated with bridge config.")
    else:
        db.add(Integration(
            type="runtime_scripts",
            name="Dispatcher Bridge",
            agent_id=None,
            credentials_enc=credentials_enc,
            extra_config={"bridge_url": bridge_url},
            is_active=True,
        ))
        await db.commit()
        logger.info("✅ runtime_scripts integration created with bridge config.")
