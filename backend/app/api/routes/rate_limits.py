"""Rate limit configuration and live usage API routes."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ModelRateLimitCreate, ModelRateLimitResponse, ModelRateLimitUpdate
from app.config import settings
from app.db.session import get_db
from app.models.rate_limit import ModelRateLimit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rate-limits", tags=["rate-limits"])


@router.get("/", response_model=list[ModelRateLimitResponse])
async def list_rate_limits(db: AsyncSession = Depends(get_db)):
    """List all configured rate limits."""
    result = await db.execute(
        select(ModelRateLimit).order_by(ModelRateLimit.provider, ModelRateLimit.model)
    )
    return result.scalars().all()


@router.post("/", response_model=ModelRateLimitResponse, status_code=201)
async def create_rate_limit(
    payload: ModelRateLimitCreate, db: AsyncSession = Depends(get_db)
):
    """Create a rate limit for a provider+model."""
    # Check for duplicate
    existing = await db.execute(
        select(ModelRateLimit).where(
            ModelRateLimit.provider == payload.provider,
            ModelRateLimit.model == payload.model,
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"Rate limit already exists for {payload.provider}/{payload.model}",
        )

    rate_limit = ModelRateLimit(**payload.model_dump())
    db.add(rate_limit)
    await db.flush()
    await db.refresh(rate_limit)

    # Invalidate cache
    from app.core.usage_tracker import refresh_rate_limit_cache
    await refresh_rate_limit_cache(db)

    return rate_limit


@router.put("/{rate_limit_id}", response_model=ModelRateLimitResponse)
async def update_rate_limit(
    rate_limit_id: str,
    payload: ModelRateLimitUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a rate limit."""
    rate_limit = await db.get(ModelRateLimit, rate_limit_id)
    if not rate_limit:
        raise HTTPException(status_code=404, detail="Rate limit not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rate_limit, field, value)

    await db.flush()
    await db.refresh(rate_limit)

    from app.core.usage_tracker import refresh_rate_limit_cache
    await refresh_rate_limit_cache(db)

    return rate_limit


@router.delete("/{rate_limit_id}", status_code=204)
async def delete_rate_limit(
    rate_limit_id: str, db: AsyncSession = Depends(get_db)
):
    """Delete a rate limit."""
    rate_limit = await db.get(ModelRateLimit, rate_limit_id)
    if not rate_limit:
        raise HTTPException(status_code=404, detail="Rate limit not found")

    await db.delete(rate_limit)

    from app.core.usage_tracker import refresh_rate_limit_cache
    await refresh_rate_limit_cache(db)


@router.get("/usage")
async def get_live_usage(db: AsyncSession = Depends(get_db)):
    """Get live usage counters from Redis for all configured rate limits.

    Also includes any provider/model pairs that have Redis usage data but no
    DB rate limit entry (e.g. models used via smart routing without explicit limits).
    """
    from app.core.usage_tracker import get_current_usage
    from app.core.redis_client import get_redis

    result = await db.execute(
        select(ModelRateLimit).order_by(ModelRateLimit.provider, ModelRateLimit.model)
    )
    limits = result.scalars().all()

    # Build set of (provider, model) pairs already covered by DB entries
    seen: set[tuple[str, str]] = set()
    usage_data = []

    for limit in limits:
        seen.add((limit.provider, limit.model))
        usage = await get_current_usage(
            limit.provider, limit.model, limit.refresh_interval_hours
        )
        usage_data.append({
            "id": limit.id,
            "provider": limit.provider,
            "model": limit.model,
            "label": limit.label,
            "limits": {
                "rpm": limit.requests_per_minute,
                "rpd": limit.requests_per_day,
                "tpm": limit.tokens_per_minute,
                "tpd": limit.tokens_per_day,
            },
            "current": usage,
        })

    # Scan Redis for any models with usage data not covered by DB entries
    try:
        redis = await get_redis()
        keys = await redis.keys("sutra:usage:*")
        redis_pairs: set[tuple[str, str]] = set()
        for key in keys:
            # Key format: sutra:usage:{provider}:{model}:{metric}:{bucket}
            parts = key.split(":")
            if len(parts) >= 5:
                provider = parts[2]
                # model may contain colons — everything between provider and metric
                metric = parts[-2]
                bucket = parts[-1]
                model = ":".join(parts[3:-2])
                if metric in ("rpm", "rpd", "tpm", "tpd"):
                    redis_pairs.add((provider, model))

        for provider, model in sorted(redis_pairs - seen):
            usage = await get_current_usage(provider, model)
            if any(v > 0 for v in usage.values()):
                usage_data.append({
                    "id": f"redis:{provider}:{model}",
                    "provider": provider,
                    "model": model,
                    "label": None,
                    "limits": {"rpm": None, "rpd": None, "tpm": None, "tpd": None},
                    "current": usage,
                })
    except Exception as e:
        logger.warning(f"Failed to scan Redis for unconfigured usage: {e}")

    return usage_data


# ─── Sync from provider ──────────────────────────────────────────────────────

def _parse_int(v: str | None) -> int | None:
    """Parse a string to int, return None for missing/invalid."""
    if not v:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


async def _sync_groq(db: AsyncSession) -> dict:
    """Sync rate limits from Groq by probing each model's headers."""
    from app.core.llm_registry import llm_registry

    api_key = llm_registry._providers.get("groq", {}).get("api_key", "") or settings.groq_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="No Groq API key configured.")

    # Fetch model list
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        models = [m["id"] for m in resp.json().get("data", [])]

    if not models:
        return {"provider": "groq", "synced": 0, "models": []}

    synced = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for model_id in models:
            try:
                # Lightweight completions call to capture rate limit headers
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1,
                    },
                    timeout=10.0,
                )
                h = r.headers
            except httpx.HTTPStatusError as e:
                h = e.response.headers
            except Exception:
                continue

            rpm = _parse_int(h.get("x-ratelimit-limit-requests"))
            tpm = _parse_int(h.get("x-ratelimit-limit-tokens"))
            rpd = _parse_int(h.get("x-ratelimit-limit-requests-day") or
                             h.get("x-ratelimit-limit-requests-daily"))
            tpd = _parse_int(h.get("x-ratelimit-limit-tokens-day") or
                             h.get("x-ratelimit-limit-tokens-daily"))

            if rpm is None and tpm is None and rpd is None and tpd is None:
                continue

            # Upsert
            result = await db.execute(
                select(ModelRateLimit).where(
                    ModelRateLimit.provider == "groq",
                    ModelRateLimit.model == model_id,
                )
            )
            existing = result.scalars().first()
            if existing:
                existing.requests_per_minute = rpm
                existing.requests_per_day = rpd
                existing.tokens_per_minute = tpm
                existing.tokens_per_day = tpd
            else:
                db.add(ModelRateLimit(
                    provider="groq", model=model_id,
                    requests_per_minute=rpm, requests_per_day=rpd,
                    tokens_per_minute=tpm, tokens_per_day=tpd,
                ))
            synced.append(model_id)

    await db.flush()

    from app.core.usage_tracker import refresh_rate_limit_cache
    await refresh_rate_limit_cache(db)

    return {"provider": "groq", "synced": len(synced), "models": synced}


