"""Skills API — CRUD for skills, agent-skill associations, role-skill associations."""

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
    SkillCreate,
    SkillExportBundle,
    SkillResponse,
    SkillUpdate,
)
from app.db.session import get_db
from app.models.skill import AgentSkill, RoleSkill, Skill, BUILTIN_SKILLS

router = APIRouter(prefix="/skills", tags=["skills"])
agent_skills_router = APIRouter(prefix="/agents/{agent_id}/skills", tags=["skills"])
role_skills_router = APIRouter(prefix="/roles/{role_id}/skills", tags=["skills"])


# ─── Skill CRUD ───────────────────────────────────────────────────────────────

@router.get("/builtin")
async def list_builtin_skills():
    """Return the built-in skill definitions (from constant, no DB query needed)."""
    return BUILTIN_SKILLS


@router.get("/reseed", status_code=200)
async def reseed_skills(db: AsyncSession = Depends(get_db)):
    """Upsert all BUILTIN_SKILLS into the skills table."""
    created, updated = [], []
    for skill_data in BUILTIN_SKILLS:
        result = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
        existing = result.scalars().first()
        if existing:
            for field, value in skill_data.items():
                setattr(existing, field, value)
            existing.source = "builtin"
            updated.append(skill_data["name"])
        else:
            db.add(Skill(source="builtin", **skill_data))
            created.append(skill_data["name"])
    await db.commit()
    return {"created": created, "updated": updated}


@router.get("/")
async def list_skills(
    category: str | None = None,
    source: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Skill).order_by(Skill.category, Skill.name)
    if category:
        query = query.where(Skill.category == category)
    if source:
        query = query.where(Skill.source == source)
    result = await db.execute(query)
    skills = result.scalars().all()
    if search:
        s = search.lower()
        skills = [sk for sk in skills if s in sk.name.lower() or (sk.description and s in sk.description.lower())]
    return skills


@router.post("/", status_code=201, response_model=SkillResponse)
async def create_skill(data: SkillCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Skill).where(Skill.name == data.name))
    if existing.scalars().first():
        raise HTTPException(409, f"A skill named '{data.name}' already exists")
    skill = Skill(source="custom", **data.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(skill_id: str, data: SkillUpdate, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(skill, field, value)
    await db.commit()
    await db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db)):
    skill = await db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    if skill.source == "builtin":
        raise HTTPException(403, "Built-in skills cannot be deleted")
    await db.delete(skill)
    await db.commit()


# ─── Export / Import ──────────────────────────────────────────────────────────

@router.post("/export")
async def export_skills(body: dict, db: AsyncSession = Depends(get_db)):
    """Export selected skills as a portable JSON bundle."""
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
    """Import skills from a JSON bundle file."""
    content = await file.read()
    try:
        bundle_data = json.loads(content)
        skills_data = bundle_data.get("skills", [])
    except (json.JSONDecodeError, AttributeError):
        raise HTTPException(400, "Invalid skill bundle format")

    created, skipped = [], []
    for sd in skills_data:
        name = sd.get("name")
        if not name:
            continue
        existing = await db.execute(select(Skill).where(Skill.name == name))
        if existing.scalars().first():
            skipped.append(name)
            continue
        skill = Skill(
            name=name,
            description=sd.get("description"),
            version=sd.get("version", "1.0.0"),
            category=sd.get("category", "general"),
            prompt_fragment=sd.get("prompt_fragment", ""),
            required_tool_ids=sd.get("required_tool_ids", []),
            config_schema=sd.get("config_schema"),
            icon=sd.get("icon"),
            color=sd.get("color"),
            source="custom",
        )
        db.add(skill)
        created.append(name)
    await db.commit()
    return {"created": created, "skipped": skipped}


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
    # Verify skill exists
    skill = await db.get(Skill, data.skill_id)
    if not skill:
        raise HTTPException(404, "Skill not found")
    # Check for duplicate
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
