"""Composed agents API.

Routes:
  GET    /composed-agents/                 list
  POST   /composed-agents/                 create
  GET    /composed-agents/{id}             read
  PUT    /composed-agents/{id}             update graph_spec / metadata
  DELETE /composed-agents/{id}             delete
  POST   /composed-agents/{id}/publish     snapshot draft as published_version
  POST   /composed-agents/{id}/run         one-shot test invocation
  POST   /composed-agents/test-guardrail   test a single guardrail config (no DB)
  GET    /composed-agents/guardrails       list available built-in guardrails
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composed_agents import guardrails as guardrails_pkg
from app.composed_agents.runner import invalidate, run_once
from app.composed_agents.schemas import GraphSpec, default_graph_spec
from app.composed_agents.state import initial_state
from app.db.session import get_db
from app.models.composed_agent import ComposedAgent
from app.models.guardrail_event import GuardrailEvent
from app.models.saved_guardrail import SavedGuardrail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/composed-agents", tags=["Composed Agents"])


# ─── Schemas ────────────────────────────────────────────────────────────────


class ComposedAgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    graph_spec: Optional[dict[str, Any]] = None  # falls back to default_graph_spec()
    state_schema: Optional[dict[str, Any]] = None


class ComposedAgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    graph_spec: Optional[dict[str, Any]] = None
    state_schema: Optional[dict[str, Any]] = None


class ComposedAgentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    graph_spec: dict[str, Any]
    state_schema: dict[str, Any]
    version: int
    published_version: Optional[int]
    is_active: bool
    status: str

    class Config:
        from_attributes = True


class RunRequest(BaseModel):
    input: str = Field(..., description="User message to invoke the agent with.")
    use_published: bool = Field(
        default=False,
        description="If true, use the published snapshot. Otherwise use the draft graph_spec.",
    )


class RunResponse(BaseModel):
    run_id: str                                   # uuid; correlates with /events?run_id=
    output: str                                  # final assistant message text
    rejected: bool                               # true if a guardrail aborted the run
    rejection_reason: Optional[str] = None
    guardrail_results: list[dict[str, Any]]      # per-guardrail trace
    scratchpad: dict[str, Any]


class TestGuardrailRequest(BaseModel):
    type: str                                    # guardrail id, e.g. "pii_redactor"
    config: dict[str, Any] = Field(default_factory=dict)
    input: str                                   # text to test against
    stage: str = "input"                         # for prompt_judge-style guardrails


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, agent_id: str) -> ComposedAgent:
    row = (await db.execute(select(ComposedAgent).where(ComposedAgent.id == agent_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"Composed agent '{agent_id}' not found")
    return row


def _validate_graph_or_422(spec: dict[str, Any]) -> dict[str, Any]:
    """Run pydantic validation and surface errors at the API boundary."""
    try:
        validated = GraphSpec.model_validate(spec)
    except Exception as e:
        raise HTTPException(status_code=422, detail={"graph_spec_error": str(e)})
    return validated.model_dump()


# ─── CRUD ───────────────────────────────────────────────────────────────────


@router.get("/", response_model=list[ComposedAgentResponse])
async def list_composed_agents(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ComposedAgent).where(ComposedAgent.is_archived == False))  # noqa: E712
    return res.scalars().all()


@router.get("/guardrails")
async def list_guardrails():
    """Descriptors for every built-in guardrail — drives the picker UI."""
    return guardrails_pkg.list_all()


@router.post("/", response_model=ComposedAgentResponse, status_code=201)
async def create_composed_agent(data: ComposedAgentCreate, db: AsyncSession = Depends(get_db)):
    spec = data.graph_spec or default_graph_spec()
    spec = _validate_graph_or_422(spec)

    agent = ComposedAgent(
        name=data.name,
        description=data.description,
        graph_spec=spec,
        state_schema=data.state_schema or {},
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=ComposedAgentResponse)
async def get_composed_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_or_404(db, agent_id)


@router.put("/{agent_id}", response_model=ComposedAgentResponse)
async def update_composed_agent(
    agent_id: str, data: ComposedAgentUpdate, db: AsyncSession = Depends(get_db)
):
    agent = await _get_or_404(db, agent_id)

    if data.graph_spec is not None:
        agent.graph_spec = _validate_graph_or_422(data.graph_spec)
        agent.version = (agent.version or 1) + 1
        invalidate(agent.id)  # drop cached compiles for every version
    if data.name is not None:
        agent.name = data.name
    if data.description is not None:
        agent.description = data.description
    if data.state_schema is not None:
        agent.state_schema = data.state_schema

    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_composed_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    agent = await _get_or_404(db, agent_id)
    invalidate(agent.id)
    await db.delete(agent)
    await db.flush()
    return None


@router.post("/{agent_id}/publish", response_model=ComposedAgentResponse)
async def publish_composed_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Snapshot the current draft graph_spec as the published version."""
    agent = await _get_or_404(db, agent_id)
    _validate_graph_or_422(agent.graph_spec)  # re-validate before publish
    agent.published_version = agent.version
    agent.status = "running"
    agent.is_active = True
    await db.flush()
    await db.refresh(agent)
    return agent


# ─── Run / test endpoints ───────────────────────────────────────────────────


