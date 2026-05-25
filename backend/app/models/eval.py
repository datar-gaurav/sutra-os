"""Eval system tables for composed agents.

Hierarchy:
  EvalSuite (one per agent)
    └── EvalCase (input + judging rubric)
  EvalRun (one execution of a suite at a point in time)
    └── EvalResult (per-case outcome)

EvalCase.source distinguishes 'authored' (hand-written), 'synthetic'
(LLM-generated from the graph_spec) and 'trace_mined' (sampled from past
successful runs). Lets the UI render where each case came from and lets the
synthetic generator avoid duplicating existing cases.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, generate_uuid


class EvalSuite(Base, TimestampMixin):
    """A named collection of EvalCases tied to a single ComposedAgent."""

    __tablename__ = "eval_suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    composed_agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("composed_agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalCase(Base, TimestampMixin):
    """A single test case. Multiple expectation types can coexist; the runner
    checks each that is non-null."""

    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM-judge rubric — natural-language description of the pass criterion.
    # Null means deterministic checks only.
    judge_rubric: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Deterministic expectations — any can be null. The runner ANDs together
    # whichever are set.
    expected_guardrail_blocked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    expected_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Provenance: where this case came from. Drives the UI and the generator's
    # dedupe logic.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="authored"
    )  # authored | synthetic | trace_mined

    # Optional category — set by the synthetic generator (capability,
    # adversarial, refusal, tool_sequencing) so the UI can group cases.
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)


class EvalRun(Base):
    """One execution of an EvalSuite at a point in time. Summarises results."""

    __tablename__ = "eval_runs"
    __table_args__ = (
        Index("ix_eval_runs_suite_started", "suite_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_suites.id", ondelete="CASCADE"), nullable=False
    )
    # Snapshot of the agent's draft version at run start — lets us compare
    # pass-rate against the prior published version.
    agent_version_at_run: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalResult(Base):
    """Per-case outcome from a single EvalRun."""

    __tablename__ = "eval_results"
    __table_args__ = (Index("ix_eval_results_run", "run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_cases.id", ondelete="CASCADE"), nullable=False
    )

    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)   # PASS | FAIL | ERROR
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw agent output captured so the UI can render it for debugging.
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    judge_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
