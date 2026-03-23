"""Project management routes — CRUD, memories, decisions, files, switching, compaction."""

import mimetypes
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CompactionResultResponse,
    MemoryCreate,
    MemoryResponse,
    ProjectCreate,
    ProjectDecisionCreate,
    ProjectDecisionResponse,
    ProjectDecisionUpdate,
    ProjectFileResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.config import settings
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.memory import Memory, MemoryTier, MemoryType
from app.models.project import Project, slugify
from app.models.project_decision import ProjectDecision
from app.models.project_file import ProjectFile

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _ensure_unique_slug(db: AsyncSession, base_slug: str, exclude_id: str | None = None) -> str:
    """Ensure slug is unique, appending -N if needed."""
    slug = base_slug
    counter = 1
    while True:
        stmt = select(Project).where(Project.slug == slug)
        if exclude_id:
            stmt = stmt.where(Project.id != exclude_id)
        result = await db.execute(stmt)
        if not result.scalars().first():
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def _ensure_files_dir(slug: str) -> str:
    """Create the project files directory and return its path."""
    path = os.path.join(settings.project_files_root, slug)
    os.makedirs(path, exist_ok=True)
    return path


# ── Project CRUD ─────────────────────────────────────────────────────────────


@router.get("/")
async def list_projects(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from app.models.task import Task

    stmt = select(Project).order_by(Project.updated_at.desc())
    if status:
        stmt = stmt.where(Project.status == status)
    result = await db.execute(stmt)
    projects = result.scalars().all()

    # Compute task counts per project
    project_ids = [p.id for p in projects]
    task_counts: dict[str, int] = {}
    if project_ids:
        count_result = await db.execute(
            select(Task.project_id, func.count(Task.id))
            .where(Task.project_id.in_(project_ids))
            .group_by(Task.project_id)
        )
        task_counts = {row[0]: row[1] for row in count_result.all()}

    # Compute conversation counts per project (in case denormalized count is stale)
    conv_counts: dict[str, int] = {}
    if project_ids:
        conv_result = await db.execute(
            select(Conversation.project_id, func.count(Conversation.id))
            .where(Conversation.project_id.in_(project_ids))
            .group_by(Conversation.project_id)
        )
        conv_counts = {row[0]: row[1] for row in conv_result.all()}

    return [
        {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "description": p.description,
            "status": p.status,
            "color": p.color,
            "icon": p.icon,
            "owner_user_id": p.owner_user_id,
            "default_agent_id": p.default_agent_id,
            "memory_count": p.memory_count or 0,
            "conversation_count": conv_counts.get(p.id, p.conversation_count or 0),
            "task_count": task_counts.get(p.id, 0),
            "last_active_at": str(p.last_active_at) if p.last_active_at else None,
            "compaction_summary": p.compaction_summary,
            "created_at": str(p.created_at),
            "updated_at": str(p.updated_at),
        }
        for p in projects
    ]


@router.post("/", response_model=ProjectResponse)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    base_slug = slugify(payload.name)
    slug = await _ensure_unique_slug(db, base_slug)
    files_dir = _ensure_files_dir(slug)

    project = Project(
        name=payload.name,
        slug=slug,
        description=payload.description,
        status=payload.status.value if payload.status else "active",
        color=payload.color,
        icon=payload.icon,
        default_agent_id=payload.default_agent_id,
        files_dir=files_dir,
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    await db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, payload: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "status" and value is not None:
            setattr(project, field, value.value if hasattr(value, "value") else value)
        elif field == "name" and value:
            project.name = value
            new_slug = slugify(value)
            project.slug = await _ensure_unique_slug(db, new_slug, exclude_id=project_id)
        else:
            setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.status = "archived"
    await db.commit()
    return {"detail": "Project archived"}


# ── Project Switch ───────────────────────────────────────────────────────────


@router.post("/{project_id}/switch/{agent_id}")
async def switch_project(project_id: str, agent_id: str, db: AsyncSession = Depends(get_db)):
    """Switch an agent to work on this project."""
    from app.core.project_memory_service import get_active_project, handle_project_switch

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    old_project_id = await get_active_project(db, agent_id)
    summary = await handle_project_switch(db, agent_id, old_project_id, project_id)
    await db.commit()
    return {"detail": summary, "project_id": project_id}


@router.delete("/{project_id}/switch/{agent_id}")
async def clear_active_project(project_id: str, agent_id: str, db: AsyncSession = Depends(get_db)):
    """Clear the active project for an agent."""
    from app.core.project_memory_service import set_active_project

    await set_active_project(db, agent_id, None)
    await db.commit()
    return {"detail": "Active project cleared"}


# ── Project Memories ─────────────────────────────────────────────────────────


@router.get("/{project_id}/memories", response_model=list[MemoryResponse])
async def list_project_memories(
    project_id: str,
    tier: str | None = None,
    memory_type: str | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Memory)
        .where(Memory.project_id == project_id, Memory.is_deleted == False)
        .order_by(Memory.created_at.desc())
        .limit(limit)
    )
    if tier:
        stmt = stmt.where(Memory.tier == tier)
    if memory_type:
        stmt = stmt.where(Memory.type == memory_type)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/{project_id}/memories", response_model=MemoryResponse)
async def create_project_memory(
    project_id: str, payload: MemoryCreate, db: AsyncSession = Depends(get_db)
):
    from app.core.memory_service import memory_service

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    memory = await memory_service.save(
        db=db,
        content=payload.content,
        agent_id=payload.agent_id,
        memory_type=MemoryType(payload.type) if payload.type else MemoryType.fact,
        importance_score=payload.importance_score or 0.5,
        tier=MemoryTier(payload.tier) if payload.tier else MemoryTier.recall,
        source="user",
        project_id=project_id,
    )
    project.memory_count = (project.memory_count or 0) + 1
    await db.commit()
    return memory


@router.get("/{project_id}/memories/search")
async def search_project_memories(
    project_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(10, le=50),
    db: AsyncSession = Depends(get_db),
):
    from app.core.project_memory_service import _search_project_memories

    memories = await _search_project_memories(db, project_id, q, limit=limit)
    return [
        {
            "id": m.id,
            "content": m.content,
            "type": m.type,
            "tier": m.tier,
            "importance_score": m.importance_score,
            "decay_score": m.decay_score,
            "created_at": str(m.created_at),
        }
        for m in memories
    ]


# ── Project Tasks ────────────────────────────────────────────────────────────


@router.get("/{project_id}/tasks")
async def list_project_tasks(
    project_id: str,
    status: str | None = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks belonging to this project."""
    from app.models.task import Task
    from app.models.agent import Agent

    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.updated_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Task.status == status)
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    # Resolve agent names for assignees
    agent_ids = {t.assignee_agent_id for t in tasks if t.assignee_agent_id}
    agent_names: dict[str, str] = {}
    if agent_ids:
        agent_result = await db.execute(
            select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids))
        )
        agent_names = {row.id: row.name for row in agent_result.all()}

    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "assignee_agent_id": t.assignee_agent_id,
            "assignee_agent_name": agent_names.get(t.assignee_agent_id) if t.assignee_agent_id else None,
            "assignee_user_id": t.assignee_user_id,
            "due_date": str(t.due_date) if t.due_date else None,
            "created_at": str(t.created_at),
            "updated_at": str(t.updated_at),
        }
        for t in tasks
    ]


# ── Project Conversations ───────────────────────────────────────────────────


@router.get("/{project_id}/conversations")
async def list_project_conversations(
    project_id: str,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List conversations linked to this project, with agent names and message counts."""
    from app.models.agent import Agent

    result = await db.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    conversations = result.scalars().all()

    # Resolve agent names
    agent_ids = {c.agent_id for c in conversations}
    agent_names: dict[str, str] = {}
    if agent_ids:
        agent_result = await db.execute(
            select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids))
        )
        agent_names = {row.id: row.name for row in agent_result.all()}

    # Message counts
    conv_ids = [c.id for c in conversations]
    msg_counts: dict[str, int] = {}
    if conv_ids:
        count_result = await db.execute(
            select(Message.conversation_id, func.count(Message.id))
            .where(Message.conversation_id.in_(conv_ids))
            .group_by(Message.conversation_id)
        )
        msg_counts = {row[0]: row[1] for row in count_result.all()}

    return [
        {
            "id": c.id,
            "agent_id": c.agent_id,
            "agent_name": agent_names.get(c.agent_id, "Unknown"),
            "title": c.title,
            "source": c.source,
            "message_count": msg_counts.get(c.id, 0),
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
        for c in conversations
    ]


# ── Project Decisions ────────────────────────────────────────────────────────


@router.get("/{project_id}/decisions", response_model=list[ProjectDecisionResponse])
async def list_project_decisions(
    project_id: str,
    importance: str | None = None,
    tag: str | None = None,
    include_superseded: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ProjectDecision).where(ProjectDecision.project_id == project_id)
    if not include_superseded:
        stmt = stmt.where(ProjectDecision.is_superseded == False)
    if importance:
        stmt = stmt.where(ProjectDecision.importance == importance)
    stmt = stmt.order_by(ProjectDecision.created_at.desc())
    result = await db.execute(stmt)
    decisions = result.scalars().all()

    if tag:
        decisions = [d for d in decisions if tag in (d.tags or [])]

    return decisions


@router.post("/{project_id}/decisions", response_model=ProjectDecisionResponse)
async def create_project_decision(
    project_id: str, payload: ProjectDecisionCreate, db: AsyncSession = Depends(get_db)
):
    from app.core.project_memory_service import record_decision

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    dec = await record_decision(
        db=db,
        project_id=project_id,
        title=payload.title,
        decision=payload.decision,
        reasoning=payload.reasoning,
        importance=payload.importance,
        alternatives_considered=payload.alternatives_considered,
        tags=payload.tags,
        data_points=payload.data_points,
        conversation_id=payload.conversation_id,
        agent_id=payload.agent_id,
    )
    await db.commit()
    return dec


@router.put("/{project_id}/decisions/{decision_id}", response_model=ProjectDecisionResponse)
async def update_project_decision(
    project_id: str, decision_id: str,
    payload: ProjectDecisionUpdate,
    db: AsyncSession = Depends(get_db),
):
    dec = await db.get(ProjectDecision, decision_id)
    if not dec or dec.project_id != project_id:
        raise HTTPException(status_code=404, detail="Decision not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dec, field, value)

    await db.commit()
    await db.refresh(dec)
    return dec


# ── Project Files ────────────────────────────────────────────────────────────


@router.get("/{project_id}/files", response_model=list[ProjectFileResponse])
async def list_project_files(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProjectFile)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{project_id}/files", response_model=ProjectFileResponse)
async def upload_project_file(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ensure files directory exists
    files_dir = project.files_dir or _ensure_files_dir(project.slug or project.id)
    if not project.files_dir:
        project.files_dir = files_dir

    # Save file to disk
    file_path = os.path.join(files_dir, file.filename)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    mime = file.content_type or mimetypes.guess_type(file.filename)[0]
    pf = ProjectFile(
        project_id=project_id,
        file_name=file.filename,
        file_path=file.filename,  # relative path
        file_size=len(content),
        mime_type=mime,
    )
    db.add(pf)
    await db.flush()
    await db.refresh(pf)
    await db.commit()
    return pf


@router.get("/{project_id}/files/{file_id}/download")
async def download_project_file(project_id: str, file_id: str, db: AsyncSession = Depends(get_db)):
    pf = await db.get(ProjectFile, file_id)
    if not pf or pf.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found")

    project = await db.get(Project, project_id)
    if not project or not project.files_dir:
        raise HTTPException(status_code=404, detail="Project files directory not found")

    full_path = os.path.join(project.files_dir, pf.file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(full_path, filename=pf.file_name, media_type=pf.mime_type)


@router.delete("/{project_id}/files/{file_id}")
async def delete_project_file(project_id: str, file_id: str, db: AsyncSession = Depends(get_db)):
    pf = await db.get(ProjectFile, file_id)
    if not pf or pf.project_id != project_id:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete from disk
    project = await db.get(Project, project_id)
    if project and project.files_dir:
        full_path = os.path.join(project.files_dir, pf.file_path)
        if os.path.isfile(full_path):
            os.remove(full_path)

    await db.delete(pf)
    await db.commit()
    return {"detail": "File deleted"}


# ── Manual Compaction ────────────────────────────────────────────────────────


@router.post("/{project_id}/compact", response_model=CompactionResultResponse)
async def compact_project_endpoint(project_id: str, db: AsyncSession = Depends(get_db)):
    """Manually trigger project memory compaction."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.core.project_memory_service import compact_project

    stats = await compact_project(db, project_id)
    await db.commit()
    return stats
