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
from app.composed_agents.evals.generator import generate_cases
from app.composed_agents.evals.runner import run_case
from app.composed_agents.runner import invalidate, run_once
from app.composed_agents.schemas import GraphSpec, default_graph_spec
from app.composed_agents.state import initial_state
from app.db.session import get_db
from app.models.composed_agent import ComposedAgent
from app.models.eval import EvalCase, EvalResult, EvalRun, EvalSuite
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


# ─── Evals ──────────────────────────────────────────────────────────────────


class EvalSuiteCreate(BaseModel):
    name: str
    description: Optional[str] = None


class EvalSuiteResponse(BaseModel):
    id: str
    composed_agent_id: str
    name: str
    description: Optional[str]

    class Config:
        from_attributes = True


class EvalCaseCreate(BaseModel):
    name: str
    input: str
    judge_rubric: Optional[str] = None
    expected_guardrail_blocked: Optional[bool] = None
    expected_schema: Optional[dict[str, Any]] = None
    category: Optional[str] = None
    source: str = "authored"


class EvalCaseResponse(BaseModel):
    id: str
    suite_id: str
    name: str
    input: str
    judge_rubric: Optional[str]
    expected_guardrail_blocked: Optional[bool]
    expected_schema: Optional[dict[str, Any]]
    category: Optional[str]
    source: str

    class Config:
        from_attributes = True


class EvalGenerateRequest(BaseModel):
    target_count: int = 12
    judge_provider: str = "openai"
    judge_model: str = "gpt-4o-mini"


class EvalRunSummary(BaseModel):
    id: str
    suite_id: str
    status: str
    total: int
    passed: int
    failed: int
    agent_version_at_run: int
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]


class EvalResultRow(BaseModel):
    id: str
    case_id: str
    passed: bool
    verdict: str
    reason: Optional[str]
    output: Optional[str]
    latency_ms: int
    judge_confidence: Optional[float]


@router.get("/{agent_id}/eval-suites", response_model=list[EvalSuiteResponse])
async def list_eval_suites(agent_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(EvalSuite).where(EvalSuite.composed_agent_id == agent_id))
    return res.scalars().all()


@router.post("/{agent_id}/eval-suites", response_model=EvalSuiteResponse, status_code=201)
async def create_eval_suite(
    agent_id: str, data: EvalSuiteCreate, db: AsyncSession = Depends(get_db)
):
    await _get_or_404(db, agent_id)
    suite = EvalSuite(composed_agent_id=agent_id, name=data.name, description=data.description)
    db.add(suite)
    await db.flush()
    await db.refresh(suite)
    return suite


@router.get("/eval-suites/{suite_id}/cases", response_model=list[EvalCaseResponse])
async def list_eval_cases(suite_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(EvalCase).where(EvalCase.suite_id == suite_id).order_by(EvalCase.created_at)
    )
    return res.scalars().all()


@router.post(
    "/eval-suites/{suite_id}/cases",
    response_model=EvalCaseResponse,
    status_code=201,
)
async def create_eval_case(
    suite_id: str, data: EvalCaseCreate, db: AsyncSession = Depends(get_db)
):
    case = EvalCase(
        suite_id=suite_id,
        name=data.name,
        input=data.input,
        judge_rubric=data.judge_rubric,
        expected_guardrail_blocked=data.expected_guardrail_blocked,
        expected_schema=data.expected_schema,
        category=data.category,
        source=data.source,
    )
    db.add(case)
    await db.flush()
    await db.refresh(case)
    return case


@router.delete("/eval-cases/{case_id}", status_code=204)
async def delete_eval_case(case_id: str, db: AsyncSession = Depends(get_db)):
    case = (await db.execute(select(EvalCase).where(EvalCase.id == case_id))).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Case not found")
    await db.delete(case)
    await db.flush()
    return None


