"""LangChain tools for agents to create and manage tasks."""

import json
import logging

from langchain_core.tools import tool
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.task import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


async def _resolve_agent_id(db, value: str) -> str | None:
    """Resolve a value to an agent UUID.

    Accepts a UUID (returned as-is) or a name/role string (looked up by name).
    Returns None if empty or not found, so the FK constraint is never violated.
    """
    if not value:
        return None
    from app.models.agent import Agent
    # If it looks like a UUID, use it directly
    import re
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', value, re.I):
        result = await db.execute(select(Agent).where(Agent.id == value))
        return value if result.scalars().first() else None
    # Otherwise search by name (case-insensitive)
    result = await db.execute(select(Agent).where(Agent.name.ilike(f"%{value}%")))
    agent = result.scalars().first()
    if agent:
        logger.info(f"Resolved agent name '{value}' → {agent.id}")
        return agent.id
    logger.warning(f"Agent '{value}' not found — assigning task without assignee")
    return None


def _make_task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "project_id": task.project_id,
        "parent_task_id": task.parent_task_id,
        "assignee_agent_id": task.assignee_agent_id,
        "assignee_user_id": task.assignee_user_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "notes": task.notes,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def create_task_tools(agent_id: str):
    """Create task management tools bound to a specific agent as the creator."""

    @tool
    async def create_task(
        title: str,
        description: str = "",
        priority: str = "medium",
        project_id: str = "",
        assignee_agent_id: str = "",
        notes: str = "",
    ) -> str:
        """Create a new task. priority must be one of: critical, high, medium, low.
        Optionally assign to a project or another agent by their IDs.
        Returns the created task as JSON."""
        if priority not in [p.value for p in TaskPriority]:
            priority = "medium"
        async with async_session_factory() as db:
            resolved_assignee = await _resolve_agent_id(db, assignee_agent_id)
            task = Task(
                title=title,
                description=description or None,
                status=TaskStatus.todo.value,
                priority=priority,
                project_id=project_id or None,
                assignee_agent_id=resolved_assignee,
                creator_agent_id=agent_id,
                notes=notes or None,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            logger.info(f"Agent {agent_id} created task {task.id}: {title!r}")
            return json.dumps(_make_task_dict(task))

    @tool
    async def list_tasks(
        project_id: str = "",
        status: str = "",
        assignee_agent_id: str = "",
    ) -> str:
        """List tasks, optionally filtered by project_id, status, or assignee_agent_id.
        status must be one of: backlog, todo, in_progress, review, done.
        Returns a JSON array of tasks."""
        from sqlalchemy import select
        async with async_session_factory() as db:
            query = select(Task)
            if project_id:
                query = query.where(Task.project_id == project_id)
            if status:
                query = query.where(Task.status == status)
            if assignee_agent_id:
                query = query.where(Task.assignee_agent_id == assignee_agent_id)
            query = query.order_by(Task.created_at.desc()).limit(50)
            result = await db.execute(query)
            tasks = result.scalars().all()
            return json.dumps([_make_task_dict(t) for t in tasks])

    @tool
    async def update_task(
        task_id: str,
        status: str = "",
        priority: str = "",
        assignee_agent_id: str = "",
        notes: str = "",
    ) -> str:
        """Update an existing task by its ID.
        status must be one of: backlog, todo, in_progress, review, done.
        priority must be one of: critical, high, medium, low.
        Returns the updated task as JSON."""
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            if not task:
                return json.dumps({"error": f"Task {task_id!r} not found"})
            if status and status in [s.value for s in TaskStatus]:
                task.status = status
            if priority and priority in [p.value for p in TaskPriority]:
                task.priority = priority
            if assignee_agent_id:
                task.assignee_agent_id = await _resolve_agent_id(db, assignee_agent_id)
            if notes:
                task.notes = notes
            await db.commit()
            await db.refresh(task)
            logger.info(f"Agent {agent_id} updated task {task_id}")
            return json.dumps(_make_task_dict(task))

    @tool
    async def get_task(task_id: str) -> str:
        """Get full details of a task by its ID. Returns JSON."""
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            if not task:
                return json.dumps({"error": f"Task {task_id!r} not found"})
            return json.dumps(_make_task_dict(task))

    @tool
    async def decompose_task(
        task_id: str,
        subtasks_json: str,
    ) -> str:
        """Break a task into subtasks.
        subtasks_json must be a JSON array of objects with keys:
          title (required), description (optional),
          priority (optional: critical/high/medium/low),
          assignee_agent_id (optional: UUID or name).
        Returns a JSON array of the created subtasks."""
        try:
            subtasks_data = json.loads(subtasks_json)
            if not isinstance(subtasks_data, list):
                return json.dumps({"error": "subtasks_json must be a JSON array"})
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})

        async with async_session_factory() as db:
            parent = await db.get(Task, task_id)
            if not parent:
                return json.dumps({"error": f"Task {task_id!r} not found"})

            created = []
            for s in subtasks_data:
                title = str(s.get("title", "")).strip()
                if not title:
                    continue
                priority = s.get("priority", "medium")
                if priority not in [p.value for p in TaskPriority]:
                    priority = "medium"
                resolved_assignee = await _resolve_agent_id(db, s.get("assignee_agent_id", ""))
                subtask = Task(
                    title=title,
                    description=s.get("description") or None,
                    status=TaskStatus.todo.value,
                    priority=priority,
                    project_id=parent.project_id,
                    parent_task_id=task_id,
                    assignee_agent_id=resolved_assignee,
                    creator_agent_id=agent_id,
                )
                db.add(subtask)
                created.append(subtask)

            await db.commit()
            for subtask in created:
                await db.refresh(subtask)
            logger.info(f"Agent {agent_id} decomposed task {task_id} into {len(created)} subtasks")
            return json.dumps([_make_task_dict(t) for t in created])

    return [create_task, list_tasks, update_task, get_task, decompose_task]


TASK_TOOL_IDS = {"create_task", "list_tasks", "update_task", "get_task", "decompose_task"}
