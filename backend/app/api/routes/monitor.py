from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.schemas import MonitorUsageOverview, ModelUsageResponse, ModelLimitResponse, ModelLimitUpdate
from app.models.usage import ModelUsage, ModelLimit
from app.models.trace import ExecutionTrace
from app.config import settings
from app.core.llm_registry import llm_registry
from app.core.token_guard import get_context_limit

router = APIRouter()

@router.get("/usage", response_model=MonitorUsageOverview)
async def get_usage_overview(db: AsyncSession = Depends(get_db)):
    """Fetch today's model usage and all model limits."""
    today = datetime.now(timezone.utc).date()
    
    # Get today's usages
    usage_stmt = select(ModelUsage).where(ModelUsage.usage_date == today)
    result = await db.execute(usage_stmt)
    usages = result.scalars().all()
    
    usage_responses = [
        ModelUsageResponse.model_validate(u) for u in usages
    ]
    
    # Get all configured limits
    limit_stmt = select(ModelLimit)
    result = await db.execute(limit_stmt)
    limits = result.scalars().all()
    
    # Map them for response
    limit_responses = [ModelLimitResponse.model_validate(limit) for limit in limits]
    
    # We might want to inject default limits for standard providers if they don't exist
    registered_providers = set(llm_registry._providers.keys()) | {"ollama", "openai", "anthropic", "google", "groq", "openrouter", "perplexity"}
    
    existing_providers = {limit.provider for limit in limits}
    
    for provider in registered_providers:
        if provider not in existing_providers:
            limit_responses.append(ModelLimitResponse(provider=provider, model="*", daily_limit=100)) # Default wildcard

    return MonitorUsageOverview(
        usages=usage_responses,
        limits=limit_responses
    )

