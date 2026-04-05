"""Analytics & Reporting routes — Phase 4.2.

Provides executive KPIs, agent scorecards, team analytics, and multi-series
trend data. All data is derived from existing tables — no new models needed.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_calculator import compute_cost_usd, get_pricing
from app.db.session import get_db
from app.models.agent import Agent
from app.models.approval_request import ApprovalRequest
from app.models.budget import Budget
from app.models.discussion import Discussion
from app.models.task import Task, TaskStatus
from app.models.team import Team
from app.models.trace import ExecutionTrace

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _period_since(period: str) -> datetime | None:
    """Return UTC start-of-period datetime, or None for 'all'."""
    now = datetime.now(timezone.utc)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # "all"


async def _compute_traces_cost(traces: list, agents: dict, db: AsyncSession) -> float:
    """Sum cost across traces using agent pricing."""
    total = 0.0
    for trace in traces:
        if not trace.total_tokens:
            continue
        agent = agents.get(trace.agent_id)
        provider = agent.llm_provider if agent else "*"
        model = agent.llm_model if agent else "*"
        inp_rate, out_rate = await get_pricing(db, provider, model)
        total += compute_cost_usd(trace.total_tokens, inp_rate, out_rate)
    return total


# ─── Executive Summary ────────────────────────────────────────────────────────

@router.get("/executive")
async def executive_summary(
    period: str = "month",
    db: AsyncSession = Depends(get_db),
):
    """High-level KPIs for the executive dashboard."""
    since = _period_since(period)

    # ── Agents ────────────────────────────────────────────────────────────────
    agents_result = await db.execute(select(Agent))
    all_agents = {a.id: a for a in agents_result.scalars().all()}
    active_agents = sum(1 for a in all_agents.values() if a.status == "running")

    # ── Tasks ─────────────────────────────────────────────────────────────────
    task_q = select(Task)
    if since:
        task_q = task_q.where(Task.created_at >= since)
    all_tasks = (await db.execute(task_q)).scalars().all()

    tasks_created = len(all_tasks)
    tasks_completed = sum(1 for t in all_tasks if t.status == TaskStatus.done.value)
    tasks_in_progress = sum(1 for t in all_tasks if t.status == "in_progress")

    # Avg time-to-done for tasks completed in the period
    done_tasks = [t for t in all_tasks if t.status == TaskStatus.done.value]
    avg_time_hours = 0.0
    if done_tasks:
        durations = [
            (t.updated_at - t.created_at).total_seconds() / 3600
            for t in done_tasks
            if t.updated_at and t.created_at
        ]
        avg_time_hours = round(sum(durations) / len(durations), 1) if durations else 0.0

    # ── Execution Traces ───────────────────────────────────────────────────────
    trace_q = select(ExecutionTrace)
    if since:
        trace_q = trace_q.where(ExecutionTrace.created_at >= since)
    traces = (await db.execute(trace_q)).scalars().all()

    total_requests = len(traces)
    error_count = sum(1 for t in traces if t.had_error)
    error_rate = round(error_count / total_requests, 4) if total_requests else 0.0

    latency_vals = [t.latency_ms for t in traces if t.latency_ms is not None]
    avg_latency_ms = round(sum(latency_vals) / len(latency_vals)) if latency_vals else 0

    total_tokens = sum(t.total_tokens or 0 for t in traces)
    total_cost = await _compute_traces_cost(traces, all_agents, db)
    cost_per_task = round(total_cost / tasks_completed, 6) if tasks_completed else 0.0

    # ── Top agents by tasks completed ─────────────────────────────────────────
    agent_task_counts: dict[str, int] = defaultdict(int)
    for t in done_tasks:
        if t.assignee_agent_id:
            agent_task_counts[t.assignee_agent_id] += 1

    top_agents = [
        {
            "agent_id": aid,
            "agent_name": all_agents[aid].name if aid in all_agents else aid[:8],
            "tasks_completed": count,
        }
        for aid, count in sorted(agent_task_counts.items(), key=lambda x: -x[1])[:5]
    ]

    # ── Approvals ─────────────────────────────────────────────────────────────
    pending_result = await db.execute(
        select(ApprovalRequest).where(ApprovalRequest.status == "pending")
    )
    approvals_pending = len(pending_result.scalars().all())

    # ── Budget utilization ─────────────────────────────────────────────────────
    budgets_result = await db.execute(select(Budget))
    budgets = budgets_result.scalars().all()
    total_budget_limit = sum(b.limit_usd for b in budgets)
    budget_utilization = round(total_cost / total_budget_limit, 4) if total_budget_limit > 0 else 0.0

    return {
        "period": period,
        "since": since.isoformat() if since else None,
        # Task KPIs
        "tasks_created": tasks_created,
        "tasks_completed": tasks_completed,
        "tasks_in_progress": tasks_in_progress,
        "completion_rate": round(tasks_completed / tasks_created, 4) if tasks_created else 0.0,
        "avg_time_to_done_hours": avg_time_hours,
        # Cost KPIs
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "cost_per_task": cost_per_task,
        # Request KPIs
        "total_requests": total_requests,
        "avg_latency_ms": avg_latency_ms,
        "error_rate": error_rate,
        # Agent KPIs
        "active_agents": active_agents,
        "total_agents": len(all_agents),
        "top_agents_by_tasks": top_agents,
        # Governance
        "approvals_pending": approvals_pending,
        "budget_utilization": budget_utilization,
    }


# ─── All-Agents Summary ───────────────────────────────────────────────────────

@router.get("/agents")
async def all_agents_summary(
    period: str = "month",
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for all agents — used by the scorecards list view."""
    since = _period_since(period)

    agents_result = await db.execute(select(Agent).where(Agent.is_archived == False))  # noqa: E712
    agents = agents_result.scalars().all()
    agent_map = {a.id: a for a in agents}

    trace_q = select(ExecutionTrace)
    if since:
        trace_q = trace_q.where(ExecutionTrace.created_at >= since)
    all_traces = (await db.execute(trace_q)).scalars().all()

    task_q = select(Task)
    if since:
        task_q = task_q.where(Task.created_at >= since)
    all_tasks = (await db.execute(task_q)).scalars().all()

    # Index by agent
    agent_traces: dict[str, list] = defaultdict(list)
    for t in all_traces:
        agent_traces[t.agent_id].append(t)

    agent_tasks: dict[str, list] = defaultdict(list)
    for t in all_tasks:
        if t.assignee_agent_id:
            agent_tasks[t.assignee_agent_id].append(t)

    summaries = []
    for agent in agents:
        ag_traces = agent_traces.get(agent.id, [])
        ag_tasks = agent_tasks.get(agent.id, [])
        total_req = len(ag_traces)
        errors = sum(1 for t in ag_traces if t.had_error)
        latencies = [t.latency_ms for t in ag_traces if t.latency_ms]
        inp_rate, out_rate = await get_pricing(db, agent.llm_provider or "*", agent.llm_model or "*")
        cost = sum(
            compute_cost_usd(t.total_tokens or 0, inp_rate, out_rate)
            for t in ag_traces if t.total_tokens
        )
        tasks_done = sum(1 for t in ag_tasks if t.status == TaskStatus.done.value)

        summaries.append({
            "agent_id": agent.id,
            "agent_name": agent.name,
            "status": agent.status,
            "llm_provider": agent.llm_provider,
            "llm_model": agent.llm_model,
            "total_requests": total_req,
            "error_rate": round(errors / total_req, 4) if total_req else 0.0,
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "total_cost_usd": round(cost, 6),
            "tasks_completed": tasks_done,
            "tasks_assigned": len(ag_tasks),
        })

    summaries.sort(key=lambda x: -x["total_cost_usd"])
    return {"period": period, "agents": summaries}


