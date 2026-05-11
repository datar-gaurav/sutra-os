"""Sync the filesystem skill registry to the DB.

What the DB stores per skill (thin):
  - id (stable surrogate, used by AgentSkill / RoleSkill joins)
  - slug (unique; source of truth is the directory name on disk)
  - name, description (cached for list/search queries)
  - trigger_embedding, trigger_hash, trigger_embed_model (for routing)
  - is_active (False when the folder is removed but attachments still exist)

Everything else (body, tools, config_schema, icon, color, version, category)
is read from disk via skill_registry.get(slug) at runtime.
"""

from __future__ import annotations

import json
import logging

import xxhash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import embedding_service
from app.models.skill import Skill
from app.skills.registry import skill_registry

logger = logging.getLogger(__name__)


def _embed_model_id() -> str:
    """Stable identifier for the currently-active embedding model.

    When this changes (e.g. OpenAI swapped for Ollama), all stored embeddings
    are invalidated and recomputed.
    """
    if not embedding_service._initialized:
        embedding_service._init_embedder()
    embedder = embedding_service._embedder
    if embedder is None:
        return "none"
    return f"{type(embedder).__name__}"


def _trigger_hash(description: str) -> str:
    return xxhash.xxh64(description.encode("utf-8")).hexdigest()


async def sync_to_db(db: AsyncSession) -> dict:
    """Upsert one Skill row per registry slug. Mark missing slugs inactive.

    Recomputes trigger_embedding only when the description hash or the active
    embedding model has changed. Returns a summary dict.
    """
    created: list[str] = []
    updated: list[str] = []
    deactivated: list[str] = []
    re_embedded: list[str] = []

    active_model = _embed_model_id()
    registry_slugs = {m.slug for m in skill_registry.all()}

    # Upsert every manifest
    for manifest in skill_registry.all():
        slug = manifest.slug
        result = await db.execute(select(Skill).where(Skill.slug == slug))
        row = result.scalars().first()

        new_hash = _trigger_hash(manifest.description)
        needs_embed = False

        if row is None:
            row = Skill(
                slug=slug,
                name=manifest.name,
                description=manifest.description,
                is_active=True,
            )
            db.add(row)
            created.append(slug)
            needs_embed = bool(manifest.description)
        else:
            changed = False
            if row.name != manifest.name:
                row.name = manifest.name
                changed = True
            if row.description != manifest.description:
                row.description = manifest.description
                changed = True
            if not row.is_active:
                row.is_active = True
                changed = True
            if changed:
                updated.append(slug)
            if (
                row.trigger_hash != new_hash
                or row.trigger_embed_model != active_model
                or row.trigger_embedding is None
            ):
                needs_embed = bool(manifest.description)

        if needs_embed:
            emb = await embedding_service.aembed(manifest.description)
            if emb is not None:
                row.trigger_embedding = json.dumps(emb)
                row.trigger_hash = new_hash
                row.trigger_embed_model = active_model
                re_embedded.append(slug)

    # Soft-delete rows whose folder is gone
    all_rows = await db.execute(select(Skill).where(Skill.is_active == True))  # noqa: E712
    for row in all_rows.scalars().all():
        if row.slug not in registry_slugs:
            row.is_active = False
            deactivated.append(row.slug)

    await db.commit()
    summary = {
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "re_embedded": re_embedded,
        "embed_model": active_model,
    }
    logger.info(
        f"Skill sync: +{len(created)} created, ~{len(updated)} updated, "
        f"-{len(deactivated)} deactivated, {len(re_embedded)} re-embedded"
    )
    return summary