@router.post("/limits/{provider}", status_code=status.HTTP_200_OK)
async def update_provider_limit(
    provider: str,
    limit_update: ModelLimitUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update or create a daily limit for a provider and model."""
    limit_stmt = select(ModelLimit).where(
        ModelLimit.provider == provider,
        ModelLimit.model == limit_update.model
    )
    result = await db.execute(limit_stmt)
    db_limit = result.scalar_one_or_none()
    
    if db_limit:
        db_limit.daily_limit = limit_update.daily_limit
    else:
        new_limit = ModelLimit(
            provider=provider,
            model=limit_update.model,
            daily_limit=limit_update.daily_limit
        )
        db.add(new_limit)
        
    await db.commit()
    return {"status": "success"}


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """
    Aggregate execution trace stats for today.
    Returns overall + per-agent breakdown.
    """
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch all traces for today
    traces_result = await db.execute(
        select(ExecutionTrace).where(ExecutionTrace.created_at >= today_start)
    )
    traces = traces_result.scalars().all()

    # Aggregate
    total = len(traces)
    errors = sum(1 for t in traces if t.had_error)
    latencies = [t.latency_ms for t in traces if t.latency_ms is not None]
    avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
    error_rate = round(errors / total, 4) if total else 0.0

    # Per-agent breakdown
    agent_stats: dict[str, dict] = {}
    for t in traces:
        s = agent_stats.setdefault(t.agent_id, {
            "agent_id": t.agent_id,
            "requests": 0,
            "errors": 0,
            "latencies": [],
            "total_tokens": 0,
            "total_input_tokens": 0,
        })
        s["requests"] += 1
        if t.had_error:
            s["errors"] += 1
        if t.latency_ms is not None:
            s["latencies"].append(t.latency_ms)
        if t.total_tokens:
            s["total_tokens"] += t.total_tokens
        if t.input_tokens:
            s["total_input_tokens"] += t.input_tokens

    # Resolve agent model info for context utilization
    from app.core.agent_manager import agent_manager

    agents = []
    for s in agent_stats.values():
        req = s["requests"]
        err = s["errors"]
        lats = s["latencies"]
        agent_entry = {
            "agent_id": s["agent_id"],
            "requests": req,
            "errors": err,
            "error_rate": round(err / req, 4) if req else 0.0,
            "avg_latency_ms": int(sum(lats) / len(lats)) if lats else 0,
            "total_tokens_today": s["total_tokens"],
            "total_input_tokens_today": s["total_input_tokens"],
        }
        # Add context utilization info if agent is running
        info = agent_manager.get_info(s["agent_id"])
        if info:
            provider = info.get("llm_provider", "")
            model = info.get("llm_model", "")
            ctx_limit = get_context_limit(provider, model)
            if s["total_input_tokens"] > 0 and req > 0:
                avg_input = s["total_input_tokens"] // req
                agent_entry["avg_context_utilization"] = round(avg_input / ctx_limit, 4) if ctx_limit else 0.0
                agent_entry["context_limit"] = ctx_limit
        agents.append(agent_entry)
    agents.sort(key=lambda a: a["requests"], reverse=True)

    # Recent errors (last 10)
    recent_errors = [
        {
            "trace_id": t.id,
            "agent_id": t.agent_id,
            "error_message": t.error_message,
            "created_at": str(t.created_at),
        }
        for t in sorted(traces, key=lambda x: x.created_at, reverse=True)
        if t.had_error
    ][:10]

    return {
        "period": "today",
        "total_requests": total,
        "total_errors": errors,
        "avg_latency_ms": avg_latency,
        "error_rate": error_rate,
        "agents": agents,
        "recent_errors": recent_errors,
    }


@router.get("/alerts")
async def get_alerts(db: AsyncSession = Depends(get_db)):
    """
    Compute active alerts based on current system state.
    Alert types: quota_exhausted, quota_warning, high_error_rate, recent_failure
    """
    alerts = []
    today = datetime.now(timezone.utc).date()
    thirty_min_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Usage vs limits ────────────────────────────────────────────────────
    usage_result = await db.execute(
        select(ModelUsage).where(ModelUsage.usage_date == today)
    )
    usages = usage_result.scalars().all()

    limit_result = await db.execute(select(ModelLimit))
    limits = limit_result.scalars().all()

    def resolve_limit(provider: str, model: str) -> int | None:
        exact = next((l for l in limits if l.provider == provider and l.model == model), None)
        if exact:
            return exact.daily_limit
        wildcard = next((l for l in limits if l.provider == provider and l.model == "*"), None)
        return wildcard.daily_limit if wildcard else None

    for u in usages:
        daily_limit = resolve_limit(u.provider, u.model)
        if daily_limit is None:
            daily_limit = 100
        pct = u.request_count / daily_limit if daily_limit > 0 else 1.0
        label = f"{u.provider}/{u.model}"
        if pct >= 1.0:
            alerts.append({
                "id": f"quota_exhausted_{u.provider}_{u.model}",
                "severity": "critical",
                "type": "quota_exhausted",
                "title": "Quota Exhausted",
                "message": f"{label} has reached its daily limit ({u.request_count}/{daily_limit} requests).",
                "provider": u.provider,
                "model": u.model,
            })
        elif pct >= 0.8:
            alerts.append({
                "id": f"quota_warning_{u.provider}_{u.model}",
                "severity": "warning",
                "type": "quota_warning",
                "title": "Quota Warning",
                "message": f"{label} is at {int(pct * 100)}% of its daily limit ({u.request_count}/{daily_limit} requests).",
                "provider": u.provider,
                "model": u.model,
            })

    # ── High error rate per agent (min 5 requests today) ──────────────────
    traces_result = await db.execute(
        select(ExecutionTrace).where(ExecutionTrace.created_at >= today_start)
    )
    traces = traces_result.scalars().all()

    agent_counts: dict[str, dict] = {}
    for t in traces:
        s = agent_counts.setdefault(t.agent_id, {"total": 0, "errors": 0})
        s["total"] += 1
        if t.had_error:
            s["errors"] += 1

    for agent_id, s in agent_counts.items():
        if s["total"] >= 5:
            rate = s["errors"] / s["total"]
            if rate >= 0.2:
                alerts.append({
                    "id": f"high_error_rate_{agent_id}",
                    "severity": "critical" if rate >= 0.5 else "warning",
                    "type": "high_error_rate",
                    "title": "High Error Rate",
                    "message": f"Agent {agent_id[:8]}… has a {int(rate * 100)}% error rate today ({s['errors']}/{s['total']} requests failed).",
                    "agent_id": agent_id,
                })

    # ── Recent failure in last 30 min ─────────────────────────────────────
    recent_failed_agents: set[str] = set()
    for t in traces:
        if t.had_error and t.created_at and t.created_at.replace(tzinfo=timezone.utc) >= thirty_min_ago:
            recent_failed_agents.add(t.agent_id)
    # Only alert if not already covered by high_error_rate
    high_error_agent_ids = {a["id"].replace("high_error_rate_", "") for a in alerts if a["type"] == "high_error_rate"}
    for agent_id in recent_failed_agents - high_error_agent_ids:
        alerts.append({
            "id": f"recent_failure_{agent_id}",
            "severity": "warning",
            "type": "recent_failure",
            "title": "Recent Failure",
            "message": f"Agent {agent_id[:8]}… had at least one error in the last 30 minutes.",
            "agent_id": agent_id,
        })

    return {"alerts": alerts, "count": len(alerts)}


# ── System Health (Circuit Breakers, Cache, Watchdog) ────────────────────────

@router.get("/health/resilience")
async def resilience_health():
    """Get status of circuit breakers, prompt cache, and agent watchdog."""
    from app.core.circuit_breaker import get_all_breakers
    from app.core.prompt_cache import prompt_cache
    from app.core.watchdog import watchdog

    return {
        "circuit_breakers": get_all_breakers(),
        "prompt_cache": prompt_cache.stats,
        "watchdog": watchdog.stats,
    }
