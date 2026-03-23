"""Agent Template CRUD + instantiate API routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AgentTemplateCreate, AgentTemplateResponse, AgentResponse
from app.core.audit import record_audit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.agent import Agent
from app.models.agent_template import AgentTemplate
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent-templates", tags=["agent-templates"])


@router.get("/", response_model=list[AgentTemplateResponse])
async def list_templates(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all agent templates (builtin + user-created), optionally filtered by category."""
    q = select(AgentTemplate).order_by(AgentTemplate.is_builtin.desc(), AgentTemplate.usage_count.desc())
    if category:
        q = q.where(AgentTemplate.category == category)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Return distinct template categories with counts."""
    result = await db.execute(
        select(AgentTemplate.category, func.count(AgentTemplate.id).label("count"))
        .group_by(AgentTemplate.category)
        .order_by(AgentTemplate.category)
    )
    return [{"category": row.category, "count": row.count} for row in result.all()]


@router.get("/{template_id}", response_model=AgentTemplateResponse)
async def get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single template by ID."""
    tpl = await db.get(AgentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.post("/", response_model=AgentTemplateResponse, status_code=201)
async def create_template(
    request: Request,
    payload: AgentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new custom agent template."""
    existing = await db.execute(select(AgentTemplate).where(AgentTemplate.name == payload.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Template name already exists")

    tpl = AgentTemplate(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        system_prompt=payload.system_prompt,
        default_tools=payload.default_tools,
        default_llm_provider=payload.default_llm_provider,
        default_llm_model=payload.default_llm_model,
        temperature=payload.temperature,
        role_name=payload.role_name,
        icon=payload.icon,
        color=payload.color,
        tags=payload.tags,
        is_builtin=False,
    )
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)

    await record_audit(
        db, action="agent_template.create", actor_id=current_user.id,
        resource_type="agent_template", resource_id=tpl.id,
        details={"name": tpl.name},
        ip_address=request.client.host if request.client else None,
    )
    return tpl


@router.put("/{template_id}", response_model=AgentTemplateResponse)
async def update_template(
    request: Request,
    template_id: str,
    payload: AgentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a template. Builtins can be edited (system_prompt, tools, model, temperature)."""
    tpl = await db.get(AgentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tpl, field, value)

    await db.flush()
    await db.refresh(tpl)
    return tpl


@router.post("/reseed", status_code=200)
async def reseed_builtin_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Force-update all builtin templates in the DB with the latest prompts and model assignments."""
    from app.models.agent_template import BUILTIN_TEMPLATES

    updated = []
    created = []
    for tpl_data in BUILTIN_TEMPLATES:
        result = await db.execute(select(AgentTemplate).where(AgentTemplate.name == tpl_data["name"]))
        existing = result.scalars().first()
        if existing:
            for field, value in tpl_data.items():
                setattr(existing, field, value)
            existing.is_builtin = True
            updated.append(tpl_data["name"])
        else:
            tpl = AgentTemplate(is_builtin=True, **tpl_data)
            db.add(tpl)
            created.append(tpl_data["name"])

    await db.commit()
    return {"updated": updated, "created": created}


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a custom (non-builtin) template."""
    tpl = await db.get(AgentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if tpl.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete builtin templates")
    await db.delete(tpl)


@router.post("/from-agent/{agent_id}", response_model=AgentTemplateResponse, status_code=201)
async def save_agent_as_template(
    request: Request,
    agent_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save an existing agent's configuration as a reusable template."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    template_name = data.get("name", f"{agent.name} Template")
    existing = await db.execute(select(AgentTemplate).where(AgentTemplate.name == template_name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Template name already exists")

    tpl = AgentTemplate(
        name=template_name,
        description=data.get("description", agent.description or f"Template based on {agent.name}"),
        category=data.get("category", "custom"),
        system_prompt=agent.system_prompt,
        default_tools=agent.enabled_tools or [],
        default_llm_provider=agent.llm_provider,
        default_llm_model=agent.llm_model,
        temperature=agent.temperature,
        role_name=None,
        icon=data.get("icon", "Bot"),
        color=data.get("color", "#6366f1"),
        tags=data.get("tags", []),
        is_builtin=False,
        created_by_agent_id=agent_id,
    )
    db.add(tpl)
    await db.flush()
    await db.refresh(tpl)

    await record_audit(
        db, action="agent_template.from_agent", actor_id=current_user.id,
        resource_type="agent_template", resource_id=tpl.id,
        details={"source_agent_id": agent_id, "name": tpl.name},
        ip_address=request.client.host if request.client else None,
    )
    return tpl


@router.post("/{template_id}/instantiate", response_model=AgentResponse, status_code=201)
async def instantiate_template(
    request: Request,
    template_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new agent from a template."""
    from app.api.schemas import AgentResponse as AgentResponseSchema

    tpl = await db.get(AgentTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    agent_name = data.get("name")
    if not agent_name:
        raise HTTPException(status_code=400, detail="Agent name is required")

    # Check name uniqueness
    existing = await db.execute(select(Agent).where(Agent.name == agent_name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Agent name already exists")

    # Merge template config with any overrides from the request
    system_prompt = data.get("system_prompt", tpl.system_prompt)
    if data.get("custom_instructions"):
        system_prompt = f"{system_prompt}\n\nAdditional Instructions:\n{data['custom_instructions']}"

    agent = Agent(
        name=agent_name,
        description=data.get("description", tpl.description),
        system_prompt=system_prompt,
        temperature=data.get("temperature", tpl.temperature),
        max_tokens=data.get("max_tokens", 4096),
        llm_provider=data.get("llm_provider", tpl.default_llm_provider),
        llm_model=data.get("llm_model", tpl.default_llm_model),
        enabled_tools=tpl.default_tools,
        template_id=template_id,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    # Increment template usage count
    tpl.usage_count = (tpl.usage_count or 0) + 1
    await db.flush()

    await record_audit(
        db, action="agent.create_from_template", actor_id=current_user.id,
        resource_type="agent", resource_id=agent.id,
        details={"template_id": template_id, "template_name": tpl.name, "agent_name": agent.name},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponseSchema.model_validate(agent)