# ─── Agent Scorecard ──────────────────────────────────────────────────────────

@router.get("/agent-scorecard/{agent_id}")
async def agent_scorecard(
    agent_id: str,
    period: str = "month",
    db: AsyncSession = Depends(get_db),
):
    """Detailed performance scorecard for a single agent."""
    since = _period_since(period)

    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    trace_q = select(ExecutionTrace).where(ExecutionTrace.agent_id == agent_id)
    if since:
        trace_q = trace_q.where(ExecutionTrace.created_at >= since)
    traces = (await db.execute(trace_q)).scalars().all()

    total_requests = len(traces)
    error_count = sum(1 for t in traces if t.had_error)
    latency_vals = [t.latency_ms for t in traces if t.latency_ms is not None]
    avg_latency_ms = round(sum(latency_vals) / len(latency_vals)) if latency_vals else 0
    total_tokens = sum(t.total_tokens or 0 for t in traces)

    inp_rate, out_rate = await get_pricing(db, agent.llm_provider or "*", agent.llm_model or "*")
    total_cost = sum(
        compute_cost_usd(t.total_tokens or 0, inp_rate, out_rate)
        for t in traces if t.total_tokens
    )

    # Tool usage breakdown from JSON tool_calls field
    tool_counts: dict[str, int] = defaultdict(int)
    for trace in traces:
        if trace.tool_calls:
            try:
                for call in json.loads(trace.tool_calls):
                    tool_counts[call.get("name", "unknown")] += 1
            except Exception:
                pass

    top_tools = [
        {"tool": k, "count": v}
        for k, v in sorted(tool_counts.items(), key=lambda x: -x[1])[:10]
    ]

    # Tasks
    task_q = select(Task).where(Task.assignee_agent_id == agent_id)
    if since:
        task_q = task_q.where(Task.created_at >= since)
    tasks = (await db.execute(task_q)).scalars().all()

    tasks_done = sum(1 for t in tasks if t.status == TaskStatus.done.value)

    # Daily request trend (last 14 days)
    trend_since = datetime.now(timezone.utc) - timedelta(days=14)
    recent_traces = [t for t in traces if t.created_at >= trend_since]
    daily_reqs: dict[str, int] = defaultdict(int)
    for t in recent_traces:
        daily_reqs[t.created_at.strftime("%Y-%m-%d")] += 1
    trend = [
        {"date": (trend_since + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
         "requests": daily_reqs.get((trend_since + timedelta(days=i + 1)).strftime("%Y-%m-%d"), 0)}
        for i in range(14)
    ]

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "period": period,
        "llm_provider": agent.llm_provider,
        "llm_model": agent.llm_model,
        "status": agent.status,
        # Request metrics
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "error_count": error_count,
        "error_rate": round(error_count / total_requests, 4) if total_requests else 0.0,
        "avg_latency_ms": avg_latency_ms,
        # Cost metrics
        "total_cost_usd": round(total_cost, 6),
        "cost_per_request": round(total_cost / total_requests, 6) if total_requests else 0.0,
        # Task metrics
        "tasks_assigned": len(tasks),
        "tasks_completed": tasks_done,
        "tasks_in_progress": sum(1 for t in tasks if t.status == "in_progress"),
        "task_completion_rate": round(tasks_done / len(tasks), 4) if tasks else 0.0,
        # Tool usage
        "top_tools": top_tools,
        "unique_tools_used": len(tool_counts),
        # Trend
        "daily_trend": trend,
    }