@router.post("/eval-suites/{suite_id}/generate", response_model=list[EvalCaseResponse])
async def generate_eval_cases(
    suite_id: str, data: EvalGenerateRequest, db: AsyncSession = Depends(get_db)
):
    """Use the synthetic generator to add new cases to the suite. Existing
    case names are passed in to discourage duplicates."""
    suite = (await db.execute(select(EvalSuite).where(EvalSuite.id == suite_id))).scalar_one_or_none()
    if suite is None:
        raise HTTPException(404, "Suite not found")
    agent = await _get_or_404(db, suite.composed_agent_id)

    existing = (
        await db.execute(select(EvalCase.name).where(EvalCase.suite_id == suite_id))
    ).scalars().all()

    generated = await generate_cases(
        agent.graph_spec,
        existing_case_names=list(existing),
        target_count=data.target_count,
        judge_provider=data.judge_provider,
        judge_model=data.judge_model,
    )

    out: list[EvalCase] = []
    for c in generated:
        row = EvalCase(
            suite_id=suite_id,
            name=c["name"],
            input=c["input"],
            judge_rubric=c.get("judge_rubric"),
            expected_guardrail_blocked=c.get("expected_guardrail_blocked"),
            category=c.get("category"),
            source="synthetic",
        )
        db.add(row)
        out.append(row)
    await db.flush()
    for r in out:
        await db.refresh(r)
    return out


@router.post("/eval-suites/{suite_id}/run", response_model=EvalRunSummary)
async def run_eval_suite(suite_id: str, db: AsyncSession = Depends(get_db)):
    """Run the full suite synchronously. For larger suites, the right
    follow-up is to push this onto Celery — keeping it inline for Phase 3."""
    suite = (await db.execute(select(EvalSuite).where(EvalSuite.id == suite_id))).scalar_one_or_none()
    if suite is None:
        raise HTTPException(404, "Suite not found")
    agent = await _get_or_404(db, suite.composed_agent_id)
    cases = (
        await db.execute(select(EvalCase).where(EvalCase.suite_id == suite_id))
    ).scalars().all()

    run = EvalRun(
        suite_id=suite_id,
        status="running",
        total=len(cases),
        agent_version_at_run=agent.version,
    )
    db.add(run)
    await db.flush()

    passed_count = 0
    failed_count = 0
    error_msg: Optional[str] = None
    try:
        for case in cases:
            outcome = await run_case(
                composed_agent_id=agent.id,
                composed_agent_version=agent.version,
                graph_spec=agent.graph_spec,
                case_id=case.id,
                case_name=case.name,
                case_input=case.input,
                judge_rubric=case.judge_rubric,
                expected_guardrail_blocked=case.expected_guardrail_blocked,
                expected_schema=case.expected_schema,
            )
            db.add(
                EvalResult(
                    run_id=run.id,
                    case_id=case.id,
                    passed=outcome.passed,
                    verdict=outcome.verdict,
                    reason=outcome.reason,
                    output=outcome.output,
                    latency_ms=outcome.latency_ms,
                    judge_confidence=outcome.judge_confidence,
                )
            )
            if outcome.passed:
                passed_count += 1
            else:
                failed_count += 1
    except Exception as e:
        logger.exception("Eval run failed")
        error_msg = str(e)

    run.passed = passed_count
    run.failed = failed_count
    run.status = "completed" if error_msg is None else "error"
    run.error = error_msg
    from datetime import datetime, timezone as _tz
    run.completed_at = datetime.now(_tz.utc)

    await db.flush()
    await db.refresh(run)
    return EvalRunSummary(
        id=run.id,
        suite_id=run.suite_id,
        status=run.status,
        total=run.total,
        passed=run.passed,
        failed=run.failed,
        agent_version_at_run=run.agent_version_at_run,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        error=run.error,
    )


@router.get("/eval-runs/{run_id}", response_model=list[EvalResultRow])
async def list_eval_results(run_id: str, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.created_at)
        )
    ).scalars().all()
    return [
        EvalResultRow(
            id=r.id,
            case_id=r.case_id,
            passed=r.passed,
            verdict=r.verdict,
            reason=r.reason,
            output=r.output,
            latency_ms=r.latency_ms,
            judge_confidence=r.judge_confidence,
        )
        for r in rows
    ]


@router.get("/eval-suites/{suite_id}/runs", response_model=list[EvalRunSummary])
async def list_eval_runs(suite_id: str, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(EvalRun)
            .where(EvalRun.suite_id == suite_id)
            .order_by(EvalRun.started_at.desc())
        )
    ).scalars().all()
    return [
        EvalRunSummary(
            id=r.id,
            suite_id=r.suite_id,
            status=r.status,
            total=r.total,
            passed=r.passed,
            failed=r.failed,
            agent_version_at_run=r.agent_version_at_run,
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            error=r.error,
        )
        for r in rows
    ]


# ─── Misc helpers ───────────────────────────────────────────────────────────


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content) if content is not None else ""
