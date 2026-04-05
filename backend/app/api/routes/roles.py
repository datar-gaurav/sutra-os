"""Agent Roles API — CRUD + predefined templates."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.role import AgentRole, ROLE_TEMPLATES

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("/templates")
async def list_role_templates():
    """Return the built-in role templates (not saved in DB)."""
    return ROLE_TEMPLATES


@router.post("/reseed", status_code=200)
async def reseed_roles(db: AsyncSession = Depends(get_db)):
    """Upsert all saved roles that match a ROLE_TEMPLATE name with the latest prompts/tools."""
    updated = []
    for tpl in ROLE_TEMPLATES:
        result = await db.execute(select(AgentRole).where(AgentRole.name == tpl["name"]))
        existing = result.scalars().first()
        if existing:
            for field, value in tpl.items():
                setattr(existing, field, value)
            updated.append(tpl["name"])
    await db.commit()
    return {"updated": updated}


@router.get("/")
async def list_roles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentRole).order_by(AgentRole.name))
    return result.scalars().all()


@router.post("/", status_code=201)
async def create_role(data: dict, db: AsyncSession = Depends(get_db)):
    role = AgentRole(
        name=data["name"],
        description=data.get("description"),
        system_prompt_template=data.get("system_prompt_template"),
        default_tools=data.get("default_tools", []),
        permissions=data.get("permissions", {}),
        reports_to_role=data.get("reports_to_role"),
        color=data.get("color"),
        icon=data.get("icon"),
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.get("/{role_id}")
async def get_role(role_id: str, db: AsyncSession = Depends(get_db)):
    role = await db.get(AgentRole, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    return role


@router.put("/{role_id}")
async def update_role(role_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    role = await db.get(AgentRole, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    for field in ("name", "description", "system_prompt_template", "default_tools",
                  "permissions", "reports_to_role", "color", "icon"):
        if field in data:
            setattr(role, field, data[field])
    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=204)
async def delete_role(role_id: str, db: AsyncSession = Depends(get_db)):
    role = await db.get(AgentRole, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    await db.delete(role)
    await db.commit()