# ─── Team Analytics ───────────────────────────────────────────────────────────

@router.get("/teams")
async def list_teams_summary(db: AsyncSession = Depends(get_db)):
    """List all teams for the team selector."""
    result = await db.execute(select(Team))
    teams = result.scalars().all()
    return [{"id": t.id, "name": t.name, "member_count": len(t.member_agent_ids or [])} for t in teams]


@router.get("/team/{team_id}")
async def team_analytics(
    team_id: str,
    period: str = "month",
    db: AsyncSession = Depends(get_db),
):
    """Cross-functional analytics for a specific team."""
    since = _period_since(period)

    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    member_ids: list[str] = team.member_agent_ids or []
    if not member_ids:
        return {
            "team_id": team_id,
            "team_name": team.name,
            "period": period,
            "member_count": 0,
            "tasks_completed": 0,
            "total_cost_usd": 0.0,
            "discussions_participated": 0,
            "collaboration_index": 0,
            "members": [],
        }

    agents_result = await db.execute(select(Agent))
    all_agents = {a.id: a for a in agents_result.scalars().all()}

    # Tasks
    task_q = select(Task).where(Task.assignee_agent_id.in_(member_ids))
    if since:
        task_q = task_q.where(Task.created_at >= since)
    tasks = (await db.execute(task_q)).scalars().all()

    tasks_done = sum(1 for t in tasks if t.status == TaskStatus.done.value)
    tasks_in_progress = sum(1 for t in tasks if t.status == "in_progress")

    # Traces & cost
    trace_q = select(ExecutionTrace).where(ExecutionTrace.agent_id.in_(member_ids))
    if since:
        trace_q = trace_q.where(ExecutionTrace.created_at >= since)
    traces = (await db.execute(trace_q)).scalars().all()

    total_requests = len(traces)
    total_cost = 0.0
    agent_costs: dict[str, float] = defaultdict(float)
    agent_requests: dict[str, int] = defaultdict(int)
    for trace in traces:
        agent = all_agents.get(trace.agent_id)
        provider = agent.llm_provider if agent else "*"
        model = agent.llm_model if agent else "*"
        inp_rate, out_rate = await get_pricing(db, provider, model)
        cost = compute_cost_usd(trace.total_tokens or 0, inp_rate, out_rate)
        total_cost += cost
        agent_costs[trace.agent_id] += cost
        agent_requests[trace.agent_id] += 1

    # Discussions with team members
    discussions_result = await db.execute(select(Discussion))
    all_discussions = discussions_result.scalars().all()
    if since:
        team_discussions = [
            d for d in all_discussions
            if d.created_at >= since
            and any(aid in member_ids for aid in (d.participant_agent_ids or []))
        ]
    else:
        team_discussions = [
            d for d in all_discussions
            if any(aid in member_ids for aid in (d.participant_agent_ids or []))
        ]

    # Collaboration index: discussions where 2+ team members co-participated
    collab_count = sum(
        1 for d in team_discussions
        if sum(1 for aid in (d.participant_agent_ids or []) if aid in member_ids) >= 2
    )

    # Per-member breakdown
    members = []
    for mid in member_ids:
        agent = all_agents.get(mid)
        if not agent:
            continue
        member_tasks = [t for t in tasks if t.assignee_agent_id == mid]
        members.append({
            "agent_id": mid,
            "agent_name": agent.name,
            "status": agent.status,
            "tasks_completed": sum(1 for t in member_tasks if t.status == TaskStatus.done.value),
            "tasks_assigned": len(member_tasks),
            "requests": agent_requests.get(mid, 0),
            "cost_usd": round(agent_costs.get(mid, 0.0), 6),
        })

    return {
        "team_id": team_id,
        "team_name": team.name,
        "period": period,
        "member_count": len(member_ids),
        "tasks_completed": tasks_done,
        "tasks_in_progress": tasks_in_progress,
        "total_tasks": len(tasks),
        "total_requests": total_requests,
        "total_cost_usd": round(total_cost, 6),
        "discussions_participated": len(team_discussions),
        "collaboration_index": collab_count,
        "members": members,
    }


