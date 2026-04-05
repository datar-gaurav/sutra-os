"""Execution traces API — retrieve agent invocation history."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.trace import ExecutionTrace

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/agent/{agent_id}")
async def list_agent_traces(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List execution traces for a specific agent, newest first."""
    result = await db.execute(
        select(ExecutionTrace)
        .where(ExecutionTrace.agent_id == agent_id)
        .order_by(ExecutionTrace.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    traces = result.scalars().all()
    return [_trace_to_dict(t) for t in traces]


@router.get("/{trace_id}")
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single execution trace by ID."""
    trace = await db.get(ExecutionTrace, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return _trace_to_dict(trace)


def _trace_to_dict(t: ExecutionTrace) -> dict:
    import json
    return {
        "id": t.id,
        "agent_id": t.agent_id,
        "conversation_id": t.conversation_id,
        "request_id": t.request_id,
        "input_message": t.input_message,
        "output_message": t.output_message,
        "tool_calls": json.loads(t.tool_calls) if t.tool_calls else [],
        "latency_ms": t.latency_ms,
        "had_error": t.had_error,
        "error_message": t.error_message,
        "created_at": str(t.created_at),
    }
