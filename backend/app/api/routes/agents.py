"""Agent CRUD API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AgentCreate, AgentPerformanceResponse, AgentResponse, AgentUpdate,
    FolderCreate, FolderResponse, FolderUpdate
)
from app.core.agent_manager import agent_manager
from app.core.audit import record_audit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.agent import Agent, AgentFolder
from app.models.role import AgentRole
from app.models.user import User

router = APIRouter(prefix="/agents", tags=["agents"])


# ─── Folders ──────────────────────────────────────────────────────────────────

@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(db: AsyncSession = Depends(get_db)):
    """List all agent folders."""
    result = await db.execute(select(AgentFolder).order_by(AgentFolder.name))
    return result.scalars().all()


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(payload: FolderCreate, db: AsyncSession = Depends(get_db)):
    """Create a new folder."""
    # Check if name exists
    existing = await db.execute(select(AgentFolder).where(AgentFolder.name == payload.name))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Folder name already exists")
    
    folder = AgentFolder(name=payload.name)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.put("/folders/{folder_id}", response_model=FolderResponse)
async def update_folder(
    folder_id: str, payload: FolderUpdate, db: AsyncSession = Depends(get_db)
):
    """Rename a folder."""
    folder = await db.get(AgentFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    existing = await db.execute(select(AgentFolder).where(AgentFolder.name == payload.name))
    existing_folder = existing.scalars().first()
    if existing_folder and existing_folder.id != folder_id:
        raise HTTPException(status_code=400, detail="Folder name already exists")

    folder.name = payload.name
    await db.flush()
    await db.refresh(folder)
    return folder


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a folder. Agents inside it will become uncategorized (folder_id=NULL)."""
    folder = await db.get(AgentFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    await db.delete(folder)
    # The ForeignKey has ondelete="SET NULL", so DB handles removing agents from folder


# ─── Agents ───────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    include_archived: bool = Query(False, description="Include archived agents"),
    db: AsyncSession = Depends(get_db),
):
    """List all agents. Archived agents are excluded by default."""
    q = select(Agent).order_by(Agent.created_at.desc())
    if not include_archived:
        q = q.where((Agent.is_archived == False) | (Agent.is_archived == None))  # noqa: E712
    result = await db.execute(q)
    agents = result.scalars().all()

    # Enrich with live status
    response = []
    for agent in agents:
        data = AgentResponse.model_validate(agent)
        if agent_manager.is_running(agent.id):
            data.status = "running"
            data.is_active = True
        response.append(data)
    return response


