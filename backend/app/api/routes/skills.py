"""Skills API.

Skill *content* (body, tools, config_schema, icon, etc.) is read from disk via
the SkillRegistry. The DB only tracks attachment joins, cached metadata, and
routing fields.

The /reseed endpoint syncs the in-memory registry to the DB (upserts rows,
recomputes trigger embeddings when descriptions change).
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    AgentSkillCreate,
    AgentSkillResponse,
    AgentSkillUpdate,
    RoleSkillCreate,
    RoleSkillResponse,
    SkillDetailResponse,
    SkillExportBundle,
    SkillResponse,
    SkillUpdate,
)
from app.db.session import get_db
from app.models.skill import AgentSkill, RoleSkill, Skill
from app.skills.registry import skill_registry
from app.skills.sync import sync_to_db

router = APIRouter(prefix="/skills", tags=["skills"])
agent_skills_router = APIRouter(prefix="/agents/{agent_id}/skills", tags=["skills"])
role_skills_router = APIRouter(prefix="/roles/{role_id}/skills", tags=["skills"])


def _manifest_payload(slug: str) -> dict:
    """Return the on-disk manifest fields for a given slug, or empty dict."""
    m = skill_registry.get(slug)
    if not m:
        return {}
    return {
        "body": m.body,
        "tools": list(m.tools),
        "config_schema": m.config_schema,
        "icon": m.icon,
        "color": m.color,
        "version": m.version,
        "category": m.category,
        "source": m.source,
        "files": sorted(m.files.keys()),
    }


# ─── Skill CRUD ───────────────────────────────────────────────────────────────

@router.get("/builtin")
async def list_builtin_manifests():
    """Return the filesystem-loaded skill manifests (read-only)."""
    return [
        {
            "slug": m.slug,
            "name": m.name,
            "description": m.description,
            "icon": m.icon,
            "color": m.color,
            "version": m.version,
            "category": m.category,
            "tools": m.tools,
            "config_schema": m.config_schema,
            "source": m.source,
        }
        for m in skill_registry.all()
    ]


@router.post("/reseed", status_code=200)
@router.get("/reseed", status_code=200)  # GET kept for legacy callers
async def reseed_skills(db: AsyncSession = Depends(get_db)):
    """Sync filesystem manifests to the DB. Recomputes trigger embeddings."""
    skill_registry.reload()
    summary = await sync_to_db(db)
    return summary


@router.get("/")
async def list_skills(
    category: str | None = None,
    source: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List DB skill rows enriched with filesystem manifest data."""
    result = await db.execute(select(Skill).order_by(Skill.name))
    rows = result.scalars().all()
    out: list[dict] = []
    for sk in rows:
        meta = _manifest_payload(sk.slug)
        if category and meta.get("category") != category:
            continue
        if source and meta.get("source") != source:
            continue
        if search:
            s = search.lower()
            if s not in sk.name.lower() and not (sk.description and s in sk.description.lower()):
                continue
        out.append({
            "id": sk.id,
            "slug": sk.slug,
            "name": sk.name,
            "description": sk.description,
            "is_active": sk.is_active,
            "routing_threshold": sk.routing_threshold,
            "trigger_embed_model": sk.trigger_embed_model,
            "created_at": sk.created_at,
            "updated_at": sk.updated_at,
            **meta,
        })
    return out


@router.get("/{skill_id}", response_model=SkillDetailResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    sk = await db.get(Skill, skill_id)
    if not sk:
        raise HTTPException(404, "Skill not found")
    meta = _manifest_payload(sk.slug)
    return SkillDetailResponse(
        id=sk.id,
        slug=sk.slug,
        name=sk.name,
        description=sk.description,
        is_active=sk.is_active,
        routing_threshold=sk.routing_threshold,
        trigger_embed_model=sk.trigger_embed_model,
        created_at=sk.created_at,
        updated_at=sk.updated_at,
        body=meta.get("body", ""),
        tools=meta.get("tools", []),
        config_schema=meta.get("config_schema"),
        icon=meta.get("icon"),
        color=meta.get("color"),
        version=meta.get("version", "1.0.0"),
        category=meta.get("category", "general"),
        source=meta.get("source", "builtin"),
        files=meta.get("files", []),
    )


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: str, data: SkillUpdate, db: AsyncSession = Depends(get_db)):
    """Update the DB-side metadata. Body/tools/etc. are edited on disk."""
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(skill, field, value)
    await db.commit()
    await db.refresh(skill)
    return skill


# ─── Export / Import ──────────────────────────────────────────────────────────

@router.post("/export")
async def export_skills(body: dict, db: AsyncSession = Depends(get_db)):
    skill_ids = body.get("skill_ids", [])
    if not skill_ids:
        raise HTTPException(400, "skill_ids is required")
    result = await db.execute(select(Skill).where(Skill.id.in_(skill_ids)))
    skills = result.scalars().all()
    bundle = SkillExportBundle(
        exported_at=datetime.now(timezone.utc).isoformat(),
        skills=[SkillResponse.model_validate(s) for s in skills],
    )
    return bundle


