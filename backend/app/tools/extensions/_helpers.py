"""Shared helpers for extension authors.

Extensions import this to fetch their configured credentials + config
without writing boilerplate DB/vault code.
"""

from __future__ import annotations

import json


async def get_extension_creds(extension_id: str, agent_id: str) -> tuple[dict, dict]:
    """Fetch credentials and config for an extension integration.

    Checks agent-specific integration first, then falls back to system-wide.

    Returns:
        (credentials_dict, extra_config_dict)

    Raises:
        ValueError: If no active integration is configured for this extension.
    """
    from sqlalchemy import select, nullslast

    from app.core.vault import decrypt_secret
    from app.db.session import async_session_factory
    from app.models.integration import Integration

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == extension_id, Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide

    if not row or not row.credentials_enc:
        raise ValueError(
            f"No active '{extension_id}' integration found. "
            f"Please configure it in Settings > Integrations."
        )

    creds = json.loads(decrypt_secret(row.credentials_enc))
    config = row.extra_config or {}
    return creds, config