@router.post("/{agent_id}/run", response_model=RunResponse)
async def run_composed_agent(
    agent_id: str, data: RunRequest, db: AsyncSession = Depends(get_db)
):
    agent = await _get_or_404(db, agent_id)

    if data.use_published:
        if agent.published_version is None:
            raise HTTPException(409, "Agent has no published version yet.")
        version = agent.published_version
    else:
        version = agent.version

    try:
        run_id, final = await run_once(agent.id, version, agent.graph_spec, data.input)
    except Exception as e:
        logger.exception("Composed agent run failed")
        raise HTTPException(500, f"Run failed: {e}")

    messages = final.get("messages") or []
    final_msg = messages[-1] if messages else None
    output_text = _content_to_text(final_msg.content if final_msg else "")

    guardrail_results = list(final.get("guardrail_results") or [])
    # Persist every verdict to the audit log. Best-effort — log and continue
    # if it fails so a transient DB error doesn't take down the run.
    try:
        for g in guardrail_results:
            db.add(
                GuardrailEvent(
                    composed_agent_id=agent.id,
                    run_id=run_id,
                    guardrail_id=g.guardrail_id,
                    stage=g.stage,
                    action=g.action,
                    passed=g.passed,
                    reason=g.reason,
                    score=g.score,
                    latency_ms=g.latency_ms,
                )
            )
        await db.flush()
    except Exception:
        logger.exception("Failed to persist guardrail events for run %s", run_id)

    rejected = bool(final.get("rejection_message"))

    return RunResponse(
        run_id=run_id,
        output=output_text,
        rejected=rejected,
        rejection_reason=final.get("rejection_message"),
        guardrail_results=[asdict(g) for g in guardrail_results],
        scratchpad=final.get("scratchpad") or {},
    )


@router.get("/{agent_id}/events")
async def list_guardrail_events(
    agent_id: str,
    run_id: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """Audit log of guardrail verdicts for an agent. Filter by run_id to get a
    single invocation's trace; omit for the most-recent events across runs."""
    q = (
        select(GuardrailEvent)
        .where(GuardrailEvent.composed_agent_id == agent_id)
        .order_by(GuardrailEvent.created_at.desc())
        .limit(min(limit, 1000))
    )
    if run_id:
        q = q.where(GuardrailEvent.run_id == run_id)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": e.id,
            "composed_agent_id": e.composed_agent_id,
            "run_id": e.run_id,
            "guardrail_id": e.guardrail_id,
            "stage": e.stage,
            "action": e.action,
            "passed": e.passed,
            "reason": e.reason,
            "score": e.score,
            "latency_ms": e.latency_ms,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.post("/test-guardrail")
async def test_guardrail(data: TestGuardrailRequest):
    """Run a single guardrail against an arbitrary input — drives the live
    Test panel in every guardrail config form. No DB row required."""
    try:
        guard = guardrails_pkg.get(data.type)
    except KeyError as e:
        raise HTTPException(404, str(e))

    state = initial_state(HumanMessage(content=data.input))
    try:
        result = await guard.check(state, data.config or {})
    except Exception as e:
        logger.exception("test-guardrail failed")
        raise HTTPException(500, f"Guardrail check failed: {e}")

    # Re-tag stage so the response matches the caller's expectation.
    result.stage = data.stage  # type: ignore[assignment]
    return asdict(result)


# ─── Saved guardrails (library) ─────────────────────────────────────────────


class SavedGuardrailCreate(BaseModel):
    name: str
    description: Optional[str] = None
    type: str                                       # built-in id or "group"
    config: dict[str, Any] = Field(default_factory=dict)


class SavedGuardrailUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class SavedGuardrailResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    type: str
    config: dict[str, Any]
    version: int

    class Config:
        from_attributes = True


@router.get("/saved-guardrails", response_model=list[SavedGuardrailResponse])
async def list_saved_guardrails(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SavedGuardrail).order_by(SavedGuardrail.name))
    return res.scalars().all()


@router.post("/saved-guardrails", response_model=SavedGuardrailResponse, status_code=201)
async def create_saved_guardrail(
    data: SavedGuardrailCreate, db: AsyncSession = Depends(get_db)
):
    # Validate that the type is a known guardrail (or 'group').
    try:
        guardrails_pkg.get(data.type)
    except KeyError as e:
        raise HTTPException(404, str(e))

    sg = SavedGuardrail(
        name=data.name,
        description=data.description,
        type=data.type,
        config=data.config,
    )
    db.add(sg)
    await db.flush()
    await db.refresh(sg)
    return sg


@router.put("/saved-guardrails/{sg_id}", response_model=SavedGuardrailResponse)
async def update_saved_guardrail(
    sg_id: str, data: SavedGuardrailUpdate, db: AsyncSession = Depends(get_db)
):
    sg = (await db.execute(select(SavedGuardrail).where(SavedGuardrail.id == sg_id))).scalar_one_or_none()
    if sg is None:
        raise HTTPException(404, "Saved guardrail not found")
    bumped = False
    if data.config is not None and data.config != sg.config:
        sg.config = data.config
        bumped = True
    if data.name is not None:
        sg.name = data.name
    if data.description is not None:
        sg.description = data.description
    if bumped:
        sg.version = (sg.version or 1) + 1
    await db.flush()
    await db.refresh(sg)
    return sg


@router.delete("/saved-guardrails/{sg_id}", status_code=204)
async def delete_saved_guardrail(sg_id: str, db: AsyncSession = Depends(get_db)):
    sg = (await db.execute(select(SavedGuardrail).where(SavedGuardrail.id == sg_id))).scalar_one_or_none()
    if sg is None:
        raise HTTPException(404, "Saved guardrail not found")
    await db.delete(sg)
    await db.flush()
    return None


# ─── Misc helpers ───────────────────────────────────────────────────────────


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content) if content is not None else ""
