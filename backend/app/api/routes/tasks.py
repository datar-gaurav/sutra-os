"""Task and Project CRUD API routes."""

import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ProjectCreate, ProjectResponse, ProjectUpdate,
    TaskCreate, TaskResponse, TaskUpdate, TaskDecomposeRequest,
)
from app.core.audit import record_audit
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

router = APIRouter(tags=["tasks"])


# ─── Projects ─────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        name=payload.name,
        description=payload.description,
        status=payload.status.value,
        owner_user_id=current_user.id,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="create_project", resource_type="project", resource_id=project.id,
                       details={"name": project.name})
    return project


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(project, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    await db.refresh(project)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="update_project", resource_type="project", resource_id=project.id)
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="delete_project", resource_type="project", resource_id=project_id)


# ─── Tasks ────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: str | None = None,
    status: str | None = None,
    assignee_agent_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Task)
    if project_id:
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status == status)
    if assignee_agent_id:
        query = query.where(Task.assignee_agent_id == assignee_agent_id)
    query = query.order_by(Task.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = Task(
        title=payload.title,
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        project_id=payload.project_id,
        parent_task_id=payload.parent_task_id,
        assignee_agent_id=payload.assignee_agent_id,
        assignee_user_id=payload.assignee_user_id,
        creator_user_id=current_user.id,
        due_date=payload.due_date,
        notes=payload.notes,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="create_task", resource_type="task", resource_id=task.id,
                       details={"title": task.title, "status": task.status})
    asyncio.create_task(_dispatch("task.created", {"id": task.id, "title": task.title, "status": task.status, "priority": task.priority}))
    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(task, field, value.value if hasattr(value, "value") else value)
    await db.flush()
    await db.refresh(task)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="update_task", resource_type="task", resource_id=task.id,
                       details={"status": task.status})
    event = "task.completed" if task.status == "done" else "task.updated"
    asyncio.create_task(_dispatch(event, {"id": task.id, "title": task.title, "status": task.status}))
    return task


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    await record_audit(db, actor_type="user", actor_id=current_user.id,
                       action="delete_task", resource_type="task", resource_id=task_id)


@router.get("/tasks/{task_id}/subtasks", response_model=list[TaskResponse])
async def list_subtasks(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(Task.parent_task_id == task_id).order_by(Task.created_at)
    )
    return result.scalars().all()


@router.post("/tasks/{task_id}/decompose", response_model=list[TaskResponse], status_code=201)
async def decompose_task(
    task_id: str,
    payload: TaskDecomposeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Use an LLM to break a task into subtasks."""
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    prompt = (
        f"Break down the following task into {payload.max_subtasks} or fewer concrete subtasks.\n\n"
        f"Task title: {task.title}\n"
        f"Task description: {task.description or 'N/A'}\n"
    )
    if payload.guidance:
        prompt += f"Additional guidance: {payload.guidance}\n"
    prompt += (
        "\nRespond ONLY with a JSON array of objects. Each object must have:\n"
        "- title (string, required)\n"
        "- description (string, optional)\n"
        "- priority (one of: critical, high, medium, low; default: medium)\n\n"
        'Example: [{"title": "Research options", "description": "Investigate tools", "priority": "high"}]'
    )

    from app.core.llm_registry import llm_registry
    from app.models.agent import Agent as AgentModel
    from app.models.task import TaskPriority

    llm = None
    if payload.agent_id:
        agent = await db.get(AgentModel, payload.agent_id)
        if agent:
            try:
                llm = llm_registry.get_chat_model(
                    provider=agent.llm_provider,
                    model=agent.llm_model,
                    temperature=0.3,
                    streaming=False,
                )
            except Exception:
                pass

    if llm is None:
        # Fall back to first available provider with an API key
        from app.models.llm_provider import LLMProvider
        result = await db.execute(
            select(LLMProvider).where(LLMProvider.is_enabled == True).order_by(LLMProvider.is_default.desc())
        )
        provider_row = result.scalars().first()
        if provider_row:
            try:
                llm = llm_registry.get_chat_model(
                    provider=provider_row.provider_type,
                    model="gpt-4o-mini" if provider_row.provider_type == "openai" else "llama3",
                    temperature=0.3,
                    streaming=False,
                )
            except Exception:
                pass

    if llm is None:
        raise HTTPException(status_code=503, detail="No LLM provider available for decomposition")

    from langchain_core.messages import HumanMessage
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if not json_match:
        raise HTTPException(status_code=422, detail="LLM did not return a valid JSON array")

    try:
        subtasks_data = json.loads(json_match.group())
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Failed to parse LLM response as JSON")

    created = []
    for s in subtasks_data[:payload.max_subtasks]:
        title = str(s.get("title", "")).strip()
        if not title:
            continue
        priority = s.get("priority", "medium")
        if priority not in [p.value for p in TaskPriority]:
            priority = "medium"
        subtask = Task(
            title=title,
            description=s.get("description") or None,
            status="todo",
            priority=priority,
            project_id=task.project_id,
            parent_task_id=task_id,
            creator_user_id=current_user.id,
        )
        db.add(subtask)
        created.append(subtask)

    await db.flush()
    for subtask in created:
        await db.refresh(subtask)

    await record_audit(
        db, actor_type="user", actor_id=current_user.id,
        action="decompose_task", resource_type="task", resource_id=task_id,
        details={"subtask_count": len(created)},
    )
    return created


async def _dispatch(event: str, payload: dict) -> None:
    try:
        from app.core.webhook_service import dispatch_event
        await dispatch_event(event, payload)
    except Exception:
        pass
