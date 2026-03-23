"""Memory service — three-tier CRUD, semantic search, decay, consolidation, and auto-extraction."""

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import embedding_service
from app.models.memory import Memory, MemoryTier, MemoryType

logger = logging.getLogger(__name__)

# ── Settings helpers ─────────────────────────────────────────────────────────

def _setting(key: str, fallback):
    """Read a memory setting from runtime config, with fallback."""
    try:
        from app.core.system_settings import sys_settings
        val = sys_settings.get(key)
        return val if val is not None else fallback
    except Exception:
        return fallback


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _keyword_score(query: str, content: str) -> float:
    qwords = set(query.lower().split())
    cwords = set(content.lower().split())
    if not qwords:
        return 0.0
    return len(qwords & cwords) / len(qwords)


def calculate_decay_score(memory: Memory) -> float:
    """
    Score = base_importance * recency_factor * frequency_factor

    recency_factor: exponential decay, half-life = 7 days
    frequency_factor: log(access_count + 1)

    Core memories always have decay_score = 1.0.
    """
    if memory.tier == MemoryTier.core.value:
        return 1.0

    now = datetime.now(timezone.utc)
    last_access = memory.last_accessed_at or memory.created_at
    if last_access.tzinfo is None:
        last_access = last_access.replace(tzinfo=timezone.utc)

    days_since = max((now - last_access).total_seconds() / 86400, 0)
    half_life = _setting("memory_decay_half_life_days", 7)
    recency = 0.5 ** (days_since / half_life)
    frequency = math.log10(memory.access_count + 1) + 0.1  # min 0.1
    frequency = min(frequency, 2.0)  # cap at 2.0

    return memory.importance_score * recency * frequency


# ── Memory Service ───────────────────────────────────────────────────────────

