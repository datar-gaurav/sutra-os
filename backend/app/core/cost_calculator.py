"""Cost calculation utilities — compute USD cost from token usage and pricing."""

import logging
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import ModelPricing, DEFAULT_PRICING

logger = logging.getLogger(__name__)

# In-memory cache of provider/model → (input_per_1k, output_per_1k)
_pricing_cache: dict[tuple[str, str], tuple[float, float]] = {}


def _load_defaults_into_cache() -> None:
    for provider, model, inp, out in DEFAULT_PRICING:
        _pricing_cache[(provider, model)] = (inp, out)


_load_defaults_into_cache()


async def get_pricing(
    db: AsyncSession, provider: str, model: str
) -> tuple[float, float]:
    """Return (input_per_1k, output_per_1k) for a provider/model pair.

    Lookup order: exact DB match → wildcard DB match → exact cache → wildcard cache → 0.001/0.002
    """
    # Try DB first (custom / overridden pricing)
    try:
        result = await db.execute(
            select(ModelPricing).where(
                ModelPricing.provider.in_([provider, "*"]),
                ModelPricing.model.in_([model, "*"]),
            )
        )
        rows = result.scalars().all()
        exact = next((r for r in rows if r.provider == provider and r.model == model), None)
        if exact:
            return exact.input_cost_per_1k, exact.output_cost_per_1k
        provider_wildcard = next((r for r in rows if r.provider == provider and r.model == "*"), None)
        if provider_wildcard:
            return provider_wildcard.input_cost_per_1k, provider_wildcard.output_cost_per_1k
    except Exception as e:
        logger.debug(f"DB pricing lookup failed, using cache: {e}")

    # Fall back to in-memory cache
    exact_cache = _pricing_cache.get((provider, model))
    if exact_cache:
        return exact_cache
    wildcard_cache = _pricing_cache.get((provider, "*"))
    if wildcard_cache:
        return wildcard_cache
    global_wildcard = _pricing_cache.get(("*", "*"))
    if global_wildcard:
        return global_wildcard

    return 0.001, 0.002


def compute_cost_usd(
    tokens: int,
    input_per_1k: float,
    output_per_1k: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> float:
    """Compute USD cost from token counts.

    If input_tokens and output_tokens are available, use them separately.
    Otherwise split total tokens 50/50 between input and output.
    """
    if tokens <= 0:
        return 0.0

    if input_tokens is not None and output_tokens is not None:
        cost = (input_tokens / 1000 * input_per_1k) + (output_tokens / 1000 * output_per_1k)
    else:
        # Blended rate using 50/50 split assumption
        blended = (input_per_1k + output_per_1k) / 2
        cost = tokens / 1000 * blended

    return round(cost, 8)


async def compute_agent_spend(
    db: AsyncSession,
    agent_id: str,
    since: "datetime | None" = None,
) -> float:
    """Compute total USD spend for an agent by summing token-cost over execution traces."""
    from app.models.trace import ExecutionTrace
    from app.models.agent import Agent

    # Get the agent's provider/model
    agent = await db.get(Agent, agent_id)
    if not agent:
        return 0.0

    provider = agent.llm_provider or "*"
    model = agent.llm_model or "*"
    inp_rate, out_rate = await get_pricing(db, provider, model)

    query = select(ExecutionTrace).where(
        ExecutionTrace.agent_id == agent_id,
        ExecutionTrace.total_tokens.isnot(None),
    )
    if since:
        query = query.where(ExecutionTrace.created_at >= since)

    result = await db.execute(query)
    traces = result.scalars().all()

    total = sum(
        compute_cost_usd(t.total_tokens or 0, inp_rate, out_rate)
        for t in traces
    )
    return round(total, 6)
