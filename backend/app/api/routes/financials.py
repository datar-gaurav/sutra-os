"""Financial management routes — budgets, cost tracking, pricing, and spend reports."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_calculator import compute_cost_usd, get_pricing
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.agent import Agent
from app.models.budget import Budget, BudgetPeriod, BudgetScope
from app.models.pricing import ModelPricing, DEFAULT_PRICING
from app.models.trace import ExecutionTrace
from app.models.usage import ModelUsage
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/financials", tags=["financials"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    scope: str = BudgetScope.agent.value
    agent_id: str | None = None
    team_id: str | None = None
    period: str = BudgetPeriod.monthly.value
    limit_usd: float = Field(..., gt=0)
    alert_threshold_pct: float = Field(0.8, ge=0.1, le=1.0)


class BudgetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    limit_usd: float | None = Field(None, gt=0)
    alert_threshold_pct: float | None = Field(None, ge=0.1, le=1.0)


class BudgetResponse(BaseModel):
    id: str
    name: str
    description: str | None
    scope: str
    agent_id: str | None
    team_id: str | None
    period: str
    limit_usd: float
    alert_threshold_pct: float
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PricingUpdate(BaseModel):
    input_cost_per_1k: float = Field(..., ge=0)
    output_cost_per_1k: float = Field(..., ge=0)


# ─── Helper: period start ─────────────────────────────────────────────────────

def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == BudgetPeriod.daily.value:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == BudgetPeriod.weekly.value:
        return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    else:  # monthly
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ─── Cost Overview ────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_overview(
    period: str = "month",  # day | week | month | all
    db: AsyncSession = Depends(get_db),
):
    """Return total spend + per-agent breakdown for the selected period."""
    now = datetime.now(timezone.utc)
    since: datetime | None = None
    if period == "day":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        since = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Fetch all agents
    agents_result = await db.execute(select(Agent))
    agents = agents_result.scalars().all()
    agent_map = {a.id: a for a in agents}

    # Fetch traces with token counts
    query = select(ExecutionTrace).where(ExecutionTrace.total_tokens.isnot(None))
    if since:
        query = query.where(ExecutionTrace.created_at >= since)
    traces_result = await db.execute(query)
    traces = traces_result.scalars().all()

    # Group by agent_id, compute cost
    agent_costs: dict[str, float] = {}
    provider_costs: dict[str, float] = {}
    total_tokens = 0
    total_cost = 0.0

    for trace in traces:
        agent = agent_map.get(trace.agent_id)
        provider = agent.llm_provider if agent else "*"
        model = agent.llm_model if agent else "*"
        inp_rate, out_rate = await get_pricing(db, provider, model)
        cost = compute_cost_usd(trace.total_tokens or 0, inp_rate, out_rate)

        agent_costs[trace.agent_id] = agent_costs.get(trace.agent_id, 0.0) + cost
        key = f"{provider}/{model}"
        provider_costs[key] = provider_costs.get(key, 0.0) + cost
        total_tokens += trace.total_tokens or 0
        total_cost += cost

    # Build per-agent list
    by_agent = [
        {
            "agent_id": aid,
            "agent_name": agent_map[aid].name if aid in agent_map else aid[:8],
            "cost_usd": round(cost, 6),
        }
        for aid, cost in sorted(agent_costs.items(), key=lambda x: -x[1])
    ]

    by_provider = [
        {"provider_model": k, "cost_usd": round(v, 6)}
        for k, v in sorted(provider_costs.items(), key=lambda x: -x[1])
    ]

    return {
        "period": period,
        "since": since.isoformat() if since else None,
        "total_cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "by_agent": by_agent,
        "by_provider": by_provider,
    }


@router.get("/trends")
async def get_trends(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Return daily cost totals for the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    agents_result = await db.execute(select(Agent))
    agents = {a.id: a for a in agents_result.scalars().all()}

    query = select(ExecutionTrace).where(
        ExecutionTrace.total_tokens.isnot(None),
        ExecutionTrace.created_at >= since,
    )
    traces = (await db.execute(query)).scalars().all()

    # Group by date
    daily: dict[str, float] = {}
    for trace in traces:
        day = trace.created_at.strftime("%Y-%m-%d")
        agent = agents.get(trace.agent_id)
        provider = agent.llm_provider if agent else "*"
        model = agent.llm_model if agent else "*"
        inp_rate, out_rate = await get_pricing(db, provider, model)
        cost = compute_cost_usd(trace.total_tokens or 0, inp_rate, out_rate)
        daily[day] = daily.get(day, 0.0) + cost

    # Fill gaps with 0
    result = []
    for i in range(days):
        day = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        result.append({"date": day, "cost_usd": round(daily.get(day, 0.0), 6)})

    return {"days": days, "data": result}


# ─── Budgets ──────────────────────────────────────────────────────────────────

@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Budget).order_by(Budget.created_at.desc()))
    return result.scalars().all()


@router.post("/budgets", response_model=BudgetResponse)
async def create_budget(
    payload: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = Budget(
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        agent_id=payload.agent_id,
        team_id=payload.team_id,
        period=payload.period,
        limit_usd=payload.limit_usd,
        alert_threshold_pct=payload.alert_threshold_pct,
        period_start=_period_start(payload.period),
        created_by_user_id=current_user.id,
    )
    db.add(budget)
    await db.flush()
    await db.refresh(budget)
    return budget


@router.put("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    db: AsyncSession = Depends(get_db),
):
    budget = await db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    if payload.name is not None:
        budget.name = payload.name
    if payload.description is not None:
        budget.description = payload.description
    if payload.limit_usd is not None:
        budget.limit_usd = payload.limit_usd
    if payload.alert_threshold_pct is not None:
        budget.alert_threshold_pct = payload.alert_threshold_pct
    await db.flush()
    await db.refresh(budget)
    return budget


@router.delete("/budgets/{budget_id}", status_code=204)
async def delete_budget(budget_id: str, db: AsyncSession = Depends(get_db)):
    budget = await db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    await db.delete(budget)
    await db.flush()


@router.get("/budgets/{budget_id}/status")
async def get_budget_status(budget_id: str, db: AsyncSession = Depends(get_db)):
    """Return current spend vs. limit for a specific budget."""
    budget = await db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    since = _period_start(budget.period)
    spent = 0.0

    agents_result = await db.execute(select(Agent))
    agents = {a.id: a for a in agents_result.scalars().all()}

    if budget.scope == BudgetScope.agent.value and budget.agent_id:
        query = select(ExecutionTrace).where(
            ExecutionTrace.agent_id == budget.agent_id,
            ExecutionTrace.total_tokens.isnot(None),
            ExecutionTrace.created_at >= since,
        )
    elif budget.scope == BudgetScope.org.value:
        query = select(ExecutionTrace).where(
            ExecutionTrace.total_tokens.isnot(None),
            ExecutionTrace.created_at >= since,
        )
    else:
        query = select(ExecutionTrace).where(
            ExecutionTrace.total_tokens.isnot(None),
            ExecutionTrace.created_at >= since,
        )

    traces = (await db.execute(query)).scalars().all()
    for trace in traces:
        agent = agents.get(trace.agent_id)
        provider = agent.llm_provider if agent else "*"
        model = agent.llm_model if agent else "*"
        inp_rate, out_rate = await get_pricing(db, provider, model)
        spent += compute_cost_usd(trace.total_tokens or 0, inp_rate, out_rate)

    pct = spent / budget.limit_usd if budget.limit_usd > 0 else 0.0
    return {
        "budget_id": budget.id,
        "name": budget.name,
        "scope": budget.scope,
        "period": budget.period,
        "limit_usd": budget.limit_usd,
        "spent_usd": round(spent, 6),
        "remaining_usd": round(max(0.0, budget.limit_usd - spent), 6),
        "utilization_pct": round(pct, 4),
        "alert_threshold_pct": budget.alert_threshold_pct,
        "is_over_budget": pct >= 1.0,
        "is_near_threshold": pct >= budget.alert_threshold_pct,
    }


@router.get("/budget-alerts")
async def get_budget_alerts(db: AsyncSession = Depends(get_db)):
    """Return list of budgets that are at or near their threshold."""
    budgets_result = await db.execute(select(Budget))
    budgets = budgets_result.scalars().all()

    agents_result = await db.execute(select(Agent))
    agents = {a.id: a for a in agents_result.scalars().all()}

    alerts = []
    for budget in budgets:
        since = _period_start(budget.period)

        query = select(ExecutionTrace).where(
            ExecutionTrace.total_tokens.isnot(None),
            ExecutionTrace.created_at >= since,
        )
        if budget.scope == BudgetScope.agent.value and budget.agent_id:
            query = query.where(ExecutionTrace.agent_id == budget.agent_id)

        traces = (await db.execute(query)).scalars().all()
        spent = 0.0
        for trace in traces:
            agent = agents.get(trace.agent_id)
            provider = agent.llm_provider if agent else "*"
            model = agent.llm_model if agent else "*"
            inp_rate, out_rate = await get_pricing(db, provider, model)
            spent += compute_cost_usd(trace.total_tokens or 0, inp_rate, out_rate)

        pct = spent / budget.limit_usd if budget.limit_usd > 0 else 0.0
        if pct >= budget.alert_threshold_pct:
            alerts.append({
                "budget_id": budget.id,
                "name": budget.name,
                "scope": budget.scope,
                "spent_usd": round(spent, 6),
                "limit_usd": budget.limit_usd,
                "utilization_pct": round(pct, 4),
                "is_over_budget": pct >= 1.0,
                "severity": "critical" if pct >= 1.0 else "warning",
            })

    return {"alerts": alerts, "count": len(alerts)}


# ─── Pricing ──────────────────────────────────────────────────────────────────

@router.get("/pricing")
async def list_pricing(db: AsyncSession = Depends(get_db)):
    """Return all configured model pricing rows, with defaults merged in."""
    result = await db.execute(select(ModelPricing).order_by(ModelPricing.provider, ModelPricing.model))
    db_rows = result.scalars().all()
    db_set = {(r.provider, r.model) for r in db_rows}

    rows = [
        {
            "id": r.id,
            "provider": r.provider,
            "model": r.model,
            "input_cost_per_1k": r.input_cost_per_1k,
            "output_cost_per_1k": r.output_cost_per_1k,
            "is_custom": True,
        }
        for r in db_rows
    ]

    # Append built-in defaults not yet in DB
    for provider, model, inp, out in DEFAULT_PRICING:
        if (provider, model) not in db_set:
            rows.append({
                "id": None,
                "provider": provider,
                "model": model,
                "input_cost_per_1k": inp,
                "output_cost_per_1k": out,
                "is_custom": False,
            })

    return rows


@router.put("/pricing/{provider}/{model}")
async def upsert_pricing(
    provider: str,
    model: str,
    payload: PricingUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Override pricing for a specific provider/model."""
    result = await db.execute(
        select(ModelPricing).where(
            ModelPricing.provider == provider,
            ModelPricing.model == model,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.input_cost_per_1k = payload.input_cost_per_1k
        row.output_cost_per_1k = payload.output_cost_per_1k
    else:
        row = ModelPricing(
            provider=provider,
            model=model,
            input_cost_per_1k=payload.input_cost_per_1k,
            output_cost_per_1k=payload.output_cost_per_1k,
        )
        db.add(row)
    await db.flush()
    await db.refresh(row)
    return {
        "provider": row.provider,
        "model": row.model,
        "input_cost_per_1k": row.input_cost_per_1k,
        "output_cost_per_1k": row.output_cost_per_1k,
    }
