"""Project memory service — project context injection, switching, decision tracking, and compaction."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.models.memory import Memory, MemoryTier, MemoryType
from app.models.project import Project
from app.models.project_decision import ProjectDecision

logger = logging.getLogger(__name__)


# ── Project Context Injection ────────────────────────────────────────────────


async def get_project_context(db: AsyncSession, project_id: str, query: str) -> str:
    """Build a context string from project info, core memories, decisions, and recall search."""
    project = await db.get(Project, project_id)
    if not project:
        return ""

    sections: list[str] = []

    # 1. Project metadata
    meta = f"Active Project: {project.name}"
    if project.description:
        meta += f"\nDescription: {project.description}"
    meta += f"\nStatus: {project.status}"
    sections.append(meta)

    # 2. Core-tier project memories (always injected)
    core_result = await db.execute(
        select(Memory).where(
            Memory.project_id == project_id,
            Memory.tier == MemoryTier.core.value,
            Memory.is_deleted == False,
        ).order_by(Memory.importance_score.desc()).limit(20)
    )
    core_memories = core_result.scalars().all()
    if core_memories:
        lines = [f"- {m.content}" for m in core_memories]
        sections.append("Project core knowledge:\n" + "\n".join(lines))

    # 3. Semantic search of project recall memories
    try:
        from app.core.memory_service import memory_service
        recall = await _search_project_memories(db, project_id, query, limit=5)
        if recall:
            lines = [f"- [{m.type}] {m.content}" for m in recall]
            sections.append("Relevant project memories:\n" + "\n".join(lines))
    except Exception as e:
        logger.debug(f"Project recall search failed: {e}")

    # 4. Recent high-importance decisions
    decision_result = await db.execute(
        select(ProjectDecision).where(
            ProjectDecision.project_id == project_id,
            ProjectDecision.is_superseded == False,
        ).order_by(ProjectDecision.created_at.desc()).limit(5)
    )
    decisions = decision_result.scalars().all()
    if decisions:
        dec_lines = []
        for d in decisions:
            dec_lines.append(f"- [{d.importance}] {d.title}: {d.decision}")
            if d.data_points:
                for k, v in d.data_points.items():
                    dec_lines.append(f"    {k}: {v}")
        sections.append("Recent project decisions:\n" + "\n".join(dec_lines))

    return "\n\n".join(sections)


async def _search_project_memories(
    db: AsyncSession, project_id: str, query: str, limit: int = 5
) -> list[Memory]:
    """Search recall-tier memories scoped to a project."""
    import math
    from app.core.embeddings import embedding_service
    from app.core.memory_service import _cosine_similarity, _keyword_score

    stmt = (
        select(Memory)
        .where(
            Memory.project_id == project_id,
            Memory.tier.in_([MemoryTier.recall.value, MemoryTier.archival.value]),
            Memory.is_deleted == False,
        )
        .order_by(Memory.decay_score.desc())
        .limit(200)
    )
    result = await db.execute(stmt)
    memories = result.scalars().all()
    if not memories:
        return []

    query_embedding = await embedding_service.aembed(query)

    scored: list[tuple[float, Memory]] = []
    for m in memories:
        if query_embedding and m.embedding:
            mem_emb = json.loads(m.embedding)
            sim = _cosine_similarity(query_embedding, mem_emb)
            score = 0.6 * sim + 0.2 * m.importance_score + 0.2 * m.decay_score
        else:
            score = 0.5 * _keyword_score(query, m.content) + 0.3 * m.importance_score + 0.2 * m.decay_score
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for score, m in scored[:limit] if score > 0.05]

    now = datetime.now(timezone.utc)
    for m in top:
        m.access_count += 1
        m.last_accessed_at = now

    return top


# ── Active Project Tracking ──────────────────────────────────────────────────


async def set_active_project(db: AsyncSession, agent_id: str, project_id: str | None) -> None:
    """Store the active project for an agent in Agent.metadata_."""
    from app.models.agent import Agent
    agent = await db.get(Agent, agent_id)
    if not agent:
        return
    meta = agent.metadata_ or {}
    if project_id:
        meta["active_project_id"] = project_id
    else:
        meta.pop("active_project_id", None)
    agent.metadata_ = meta
    await db.flush()


async def get_active_project(db: AsyncSession, agent_id: str) -> str | None:
    """Return the active project_id for an agent, or None."""
    from app.models.agent import Agent
    agent = await db.get(Agent, agent_id)
    if not agent:
        return None
    meta = agent.metadata_ or {}
    return meta.get("active_project_id")


# ── Project Switch Detection ─────────────────────────────────────────────────


_SWITCH_PATTERNS = [
    re.compile(r"(?:switch|change|move)\s+to\s+project\s+['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
    re.compile(r"(?:work|working)\s+on\s+(?:project\s+)?['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
    re.compile(r"@([\w-]+)", re.IGNORECASE),
]


async def detect_project_switch(db: AsyncSession, message: str) -> str | None:
    """Detect if a message indicates a project switch. Returns project_id or None."""
    # 1. Regex patterns
    for pattern in _SWITCH_PATTERNS:
        match = pattern.search(message)
        if match:
            candidate = match.group(1).strip()
            project_id = await _lookup_project(db, candidate)
            if project_id:
                return project_id

    return None


async def _lookup_project(db: AsyncSession, name_or_slug: str) -> str | None:
    """Case-insensitive lookup by name or slug."""
    result = await db.execute(
        select(Project).where(
            or_(
                func.lower(Project.name) == name_or_slug.lower(),
                func.lower(Project.slug) == name_or_slug.lower(),
            ),
            Project.status != "archived",
        )
    )
    project = result.scalars().first()
    return project.id if project else None


async def handle_project_switch(
    db: AsyncSession, agent_id: str, old_project_id: str | None, new_project_id: str
) -> str:
    """Execute project switch: save checkpoint, update tracking, return summary."""
    from app.core.memory_service import memory_service

    # Save checkpoint in old project
    if old_project_id:
        await memory_service.save(
            db=db,
            content="Conversation paused — switching to another project.",
            agent_id=agent_id,
            memory_type=MemoryType.episode,
            importance_score=0.3,
            tier=MemoryTier.recall,
            source="auto",
        )
        # Tag with project_id
        result = await db.execute(
            select(Memory).order_by(Memory.created_at.desc()).limit(1)
        )
        last_mem = result.scalars().first()
        if last_mem:
            last_mem.project_id = old_project_id

    # Update active project
    await set_active_project(db, agent_id, new_project_id)

    # Update project last_active_at
    project = await db.get(Project, new_project_id)
    if project:
        project.last_active_at = datetime.now(timezone.utc)

    await db.flush()

    # Return context summary
    context = await get_project_context(db, new_project_id, "project overview")
    project_name = project.name if project else "Unknown"
    return f"Switched to project: {project_name}\n\n{context}"


# ── Decision Tracking ────────────────────────────────────────────────────────


async def record_decision(
    db: AsyncSession,
    project_id: str,
    title: str,
    decision: str,
    reasoning: str,
    importance: str = "medium",
    alternatives_considered: list[str] | None = None,
    tags: list[str] | None = None,
    data_points: dict | None = None,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    created_by_user_id: str | None = None,
) -> ProjectDecision:
    """Record a decision and create a corresponding core-tier memory."""
    from app.core.memory_service import memory_service

    dec = ProjectDecision(
        project_id=project_id,
        title=title,
        decision=decision,
        reasoning=reasoning,
        importance=importance,
        alternatives_considered=alternatives_considered,
        tags=tags or [],
        data_points=data_points,
        conversation_id=conversation_id,
        agent_id=agent_id,
        created_by_user_id=created_by_user_id,
    )
    db.add(dec)
    await db.flush()
    await db.refresh(dec)

    # Also save as a core memory if importance >= high
    if importance in ("high", "critical"):
        mem = await memory_service.save(
            db=db,
            content=f"Decision: {title} — {decision}",
            agent_id=agent_id,
            memory_type=MemoryType.fact,
            importance_score=0.9 if importance == "critical" else 0.8,
            tier=MemoryTier.core,
            source="auto",
        )
        mem.project_id = project_id

    # Update project memory_count
    project = await db.get(Project, project_id)
    if project:
        project.memory_count = (project.memory_count or 0) + 1

    await db.flush()
    return dec


async def auto_extract_decisions(
    db: AsyncSession,
    project_id: str,
    agent_id: str,
    user_message: str,
    assistant_response: str,
    llm_provider: str,
    llm_model: str,
    conversation_id: str | None = None,
) -> list[ProjectDecision]:
    """LLM-extract 0-2 decisions from a conversation exchange."""
    if len(assistant_response) < 100:
        return []

    try:
        from app.core.llm_registry import llm_registry
        from langchain_core.messages import HumanMessage

        llm = llm_registry.get_chat_model(provider=llm_provider, model=llm_model, temperature=0.1)

        prompt = (
            "Extract 0-2 important decisions from this exchange. A decision is a choice or commitment "
            "that affects future work. Include the reasoning and any quantitative data points.\n\n"
            f"User: {user_message[:500]}\n"
            f"Assistant: {assistant_response[:1500]}\n\n"
            "Output ONLY a JSON array. Each element: "
            '{"title": "...", "decision": "...", "reasoning": "...", "importance": "low|medium|high|critical", '
            '"data_points": {"key": "value"} or null}\n'
            "If no decisions, return []."
        )

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []

        items = json.loads(match.group())
        saved: list[ProjectDecision] = []
        for item in items[:2]:
            if isinstance(item, dict) and item.get("title") and item.get("decision"):
                dec = await record_decision(
                    db=db,
                    project_id=project_id,
                    title=item["title"][:300],
                    decision=item["decision"],
                    reasoning=item.get("reasoning", ""),
                    importance=item.get("importance", "medium"),
                    data_points=item.get("data_points"),
                    conversation_id=conversation_id,
                    agent_id=agent_id,
                )
                saved.append(dec)
        return saved

    except Exception as e:
        logger.debug(f"Auto-extract decisions failed: {e}")
        return []


# ── Nightly Compaction ────────────────────────────────────────────────────────


async def compact_project(db: AsyncSession, project_id: str) -> dict:
    """Compact a project's memory: decay, consolidate, summarize old conversations."""
    from app.core.memory_service import memory_service, calculate_decay_score

    stats = {"decay_updated": 0, "consolidated": 0, "conversations_summarized": 0}
    now = datetime.now(timezone.utc)

    # 1. Update decay scores on project memories
    result = await db.execute(
        select(Memory).where(
            Memory.project_id == project_id,
            Memory.tier != MemoryTier.core.value,
            Memory.is_deleted == False,
        )
    )
    for m in result.scalars().all():
        new_score = calculate_decay_score(m)
        if abs(new_score - m.decay_score) > 0.01:
            m.decay_score = new_score
            stats["decay_updated"] += 1

    # 2. Consolidate low-decay recall → archival
    from app.core.memory_service import _setting
    consol_threshold = _setting("memory_consolidation_decay_threshold", 0.1)
    consol_age = _setting("memory_consolidation_age_days", 14)
    cutoff = now - timedelta(days=consol_age)

    result = await db.execute(
        select(Memory).where(
            Memory.project_id == project_id,
            Memory.tier == MemoryTier.recall.value,
            Memory.is_deleted == False,
            Memory.decay_score < consol_threshold,
            Memory.created_at < cutoff,
        ).order_by(Memory.created_at)
    )
    candidates = result.scalars().all()

    if len(candidates) >= 2:
        summary = await _summarize_with_figure_safety(candidates)
        if summary:
            mem = await memory_service.save(
                db=db,
                content=summary,
                agent_id=None,
                memory_type=MemoryType.episode,
                importance_score=0.4,
                tier=MemoryTier.archival,
                source="consolidation",
            )
            mem.project_id = project_id
            for m in candidates:
                m.is_deleted = True
                m.deleted_reason = "project_compacted"
            stats["consolidated"] = len(candidates)
    elif len(candidates) == 1:
        candidates[0].tier = MemoryTier.archival.value
        stats["consolidated"] = 1

    # 3. Summarize old conversations (>7 days, >50 messages)
    conv_cutoff = now - timedelta(days=7)
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.created_at < conv_cutoff,
        )
    )
    for conv in conv_result.scalars().all():
        msg_result = await db.execute(
            select(func.count(Message.id)).where(Message.conversation_id == conv.id)
        )
        msg_count = msg_result.scalar() or 0
        if msg_count > 50:
            # Summarize to archival memory
            msg_sample = await db.execute(
                select(Message).where(Message.conversation_id == conv.id)
                .order_by(Message.created_at).limit(20)
            )
            msgs = msg_sample.scalars().all()
            content = "\n".join(f"[{m.role}] {m.content[:200]}" for m in msgs)
            summary = await _summarize_conversation(content, conv.title)
            if summary:
                mem = await memory_service.save(
                    db=db,
                    content=summary,
                    agent_id=None,
                    memory_type=MemoryType.episode,
                    importance_score=0.3,
                    tier=MemoryTier.archival,
                    source="consolidation",
                )
                mem.project_id = project_id
                stats["conversations_summarized"] += 1

    # Update compaction summary
    project = await db.get(Project, project_id)
    if project:
        project.compaction_summary = (
            f"Last compaction: {now.isoformat()} — "
            f"{stats['decay_updated']} decay updates, "
            f"{stats['consolidated']} memories consolidated, "
            f"{stats['conversations_summarized']} conversations summarized"
        )

    await db.flush()
    logger.info(f"Project {project_id} compaction: {stats}")
    return stats