# ─── Multi-Series Trends ──────────────────────────────────────────────────────

@router.get("/trends")
async def multi_trends(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Multi-series daily trends: cost, requests, errors, tasks completed."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    agents_result = await db.execute(select(Agent))
    agents = {a.id: a for a in agents_result.scalars().all()}

    traces = (await db.execute(
        select(ExecutionTrace).where(ExecutionTrace.created_at >= since)
    )).scalars().all()

    tasks = (await db.execute(
        select(Task).where(
            Task.updated_at >= since,
            Task.status == TaskStatus.done.value,
        )
    )).scalars().all()

    # Aggregate by day
    daily_cost: dict[str, float] = {}
    daily_reqs: dict[str, int] = defaultdict(int)
    daily_errors: dict[str, int] = defaultdict(int)

    for trace in traces:
        day = trace.created_at.strftime("%Y-%m-%d")
        daily_reqs[day] += 1
        if trace.had_error:
            daily_errors[day] += 1
        if trace.total_tokens:
            agent = agents.get(trace.agent_id)
            provider = agent.llm_provider if agent else "*"
            model = agent.llm_model if agent else "*"
            inp_rate, out_rate = await get_pricing(db, provider, model)
            daily_cost[day] = daily_cost.get(day, 0.0) + compute_cost_usd(
                trace.total_tokens, inp_rate, out_rate
            )

    daily_tasks: dict[str, int] = defaultdict(int)
    for task in tasks:
        if task.updated_at:
            daily_tasks[task.updated_at.strftime("%Y-%m-%d")] += 1

    # Fill all days (including zeros)
    result = []
    for i in range(days):
        day = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({
            "date": day,
            "cost_usd": round(daily_cost.get(day, 0.0), 6),
            "requests": daily_reqs.get(day, 0),
            "errors": daily_errors.get(day, 0),
            "tasks_completed": daily_tasks.get(day, 0),
        })

    return {"days": days, "data": result}
