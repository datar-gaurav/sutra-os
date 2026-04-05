"""Memory management API routes — three-tier memory system."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import MemoryCreate, MemoryResponse
from app.core.memory_service import memory_service
from app.db.session import get_db
from app.models.memory import Memory, MemoryTier, MemoryType

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/", response_model=list[MemoryResponse])
async def list_memories(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    include_shared: bool = Query(False),
    memory_type: MemoryType | None = Query(None),
    tier: str | None = Query(None, description="Filter by tier: core, recall, archival"),
    db: AsyncSession = Depends(get_db),
):
    """List memories for an agent or shared memories, optionally filtered by tier."""
    all_memories = await memory_service.list_all(
        db,
        agent_id=agent_id,
        include_shared=include_shared,
        memory_type=memory_type,
    )
    if tier and tier in ("core", "recall", "archival"):
        all_memories = [m for m in all_memories if m.tier == tier]
    return all_memories


@router.get("/shared", response_model=list[MemoryResponse])
async def list_shared_memories(
    memory_type: MemoryType | None = Query(None),
    tier: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List org-wide shared memories (agent_id=None)."""
    memories = await memory_service.list_all(db, agent_id=None, memory_type=memory_type)
    if tier and tier in ("core", "recall", "archival"):
        memories = [m for m in memories if m.tier == tier]
    return memories


@router.get("/search", response_model=list[MemoryResponse])
async def search_memories(
    q: str = Query(..., min_length=1, description="Search query"),
    agent_id: str | None = Query(None),
    include_shared: bool = Query(True),
    tier: str | None = Query(None, description="Filter by tier"),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across memories."""
    tier_filter = MemoryTier(tier) if tier in ("core", "recall", "archival") else None
    return await memory_service.search(
        db, query=q, agent_id=agent_id, limit=limit,
        include_shared=include_shared, tier=tier_filter,
    )


@router.post("/", response_model=MemoryResponse, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new memory entry."""
    tier = MemoryTier(payload.tier) if payload.tier in ("core", "recall", "archival") else MemoryTier.recall
    memory = await memory_service.save(
        db=db,
        content=payload.content,
        agent_id=payload.agent_id,
        memory_type=payload.type,
        importance_score=payload.importance_score,
        tier=tier,
        source="user",
    )
    return memory


@router.patch("/{memory_id}/promote", response_model=MemoryResponse)
async def promote_memory(
    memory_id: str,
    target_tier: str = Query(..., description="Target tier: core, recall, archival"),
    db: AsyncSession = Depends(get_db),
):
    """Move a memory to a different tier."""
    if target_tier not in ("core", "recall", "archival"):
        raise HTTPException(status_code=400, detail="Invalid tier")
    result = await memory_service.promote(db, memory_id, MemoryTier(target_tier))
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


@router.delete("/clear", status_code=200)
async def clear_memories(
    agent_id: str | None = Query(None, description="Agent ID to clear, or omit for shared memories"),
    db: AsyncSession = Depends(get_db),
):
    """Delete all memories for a given agent (or all shared memories if agent_id is None)."""
    stmt = delete(Memory).where(
        Memory.agent_id == agent_id if agent_id else Memory.agent_id.is_(None)
    )
    result = await db.execute(stmt)
    return {"deleted": result.rowcount}


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a memory."""
    deleted = await memory_service.delete(db, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
