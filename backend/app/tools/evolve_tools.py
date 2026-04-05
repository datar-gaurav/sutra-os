"""Evolve agent tools — platform stats, error patterns, and suggestion submission."""

import json
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EVOLVE_TOOL_IDS = {
    "evolve_get_platform_stats",
    "evolve_get_error_patterns",
    "evolve_get_system_errors",
    "evolve_submit_suggestion",
}


class PlatformStatsInput(BaseModel):
    hours: int = Field(24, description="Look-back window in hours (default 24)")


class ErrorPatternsInput(BaseModel):
    hours: int = Field(24, description="Look-back window in hours (default 24)")
    limit: int = Field(20, description="Max error groups to return")


class SystemErrorsInput(BaseModel):
    hours: int = Field(24, description="Look-back window in hours (default 24)")
    severity: str = Field("", description="Filter by severity: debug|info|warning|error|critical (empty = all)")
    source: str = Field("", description="Filter by source: route|background_task|startup|scheduler (empty = all)")
    limit: int = Field(50, description="Max records to return")


class SubmitSuggestionInput(BaseModel):
    title: str = Field(..., description="Short title for the suggestion")
    description: str = Field(..., description="Detailed description of the improvement")
    category: str = Field("feature_idea", description="platform_health|error_pattern|performance|competitor_gap|feature_idea")
    priority: str = Field("medium", description="low|medium|high|critical")
    evidence: str = Field("{}", description="JSON string with supporting data")
    action_type: str = Field("task", description="forge_request|task|goal")
    action_config: str = Field("{}", description="JSON string with action configuration")