@router.get("/org-chart")
async def get_org_chart_list(db: AsyncSession = Depends(get_db)):
    """Return all agents with their role, team, and reporting relationships."""
    result = await db.execute(select(Agent).order_by(Agent.name))
    agents = result.scalars().all()

    roles_result = await db.execute(select(AgentRole))
    roles_map = {r.id: r for r in roles_result.scalars().all()}

    nodes = []
    for agent in agents:
        role = roles_map.get(agent.role_id) if agent.role_id else None
        nodes.append({
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "role_id": agent.role_id,
            "role_name": role.name if role else None,
            "role_color": role.color if role else None,
            "role_icon": role.icon if role else None,
            "team_id": agent.team_id,
            "reports_to_agent_id": agent.reports_to_agent_id,
            "skills": agent.skills or [],
            "avatar_url": agent.avatar_url,
        })
    return nodes


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single agent by ID."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = AgentResponse.model_validate(agent)
    if agent_manager.is_running(agent.id):
        data.status = "running"
        data.is_active = True
    return data


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(
    request: Request,
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new agent."""
    agent = Agent(
        name=payload.name,
        description=payload.description,
        avatar_url=payload.avatar_url,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        purpose_id=payload.purpose_id,
        llm_provider=payload.llm_provider,
        llm_model=payload.llm_model,
        enabled_tools=payload.enabled_tools,
        folder_id=payload.folder_id,
        slack_channel_id=payload.slack_channel_id,
        telegram_enabled=payload.telegram_enabled,
        telegram_chat_id=payload.telegram_chat_id,
        online_notification_enabled=payload.online_notification_enabled,
        metadata_=payload.metadata_ or {},
        auto_approve_below=payload.auto_approve_below,
        max_tool_calls_per_run=payload.max_tool_calls_per_run,
        max_tokens_per_day=payload.max_tokens_per_day,
        voice_enabled=payload.voice_enabled,
        voice_id=payload.voice_id,
        voice_provider_tts=payload.voice_provider_tts,
        voice_provider_stt=payload.voice_provider_stt,
        voice_speed=payload.voice_speed,
        telegram_voice_enabled=payload.telegram_voice_enabled,
        web_voice_enabled=payload.web_voice_enabled,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    await record_audit(
        db, action="agent.create", actor_id=current_user.id,
        resource_type="agent", resource_id=agent.id,
        details={"name": agent.name, "provider": agent.llm_provider},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    request: Request,
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)
    await record_audit(
        db, action="agent.update", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        details={"fields_changed": list(update_data.keys())},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    request: Request,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Stop if running
    if agent_manager.is_running(agent_id):
        await agent_manager.stop_agent(agent_id)

    agent_name = agent.name
    await db.delete(agent)
    await record_audit(
        db, action="agent.delete", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        details={"name": agent_name},
        ip_address=request.client.host if request.client else None,
    )


async def _get_agent_skills_config(db: AsyncSession, agent_id: str) -> dict:
    """Deprecated. Skills are now fetched per-turn by the orchestrator; the agent
    config no longer carries skill_fragments/skill_tool_ids/skill_config_overrides.

    Kept as a stub for any caller that still references it.
    """
    return {}


@router.post("/{agent_id}/start")
async def start_agent(
    request: Request,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start an agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    config = {
        "id": agent.id,
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "purpose_id": agent.purpose_id,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "enabled_tools": agent.enabled_tools or [],
        "secondary_provider": agent.secondary_provider,
        "secondary_model": agent.secondary_model,
        "fallback_provider": agent.fallback_provider,
        "fallback_model": agent.fallback_model,
        "telegram_enabled": agent.telegram_enabled,
        "telegram_chat_id": agent.telegram_chat_id,
        "online_notification_enabled": agent.online_notification_enabled,
        "auto_approve_below": agent.auto_approve_below,
        "max_tool_calls_per_run": agent.max_tool_calls_per_run or 0,
        "max_tokens_per_day": agent.max_tokens_per_day or 0,
        "skill_routing_enabled": getattr(agent, "skill_routing_enabled", None),
    }
    result = await agent_manager.start_agent(config)

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

    # Update DB status
    agent.status = result["status"]
    agent.is_active = result["status"] == "running"
    await db.flush()

    await record_audit(
        db, action="agent.start", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/{agent_id}/stop")
async def stop_agent(
    request: Request,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stop a running agent."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await agent_manager.stop_agent(agent_id)

    agent.status = "stopped"
    agent.is_active = False
    await db.flush()

    await record_audit(
        db, action="agent.stop", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.post("/{agent_id}/apply-role")
async def apply_role_to_agent(
    agent_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Apply a role to an agent — sets role_id and optionally patches system prompt + tools."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    role_id = data.get("role_id")
    if not role_id:
        raise HTTPException(400, "role_id required")

    role = await db.get(AgentRole, role_id)
    if not role:
        raise HTTPException(404, "Role not found")

    agent.role_id = role_id
    if data.get("apply_prompt") and role.system_prompt_template:
        agent.system_prompt = role.system_prompt_template
    if data.get("apply_tools") and role.default_tools:
        agent.enabled_tools = role.default_tools
    if data.get("reports_to_agent_id") is not None:
        agent.reports_to_agent_id = data["reports_to_agent_id"]
    if data.get("team_id") is not None:
        agent.team_id = data["team_id"]
    if data.get("skills") is not None:
        agent.skills = data["skills"]

    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/restart")
async def restart_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Restart an agent with current config."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    config = {
        "id": agent.id,
        "name": agent.name,
        "system_prompt": agent.system_prompt,
        "purpose_id": agent.purpose_id,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model,
        "temperature": agent.temperature,
        "max_tokens": agent.max_tokens,
        "enabled_tools": agent.enabled_tools or [],
        "secondary_provider": agent.secondary_provider,
        "secondary_model": agent.secondary_model,
        "fallback_provider": agent.fallback_provider,
        "fallback_model": agent.fallback_model,
        "telegram_enabled": agent.telegram_enabled,
        "telegram_chat_id": agent.telegram_chat_id,
        "online_notification_enabled": agent.online_notification_enabled,
        "auto_approve_below": agent.auto_approve_below,
        "max_tool_calls_per_run": agent.max_tool_calls_per_run or 0,
        "max_tokens_per_day": agent.max_tokens_per_day or 0,
        "skill_routing_enabled": getattr(agent, "skill_routing_enabled", None),
    }
    result = await agent_manager.restart_agent(config)

    agent.status = result["status"]
    agent.is_active = result["status"] == "running"
    await db.flush()

    return result


@router.post("/{agent_id}/clone", response_model=AgentResponse, status_code=201)
async def clone_agent(
    request: Request,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clone an agent, creating a stopped copy with 'Copy of' prefix."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    clone = Agent(
        name=f"Copy of {agent.name}",
        description=agent.description,
        avatar_url=agent.avatar_url,
        system_prompt=agent.system_prompt,
        temperature=agent.temperature,
        max_tokens=agent.max_tokens,
        purpose_id=agent.purpose_id,
        llm_provider=agent.llm_provider,
        llm_model=agent.llm_model,
        enabled_tools=agent.enabled_tools,
        folder_id=agent.folder_id,
        slack_channel_id=agent.slack_channel_id,
        telegram_enabled=agent.telegram_enabled,
        telegram_chat_id=agent.telegram_chat_id,
        online_notification_enabled=agent.online_notification_enabled,
        metadata_=agent.metadata_ or {},
        auto_approve_below=agent.auto_approve_below,
        max_tool_calls_per_run=agent.max_tool_calls_per_run,
        max_tokens_per_day=agent.max_tokens_per_day,
        secondary_provider=agent.secondary_provider,
        secondary_model=agent.secondary_model,
        fallback_provider=agent.fallback_provider,
        fallback_model=agent.fallback_model,
    )
    db.add(clone)
    await db.flush()
    await db.refresh(clone)
    await record_audit(
        db, action="agent.clone", actor_id=current_user.id,
        resource_type="agent", resource_id=clone.id,
        details={"name": clone.name, "cloned_from": agent_id},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponse.model_validate(clone)


@router.post("/{agent_id}/archive", response_model=AgentResponse)
async def archive_agent(
    request: Request,
    agent_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive (retire) an agent. Stops it and marks it as archived."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_archived:
        raise HTTPException(status_code=400, detail="Agent is already archived")

    # Stop if running
    if agent_manager.is_running(agent_id):
        await agent_manager.stop_agent(agent_id)

    agent.is_archived = True
    agent.archived_at = datetime.now(timezone.utc)
    agent.archived_reason = data.get("reason", "")
    agent.status = "stopped"
    agent.is_active = False
    await db.flush()
    await db.refresh(agent)

    await record_audit(
        db, action="agent.archive", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        details={"name": agent.name, "reason": agent.archived_reason},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/unarchive", response_model=AgentResponse)
async def unarchive_agent(
    request: Request,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore an archived agent back to active status."""
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_archived:
        raise HTTPException(status_code=400, detail="Agent is not archived")

    agent.is_archived = False
    agent.archived_at = None
    agent.archived_reason = None
    await db.flush()
    await db.refresh(agent)

    await record_audit(
        db, action="agent.unarchive", actor_id=current_user.id,
        resource_type="agent", resource_id=agent_id,
        details={"name": agent.name},
        ip_address=request.client.host if request.client else None,
    )
    return AgentResponse.model_validate(agent)


@router.get("/{agent_id}/performance", response_model=AgentPerformanceResponse)
async def get_agent_performance(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Compute and return performance metrics for an agent."""
    from app.models.trace import ExecutionTrace
    from app.models.task import Task, TaskStatus

    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Execution trace stats
    trace_result = await db.execute(
        select(
            func.count(ExecutionTrace.id).label("total"),
            func.sum(ExecutionTrace.had_error.cast("integer")).label("errors"),
            func.avg(ExecutionTrace.latency_ms).label("avg_latency"),
        ).where(ExecutionTrace.agent_id == agent_id)
    )
    trace_row = trace_result.one()
    total_invocations = int(trace_row.total or 0)
    error_count = int(trace_row.errors or 0)
    avg_latency_ms = float(trace_row.avg_latency or 0.0)
    total_cost_usd = 0.0  # Populated from budget spend tracking if available
    error_rate = (error_count / total_invocations) if total_invocations > 0 else 0.0

    # Task stats
    tasks_created_result = await db.execute(
        select(func.count(Task.id)).where(Task.assignee_agent_id == agent_id)
    )
    total_tasks_created = int(tasks_created_result.scalar() or 0)

    tasks_done_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.assignee_agent_id == agent_id,
            Task.status == TaskStatus.done,
        )
    )
    total_tasks_completed = int(tasks_done_result.scalar() or 0)
    task_completion_rate = (
        total_tasks_completed / total_tasks_created if total_tasks_created > 0 else 0.0
    )

    # Performance score (0-100): weighted composite
    # Components: task completion (40%), low error rate (30%), responsiveness (30%)
    task_score = task_completion_rate * 40
    error_score = max(0, (1 - error_rate)) * 30
    latency_score = max(0, min(30, 30 * (1 - min(avg_latency_ms, 10000) / 10000)))
    performance_score = round(task_score + error_score + latency_score, 1)

    return AgentPerformanceResponse(
        agent_id=agent_id,
        agent_name=agent.name,
        total_invocations=total_invocations,
        error_count=error_count,
        error_rate=round(error_rate, 4),
        avg_latency_ms=round(avg_latency_ms, 1),
        total_tasks_created=total_tasks_created,
        total_tasks_completed=total_tasks_completed,
        task_completion_rate=round(task_completion_rate, 4),
        total_cost_usd=round(total_cost_usd, 6),
        performance_score=performance_score,
    )