class MemoryService:

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def save(
        self,
        db: AsyncSession,
        content: str,
        agent_id: str | None = None,
        memory_type: MemoryType = MemoryType.fact,
        importance_score: float = 0.5,
        tier: MemoryTier = MemoryTier.recall,
        source: str = "auto",
        project_id: str | None = None,
    ) -> Memory:
        embedding = await embedding_service.aembed(content)
        memory = Memory(
            agent_id=agent_id,
            type=memory_type,
            content=content,
            embedding=json.dumps(embedding) if embedding else None,
            importance_score=max(0.0, min(1.0, importance_score)),
            tier=tier.value if isinstance(tier, MemoryTier) else tier,
            source=source,
            decay_score=1.0,
            project_id=project_id,
        )
        db.add(memory)
        await db.flush()
        await db.refresh(memory)
        logger.debug(f"Saved {tier} memory ({memory_type}) for agent={agent_id} project={project_id}: {content[:60]}")
        return memory

    async def update_content(
        self, db: AsyncSession, memory_id: str, new_content: str
    ) -> Memory | None:
        """Update a memory's content and re-embed."""
        memory = await db.get(Memory, memory_id)
        if not memory or memory.is_deleted:
            return None
        memory.content = new_content
        embedding = await embedding_service.aembed(new_content)
        memory.embedding = json.dumps(embedding) if embedding else None
        memory.decay_score = calculate_decay_score(memory)
        await db.flush()
        return memory

    async def forget(
        self, db: AsyncSession, memory_id: str, reason: str = "agent_requested"
    ) -> bool:
        """Soft-delete a memory with a reason."""
        memory = await db.get(Memory, memory_id)
        if not memory:
            return False
        memory.is_deleted = True
        memory.deleted_reason = reason
        await db.flush()
        logger.debug(f"Forgot memory {memory_id}: {reason}")
        return True

    async def promote(
        self, db: AsyncSession, memory_id: str, target_tier: MemoryTier
    ) -> Memory | None:
        """Move a memory to a different tier."""
        memory = await db.get(Memory, memory_id)
        if not memory or memory.is_deleted:
            return None
        old_tier = memory.tier
        memory.tier = target_tier.value if isinstance(target_tier, MemoryTier) else target_tier
        if target_tier == MemoryTier.core:
            memory.decay_score = 1.0  # Core memories don't decay
        else:
            memory.decay_score = calculate_decay_score(memory)
        logger.debug(f"Promoted memory {memory_id}: {old_tier} → {memory.tier}")
        await db.flush()
        return memory

    async def delete(self, db: AsyncSession, memory_id: str) -> bool:
        memory = await db.get(Memory, memory_id)
        if not memory:
            return False
        await db.delete(memory)
        return True

    # ── Tier-based retrieval ─────────────────────────────────────────────────

    async def get_core_memories(
        self, db: AsyncSession, agent_id: str
    ) -> list[Memory]:
        """Get all core (Tier 1) memories for an agent. Always injected into context."""
        result = await db.execute(
            select(Memory).where(
                Memory.agent_id == agent_id,
                Memory.tier == MemoryTier.core.value,
                Memory.is_deleted == False,
            ).order_by(Memory.importance_score.desc())
        )
        return result.scalars().all()

    async def get_by_tier(
        self, db: AsyncSession, agent_id: str, tier: MemoryTier, limit: int = 50
    ) -> list[Memory]:
        """Get memories for an agent in a specific tier."""
        result = await db.execute(
            select(Memory).where(
                Memory.agent_id == agent_id,
                Memory.tier == tier.value,
                Memory.is_deleted == False,
            ).order_by(Memory.decay_score.desc()).limit(limit)
        )
        return result.scalars().all()

    # ── Search ───────────────────────────────────────────────────────────────

    async def search(
        self,
        db: AsyncSession,
        query: str,
        agent_id: str | None = None,
        limit: int = 5,
        include_shared: bool = True,
        tier: MemoryTier | None = None,
        project_id: str | None = None,
    ) -> list[Memory]:
        """Return top-N memories ranked by semantic similarity + importance + decay."""
        stmt = select(Memory).where(Memory.is_deleted == False)

        if agent_id:
            if include_shared:
                stmt = stmt.where(
                    or_(Memory.agent_id == agent_id, Memory.agent_id.is_(None))
                )
            else:
                stmt = stmt.where(Memory.agent_id == agent_id)
        else:
            stmt = stmt.where(Memory.agent_id.is_(None))

        # Filter by project (None = unscoped memories only)
        if project_id:
            stmt = stmt.where(
                or_(Memory.project_id == project_id, Memory.project_id.is_(None))
            )
        else:
            stmt = stmt.where(Memory.project_id.is_(None))

        if tier:
            tier_val = tier.value if isinstance(tier, MemoryTier) else tier
            stmt = stmt.where(Memory.tier == tier_val)

        # Pre-filter: only load recent/high-value memories (cap at 200 to avoid full-table scan)
        stmt = stmt.order_by(Memory.decay_score.desc()).limit(200)

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
                # Blend: 60% similarity + 20% importance + 20% decay
                score = 0.6 * sim + 0.2 * m.importance_score + 0.2 * m.decay_score
            else:
                score = 0.5 * _keyword_score(query, m.content) + 0.3 * m.importance_score + 0.2 * m.decay_score
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [m for score, m in scored[:limit] if score > 0.05]

        # Update access stats
        now = datetime.now(timezone.utc)
        for m in top:
            m.access_count += 1
            m.last_accessed_at = now
            m.decay_score = calculate_decay_score(m)

        return top

    # ── Listing ──────────────────────────────────────────────────────────────

    async def list_all(
        self,
        db: AsyncSession,
        agent_id: str | None = None,
        include_shared: bool = False,
        memory_type: MemoryType | None = None,
        tier: MemoryTier | None = None,
        limit: int = 200,
    ) -> list[Memory]:
        stmt = select(Memory).where(
            Memory.is_deleted == False
        ).order_by(Memory.created_at.desc()).limit(limit)

        if agent_id is not None:
            if include_shared:
                stmt = stmt.where(
                    or_(Memory.agent_id == agent_id, Memory.agent_id.is_(None))
                )
            else:
                stmt = stmt.where(Memory.agent_id == agent_id)
        else:
            stmt = stmt.where(Memory.agent_id.is_(None))

        if memory_type:
            stmt = stmt.where(Memory.type == memory_type)
        if tier:
            tier_val = tier.value if isinstance(tier, MemoryTier) else tier
            stmt = stmt.where(Memory.tier == tier_val)

        result = await db.execute(stmt)
        return result.scalars().all()

    # ── Decay ────────────────────────────────────────────────────────────────

    async def update_decay_scores(self, db: AsyncSession) -> int:
        """Recalculate decay scores for all non-core memories. Returns count updated."""
        result = await db.execute(
            select(Memory).where(
                Memory.tier != MemoryTier.core.value,
                Memory.is_deleted == False,
            )
        )
        memories = result.scalars().all()
        updated = 0
        for m in memories:
            new_score = calculate_decay_score(m)
            if abs(new_score - m.decay_score) > 0.01:
                m.decay_score = new_score
                updated += 1
        if updated:
            await db.flush()
        return updated

    # ── Consolidation ────────────────────────────────────────────────────────

    async def consolidate(self, db: AsyncSession) -> dict:
        """
        Consolidation pipeline:
        1. Find recall memories with low decay score + old age → summarize → move to archival
        2. Delete archival memories with very low decay score + very old
        """
        now = datetime.now(timezone.utc)
        stats = {"consolidated": 0, "deleted": 0, "decay_updated": 0}

        # Step 0: Update all decay scores
        stats["decay_updated"] = await self.update_decay_scores(db)

        # Step 1: Find consolidation candidates (recall tier, low decay, old)
        consol_age = _setting("memory_consolidation_age_days", 14)
        consol_threshold = _setting("memory_consolidation_decay_threshold", 0.1)
        cutoff = now - timedelta(days=consol_age)
        result = await db.execute(
            select(Memory).where(
                Memory.tier == MemoryTier.recall.value,
                Memory.is_deleted == False,
                Memory.decay_score < consol_threshold,
                Memory.created_at < cutoff,
            ).order_by(Memory.agent_id, Memory.created_at)
        )
        candidates = result.scalars().all()

        # Group by agent_id
        by_agent: dict[str | None, list[Memory]] = {}
        for m in candidates:
            by_agent.setdefault(m.agent_id, []).append(m)

        for agent_id, memories in by_agent.items():
            if len(memories) < 2:
                # Single memory — just move to archival
                for m in memories:
                    m.tier = MemoryTier.archival.value
                    stats["consolidated"] += 1
                continue

            # Summarize the batch into a single archival memory
            summary = await self._summarize_memories(memories)
            if summary:
                source_ids = [m.id for m in memories]
                await self.save(
                    db=db,
                    content=summary,
                    agent_id=agent_id,
                    memory_type=MemoryType.episode,
                    importance_score=0.4,
                    tier=MemoryTier.archival,
                    source="consolidation",
                )
                # Soft-delete originals
                for m in memories:
                    m.is_deleted = True
                    m.deleted_reason = "consolidated"
                stats["consolidated"] += len(memories)

        # Step 2: Delete very old archival memories with near-zero decay
        arch_delete_days = _setting("memory_archival_delete_days", 90)
        archive_cutoff = now - timedelta(days=arch_delete_days)
        delete_result = await db.execute(
            select(Memory).where(
                Memory.tier == MemoryTier.archival.value,
                Memory.is_deleted == False,
                Memory.decay_score < 0.01,
                Memory.created_at < archive_cutoff,
            )
        )
        for m in delete_result.scalars().all():
            m.is_deleted = True
            m.deleted_reason = "expired"
            stats["deleted"] += 1

        await db.flush()
        logger.info(f"Memory consolidation: {stats}")
        return stats

    async def _summarize_memories(self, memories: list[Memory]) -> str | None:
        """LLM-summarize a batch of memories into a single consolidated memory."""
        try:
            from app.core.llm_registry import llm_registry
            from langchain_core.messages import HumanMessage

            content_list = "\n".join(f"- [{m.type}] {m.content}" for m in memories[:20])
            prompt = (
                "Consolidate these memories into a single concise summary (2-4 sentences). "
                "Preserve key facts, decisions, and outcomes. Drop redundancies.\n\n"
                f"{content_list}"
            )

            llm = llm_registry.get_chat_model(provider="groq", model="llama-3.1-8b-instant")
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return response.content.strip() if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.debug(f"Memory consolidation summarization failed: {e}")
            # Fallback: just concatenate
            contents = [m.content for m in memories[:5]]
            return " | ".join(contents)

    # ── Auto-extract ─────────────────────────────────────────────────────────

    async def auto_extract(
        self,
        db: AsyncSession,
        agent_id: str,
        user_message: str,
        assistant_response: str,
        llm_provider: str,
        llm_model: str,
    ) -> list[Memory]:
        """Extract key facts from a conversation exchange using the LLM."""
        if len(assistant_response) < 80:
            return []

        try:
            from app.core.llm_registry import llm_registry
            from langchain_core.messages import HumanMessage

            llm = llm_registry.get_chat_model(
                provider=llm_provider, model=llm_model, temperature=0.1
            )

            prompt = (
                "Extract 0–2 important facts, preferences, or decisions from this exchange "
                "worth remembering for future conversations.\n\n"
                f"User: {user_message[:500]}\n"
                f"Assistant: {assistant_response[:1000]}\n\n"
                "Output ONLY a JSON array of strings. If nothing important, return [].\n"
                'Example: ["User prefers concise answers", "Project deadline is April 2025"]'
            )

            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content.strip()

            match = re.search(r"\[.*?\]", raw, re.DOTALL)
            if not match:
                return []

            facts: list = json.loads(match.group())
            saved = []
            for fact in facts[:2]:
                if isinstance(fact, str) and len(fact) > 15:
                    m = await self.save(
                        db=db,
                        content=fact,
                        agent_id=agent_id,
                        memory_type=MemoryType.episode,
                        importance_score=0.55,
                        tier=MemoryTier.recall,
                        source="auto",
                    )
                    saved.append(m)
            return saved

        except Exception as e:
            logger.debug(f"Auto-extract memories failed: {e}")
            return []

    # ── Cross-agent knowledge sharing ────────────────────────────────────────

    async def share_knowledge(
        self, db: AsyncSession, source_agent_id: str, content: str,
        target_agent_ids: list[str] | None = None,
    ) -> int:
        """
        Share a piece of knowledge from one agent to others.
        If target_agent_ids is None, shares org-wide (agent_id=None).
        """
        shared = 0
        if target_agent_ids is None:
            # Org-wide shared memory
            await self.save(
                db=db, content=content, agent_id=None,
                memory_type=MemoryType.fact, importance_score=0.6,
                tier=MemoryTier.recall, source="shared",
            )
            shared = 1
        else:
            for target_id in target_agent_ids:
                if target_id != source_agent_id:
                    await self.save(
                        db=db, content=content, agent_id=target_id,
                        memory_type=MemoryType.fact, importance_score=0.5,
                        tier=MemoryTier.recall, source="shared",
                    )
                    shared += 1
        return shared


memory_service = MemoryService()
