"""Memory tools for agents — self-editing three-tier memory system.

Tools:
  - save_memory: Save new information (defaults to recall tier)
  - search_memory: Semantic search across all tiers
  - memory_update: Rewrite an existing memory's content
  - memory_forget: Soft-delete a memory with a reason
  - memory_promote: Move a memory between tiers (recall→core, core→archival, etc.)
"""

import logging

from langchain_core.tools import tool

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

MEMORY_TOOL_IDS = {"save_memory", "search_memory", "memory_update", "memory_forget", "memory_promote"}


def create_memory_tools(agent_id: str):
    """Return memory tools bound to a specific agent."""

    @tool
    async def save_memory(content: str, importance: float = 0.7, tier: str = "recall") -> str:
        """Save important information to your long-term memory for future conversations.

        Args:
            content: The information to remember (a clear, standalone statement).
            importance: How important this is (0.0 = low, 1.0 = critical). Default 0.7.
            tier: Memory tier — "core" (always in context), "recall" (searchable, default), or "archival" (long-term storage).
        """
        from app.core.memory_service import memory_service
        from app.models.memory import MemoryTier, MemoryType

        if tier not in ("core", "recall", "archival"):
            return f"Invalid tier '{tier}'. Must be one of: core, recall, archival."

        try:
            async with async_session_factory() as db:
                await memory_service.save(
                    db=db,
                    content=content,
                    agent_id=agent_id,
                    memory_type=MemoryType.fact,
                    importance_score=importance,
                    tier=MemoryTier(tier),
                    source="agent",
                )
                await db.commit()
            return f"Saved to {tier} memory: {content[:80]}"
        except Exception as e:
            logger.error(f"save_memory tool failed: {e}")
            return f"Failed to save memory: {e}"

    @tool
    async def search_memory(query: str, tier: str = "") -> str:
        """Search your long-term memory for information relevant to a query.

        Args:
            query: What to search for in your memories.
            tier: Optional tier filter — "core", "recall", or "archival". Empty = search all tiers.
        """
        from app.core.memory_service import memory_service
        from app.models.memory import MemoryTier

        tier_filter = MemoryTier(tier) if tier in ("core", "recall", "archival") else None

        try:
            async with async_session_factory() as db:
                memories = await memory_service.search(
                    db=db, query=query, agent_id=agent_id, limit=5,
                    include_shared=True, tier=tier_filter,
                )
            if not memories:
                return "No relevant memories found."
            lines = []
            for m in memories:
                tier_label = getattr(m, "tier", "recall")
                lines.append(f"- [{m.type}|{tier_label}] (id:{m.id[:8]}) {m.content}")
            return "Relevant memories:\n" + "\n".join(lines)
        except Exception as e:
            logger.error(f"search_memory tool failed: {e}")
            return f"Memory search failed: {e}"

    @tool
    async def memory_update(memory_id: str, new_content: str) -> str:
        """Update the content of an existing memory. Use this when information has changed.

        Args:
            memory_id: The ID of the memory to update (from search_memory results).
            new_content: The updated content to replace the old memory.
        """
        from app.core.memory_service import memory_service

        try:
            async with async_session_factory() as db:
                updated = await memory_service.update_content(db, memory_id, new_content)
                if not updated:
                    return f"Memory {memory_id} not found."
                await db.commit()
            return f"Updated memory {memory_id[:8]}: {new_content[:80]}"
        except Exception as e:
            logger.error(f"memory_update tool failed: {e}")
            return f"Failed to update memory: {e}"

    @tool
    async def memory_forget(memory_id: str, reason: str) -> str:
        """Forget (soft-delete) a memory that is no longer accurate or relevant.

        Args:
            memory_id: The ID of the memory to forget.
            reason: Why this memory should be forgotten (e.g., "outdated", "corrected", "no longer relevant").
        """
        from app.core.memory_service import memory_service

        try:
            async with async_session_factory() as db:
                forgotten = await memory_service.forget(db, memory_id, reason)
                if not forgotten:
                    return f"Memory {memory_id} not found."
                await db.commit()
            return f"Forgot memory {memory_id[:8]}: {reason}"
        except Exception as e:
            logger.error(f"memory_forget tool failed: {e}")
            return f"Failed to forget memory: {e}"

    @tool
    async def memory_promote(memory_id: str, target_tier: str) -> str:
        """Move a memory to a different tier.

        Args:
            memory_id: The ID of the memory to move.
            target_tier: The destination tier — "core" (always in context), "recall" (searchable), or "archival" (long-term storage).
        """
        from app.core.memory_service import memory_service
        from app.models.memory import MemoryTier

        if target_tier not in ("core", "recall", "archival"):
            return f"Invalid tier '{target_tier}'. Must be one of: core, recall, archival."

        try:
            async with async_session_factory() as db:
                promoted = await memory_service.promote(db, memory_id, MemoryTier(target_tier))
                if not promoted:
                    return f"Memory {memory_id} not found."
                await db.commit()
            return f"Moved memory {memory_id[:8]} to {target_tier} tier."
        except Exception as e:
            logger.error(f"memory_promote tool failed: {e}")
            return f"Failed to promote memory: {e}"

    return [save_memory, search_memory, memory_update, memory_forget, memory_promote]