async def compact_all_projects(db: AsyncSession) -> dict:
    """Compact all active projects."""
    result = await db.execute(
        select(Project).where(Project.status == "active")
    )
    projects = result.scalars().all()
    total_stats = {"projects": 0, "total_consolidated": 0}
    for project in projects:
        try:
            stats = await compact_project(db, project.id)
            total_stats["projects"] += 1
            total_stats["total_consolidated"] += stats.get("consolidated", 0)
        except Exception as e:
            logger.error(f"Compaction failed for project {project.id}: {e}")
    return total_stats


async def _summarize_with_figure_safety(memories: list[Memory]) -> str | None:
    """Summarize memories, preserving numbers/figures."""
    try:
        from app.core.llm_registry import llm_registry
        from langchain_core.messages import HumanMessage

        content_list = "\n".join(f"- [{m.type}] {m.content}" for m in memories[:20])
        prompt = (
            "Consolidate these project memories into a concise summary (2-4 sentences). "
            "IMPORTANT: Preserve all numbers, dollar amounts, percentages, dates, and quantitative "
            "data exactly as stated. Drop redundancies but keep key decisions and facts.\n\n"
            f"{content_list}"
        )

        llm = llm_registry.get_chat_model(provider="groq", model="llama-3.1-8b-instant")
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip() if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.debug(f"Figure-safe summarization failed: {e}")
        return " | ".join(m.content for m in memories[:5])


async def _summarize_conversation(content: str, title: str | None) -> str | None:
    """Summarize a conversation into a compact memory."""
    try:
        from app.core.llm_registry import llm_registry
        from langchain_core.messages import HumanMessage

        prompt = (
            f"Summarize this conversation{f' ({title})' if title else ''} in 2-3 sentences. "
            "Focus on decisions, outcomes, and key information.\n\n"
            f"{content[:3000]}"
        )

        llm = llm_registry.get_chat_model(provider="groq", model="llama-3.1-8b-instant")
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip() if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.debug(f"Conversation summarization failed: {e}")
        return None