async def _sync_google(db: AsyncSession) -> dict:
    """Sync rate limits from Google Gemini API model metadata."""
    from app.core.llm_registry import llm_registry

    api_key = llm_registry._providers.get("google", {}).get("api_key", "") or settings.google_api_key
    if not api_key:
        raise HTTPException(status_code=400, detail="No Google API key configured.")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        resp.raise_for_status()
        models_data = resp.json().get("models", [])

    synced = []
    for m in models_data:
        model_id = m.get("name", "").removeprefix("models/")
        if not model_id:
            continue

        # Google exposes rate limits in model metadata
        rpm = m.get("rateLimits", {}).get("requestsPerMinute") or m.get("requestsPerMinute")
        tpm = m.get("rateLimits", {}).get("tokensPerMinute") or m.get("tokensPerMinute")
        rpd = m.get("rateLimits", {}).get("requestsPerDay") or m.get("requestsPerDay")

        # Determine label from supported methods
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
            label = "Text-out"
        elif "embedContent" in methods:
            label = "Embedding"
        else:
            label = "Other"

        # Upsert
        result = await db.execute(
            select(ModelRateLimit).where(
                ModelRateLimit.provider == "google",
                ModelRateLimit.model == model_id,
            )
        )
        existing = result.scalars().first()
        if existing:
            if rpm is not None:
                existing.requests_per_minute = rpm
            if rpd is not None:
                existing.requests_per_day = rpd
            if tpm is not None:
                existing.tokens_per_minute = tpm
            existing.label = label
        else:
            db.add(ModelRateLimit(
                provider="google", model=model_id,
                requests_per_minute=rpm, requests_per_day=rpd,
                tokens_per_minute=tpm, tokens_per_day=None,
                label=label,
            ))
        synced.append(model_id)

    await db.flush()

    from app.core.usage_tracker import refresh_rate_limit_cache
    await refresh_rate_limit_cache(db)

    return {"provider": "google", "synced": len(synced), "models": synced}


_SYNC_HANDLERS = {
    "groq": _sync_groq,
    "google": _sync_google,
}


@router.post("/sync/{provider}")
async def sync_from_provider(provider: str, db: AsyncSession = Depends(get_db)):
    """Sync rate limits from a provider's API. Supported: groq, google."""
    handler = _SYNC_HANDLERS.get(provider)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Sync not supported for '{provider}'. Supported: {', '.join(_SYNC_HANDLERS)}",
        )
    try:
        result = await handler(db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync from {provider} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