async def _get_platform_stats(hours: int = 24) -> str:
    """Query DB for platform health stats over the given time window."""
    try:
        from app.db.session import async_session_factory
        from app.models.agent import Agent
        from app.models.trace import ExecutionTrace
        from sqlalchemy import func, select

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with async_session_factory() as db:
            # Agent counts
            agent_result = await db.execute(select(func.count(Agent.id)))
            total_agents = agent_result.scalar() or 0

            active_result = await db.execute(
                select(func.count(Agent.id)).where(Agent.status == "running")
            )
            active_agents = active_result.scalar() or 0

            # Trace stats
            trace_count_result = await db.execute(
                select(func.count(ExecutionTrace.id)).where(ExecutionTrace.created_at >= cutoff)
            )
            trace_count = trace_count_result.scalar() or 0

            error_count_result = await db.execute(
                select(func.count(ExecutionTrace.id)).where(
                    ExecutionTrace.created_at >= cutoff,
                    ExecutionTrace.had_error == True,
                )
            )
            error_count = error_count_result.scalar() or 0

            avg_latency_result = await db.execute(
                select(func.avg(ExecutionTrace.latency_ms)).where(
                    ExecutionTrace.created_at >= cutoff
                )
            )
            avg_latency = avg_latency_result.scalar() or 0

            # Request usage count
            try:
                from app.models.usage import ModelUsage
                usage_result = await db.execute(
                    select(func.sum(ModelUsage.request_count)).where(
                        ModelUsage.created_at >= cutoff
                    )
                )
                total_requests = usage_result.scalar() or 0
            except Exception:
                total_requests = 0

        error_rate = (error_count / trace_count * 100) if trace_count > 0 else 0

        stats = {
            "window_hours": hours,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "total_invocations": trace_count,
            "error_count": error_count,
            "error_rate_pct": round(error_rate, 2),
            "avg_latency_ms": round(float(avg_latency), 1),
            "total_llm_requests": total_requests,
        }
        return json.dumps(stats, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _get_error_patterns(hours: int = 24, limit: int = 20) -> str:
    """Get top error patterns from ExecutionTrace grouped by agent/tool."""
    try:
        from app.db.session import async_session_factory
        from app.models.trace import ExecutionTrace
        from app.models.agent import Agent
        from sqlalchemy import func, select

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with async_session_factory() as db:
            result = await db.execute(
                select(
                    ExecutionTrace.agent_id,
                    func.count(ExecutionTrace.id).label("error_count"),
                    func.avg(ExecutionTrace.latency_ms).label("avg_latency"),
                ).where(
                    ExecutionTrace.created_at >= cutoff,
                    ExecutionTrace.had_error == True,
                ).group_by(ExecutionTrace.agent_id)
                .order_by(func.count(ExecutionTrace.id).desc())
                .limit(limit)
            )
            rows = result.all()

            patterns = []
            for row in rows:
                agent_name = "unknown"
                if row.agent_id:
                    agent = await db.get(Agent, row.agent_id)
                    if agent:
                        agent_name = agent.name

                # Get sample errors
                sample_result = await db.execute(
                    select(ExecutionTrace.error_message).where(
                        ExecutionTrace.agent_id == row.agent_id,
                        ExecutionTrace.had_error == True,
                        ExecutionTrace.created_at >= cutoff,
                    ).limit(3)
                )
                samples = [r[0][:200] if r[0] else "" for r in sample_result.all()]

                patterns.append({
                    "agent_id": row.agent_id,
                    "agent_name": agent_name,
                    "error_count": row.error_count,
                    "avg_latency_ms": round(float(row.avg_latency or 0), 1),
                    "sample_errors": samples,
                })

        return json.dumps(patterns, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _get_system_errors(hours: int = 24, severity: str = "", source: str = "", limit: int = 50) -> str:
    """Query the error_logs table for non-agent platform errors."""
    try:
        from app.db.session import async_session_factory
        from app.models.error_log import ErrorLog
        from sqlalchemy import func, select

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with async_session_factory() as db:
            q = select(ErrorLog).where(ErrorLog.created_at >= cutoff)
            if severity:
                q = q.where(ErrorLog.severity == severity)
            if source:
                q = q.where(ErrorLog.source == source)
            q = q.order_by(ErrorLog.created_at.desc()).limit(limit)

            result = await db.execute(q)
            rows = result.scalars().all()

            # Summary counts by source and severity
            summary_q = (
                select(
                    ErrorLog.source,
                    ErrorLog.severity,
                    func.count(ErrorLog.id).label("count"),
                )
                .where(ErrorLog.created_at >= cutoff)
                .group_by(ErrorLog.source, ErrorLog.severity)
                .order_by(func.count(ErrorLog.id).desc())
            )
            summary_result = await db.execute(summary_q)
            summary = [
                {"source": r.source, "severity": r.severity, "count": r.count}
                for r in summary_result.all()
            ]

            records = [
                {
                    "id": r.id,
                    "source": r.source,
                    "error_type": r.error_type,
                    "severity": r.severity,
                    "message": r.message,
                    "traceback": r.traceback[:500] if r.traceback else None,
                    "request_path": r.request_path,
                    "agent_id": r.agent_id,
                    "context": r.context,
                    "resolved": r.resolved,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]

        return json.dumps({"window_hours": hours, "summary": summary, "errors": records}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def _submit_suggestion(
    title: str,
    description: str,
    category: str = "feature_idea",
    priority: str = "medium",
    evidence: str = "{}",
    action_type: str = "task",
    action_config: str = "{}",
) -> str:
    """Create an EvolveSuggestion + ApprovalRequest pair."""
    try:
        from app.db.session import async_session_factory
        from app.models.evolve import EvolveSuggestion, SuggestionStatus
        from app.models.approval_request import ApprovalRequest

        evidence_data = json.loads(evidence) if evidence else {}
        action_config_data = json.loads(action_config) if action_config else {}

        async with async_session_factory() as db:
            # Find evolve agent
            from app.models.agent import Agent
            from sqlalchemy import select
            result = await db.execute(select(Agent).where(Agent.name == "Evolve"))
            evolve_agent = result.scalars().first()
            evolve_agent_id = evolve_agent.id if evolve_agent else None

            # Create suggestion
            suggestion = EvolveSuggestion(
                evolve_agent_id=evolve_agent_id,
                category=category,
                source="manual",
                title=title,
                description=description,
                evidence=evidence_data,
                priority=priority,
                status=SuggestionStatus.pending_approval.value,
                action_type=action_type,
                action_config=action_config_data,
            )
            db.add(suggestion)
            await db.flush()
            await db.refresh(suggestion)

            # Create approval request
            approval = ApprovalRequest(
                title=f"[Evolve] {title}",
                description=description,
                category="evolve",
                risk_level="medium" if priority in ("low", "medium") else "high",
                context={"suggestion_id": suggestion.id, "evidence": evidence_data},
                action_payload={
                    "type": "evolve_action",
                    "suggestion_id": suggestion.id,
                    "action_type": action_type,
                    "action_config": action_config_data,
                },
                requester_agent_id=evolve_agent_id,
            )
            db.add(approval)
            await db.flush()
            await db.refresh(approval)

            suggestion.approval_request_id = approval.id
            await db.commit()

            return json.dumps({
                "status": "created",
                "suggestion_id": suggestion.id,
                "approval_id": approval.id,
                "message": f"Suggestion '{title}' created and pending human approval.",
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_evolve_tools() -> list[StructuredTool]:
    """Create LangChain tools for the Evolve agent."""
    return [
        StructuredTool.from_function(
            coroutine=_get_platform_stats,
            name="evolve_get_platform_stats",
            description="Get platform health statistics: agent count, invocation count, error rate, avg latency, token usage over the last N hours.",
            args_schema=PlatformStatsInput,
        ),
        StructuredTool.from_function(
            coroutine=_get_error_patterns,
            name="evolve_get_error_patterns",
            description="Get top error patterns from execution traces grouped by agent, with sample error messages.",
            args_schema=ErrorPatternsInput,
        ),
        StructuredTool.from_function(
            coroutine=_get_system_errors,
            name="evolve_get_system_errors",
            description=(
                "Query the platform error log for non-agent errors: unhandled route exceptions, "
                "background task failures, startup errors, and scheduler errors. "
                "Grouped by source and severity. Use this alongside evolve_get_error_patterns "
                "to get a complete picture of platform health."
            ),
            args_schema=SystemErrorsInput,
        ),
        StructuredTool.from_function(
            coroutine=_submit_suggestion,
            name="evolve_submit_suggestion",
            description="Submit an improvement suggestion for the platform. Creates a suggestion record and an approval request for human review. Never executes directly.",
            args_schema=SubmitSuggestionInput,
        ),
    ]