@router.post("/import")
async def import_skills(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Import is now a no-op stub.

    Filesystem-backed skills are imported by placing the directory on disk.
    Kept for API compat with the old JSON-bundle import.
    """
    content = await file.read()
    try:
        json.loads(content)
    except (json.JSONDecodeError, AttributeError):
        raise HTTPException(400, "Invalid skill bundle format")
    return {
        "created": [],
        "skipped": [],
        "note": "Filesystem-backed skills: place the directory under backend/skills/ "
                "or the custom_skills_dir and call /skills/reseed",
    }


# ─── Agent-Skill Associations ─────────────────────────────────────────────────

async def _load_agent_skill(db: AsyncSession, agent_skill_id: str) -> AgentSkill:
    result = await db.execute(
        select(AgentSkill)
        .options(selectinload(AgentSkill.skill))
        .where(AgentSkill.id == agent_skill_id)
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(404, "Agent skill association not found")
    return row


@agent_skills_router.get("/", response_model=list[AgentSkillResponse])
async def list_agent_skills(agent_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AgentSkill)
        .options(selectinload(AgentSkill.skill))
        .where(AgentSkill.agent_id == agent_id)
        .order_by(AgentSkill.priority)
    )
    return result.scalars().all()


@agent_skills_router.post("/", status_code=201, response_model=AgentSkillResponse)
async def attach_skill_to_agent(
    agent_id: str,
    data: AgentSkillCreate,
    db: AsyncSession = Depends(get_db),
):
    skill = await db.get(Skill, data.skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    existing = await db.execute(
        select(AgentSkill).where(
            AgentSkill.agent_id == agent_id,
            AgentSkill.skill_id == data.skill_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(409, "Skill already attached to this agent")

    agent_skill = AgentSkill(
        agent_id=agent_id,
        skill_id=data.skill_id,
        priority=data.priority,
        config_overrides=data.config_overrides,
        always_load=data.always_load,
    )
    db.add(agent_skill)
    await db.commit()

    result = await db.execute(
        select(AgentSkill)
        .options(selectinload(AgentSkill.skill))
        .where(AgentSkill.id == agent_skill.id)
    )
    return result.scalars().first()


@agent_skills_router.put("/{agent_skill_id}", response_model=AgentSkillResponse)
async def update_agent_skill(
    agent_id: str,
    agent_skill_id: str,
    data: AgentSkillUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await _load_agent_skill(db, agent_skill_id)
    if row.agent_id != agent_id:
        raise HTTPException(404, "Agent skill association not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    await db.commit()
    return await _load_agent_skill(db, agent_skill_id)


@agent_skills_router.delete("/{agent_skill_id}", status_code=204)
async def detach_skill_from_agent(
    agent_id: str,
    agent_skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSkill).where(
            AgentSkill.id == agent_skill_id,
            AgentSkill.agent_id == agent_id,
        )
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(404, "Agent skill association not found")
    await db.delete(row)
    await db.commit()


@agent_skills_router.post("/reorder", status_code=200)
async def reorder_agent_skills(
    agent_id: str,
    body: list[dict],
    db: AsyncSession = Depends(get_db),
):
    """Bulk-update priorities. body: [{agent_skill_id, priority}]"""
    for item in body:
        result = await db.execute(
            select(AgentSkill).where(
                AgentSkill.id == item["agent_skill_id"],
                AgentSkill.agent_id == agent_id,
            )
        )
        row = result.scalars().first()
        if row:
            row.priority = item["priority"]
    await db.commit()
    return {"status": "ok"}


# ─── Role-Skill Associations ──────────────────────────────────────────────────

@role_skills_router.get("/", response_model=list[RoleSkillResponse])
async def list_role_skills(role_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RoleSkill)
        .options(selectinload(RoleSkill.skill))
        .where(RoleSkill.role_id == role_id)
        .order_by(RoleSkill.priority)
    )
    return result.scalars().all()


@role_skills_router.post("/", status_code=201, response_model=RoleSkillResponse)
async def attach_skill_to_role(
    role_id: str,
    data: RoleSkillCreate,
    db: AsyncSession = Depends(get_db),
):
    skill = await db.get(Skill, data.skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    existing = await db.execute(
        select(RoleSkill).where(
            RoleSkill.role_id == role_id,
            RoleSkill.skill_id == data.skill_id,
        )
    )
    if existing.scalars().first():
        raise HTTPException(409, "Skill already attached to this role")

    role_skill = RoleSkill(
        role_id=role_id,
        skill_id=data.skill_id,
        priority=data.priority,
        config_overrides=data.config_overrides,
        always_load=data.always_load,
    )
    db.add(role_skill)
    await db.commit()

    result = await db.execute(
        select(RoleSkill)
        .options(selectinload(RoleSkill.skill))
        .where(RoleSkill.id == role_skill.id)
    )
    return result.scalars().first()


@role_skills_router.delete("/{role_skill_id}", status_code=204)
async def detach_skill_from_role(
    role_id: str,
    role_skill_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RoleSkill).where(
            RoleSkill.id == role_skill_id,
            RoleSkill.role_id == role_id,
        )
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(404, "Role skill association not found")
    await db.delete(row)
    await db.commit()
