"""Redis-backed real-time usage tracker for LLM rate limit management."""

import logging
import time
from datetime import datetime, timezone

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

# In-memory cache for rate limit configs (avoids DB hit per request)
_rate_limit_cache: dict[str, dict] = {}
_cache_expires_at: float = 0
_CACHE_TTL_SECONDS = 60


def _minute_bucket() -> str:
    """Current minute bucket key segment: YYYYMMDD_HHMM."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def _day_bucket(refresh_interval_hours: int = 24) -> str:
    """Current day/window bucket key segment."""
    now = datetime.now(timezone.utc)
    if refresh_interval_hours >= 24:
        return now.strftime("%Y%m%d")
    # Sub-24h windows: calculate window number within the day
    hours_elapsed = now.hour + now.minute / 60
    window_num = int(hours_elapsed // refresh_interval_hours)
    return f"{now.strftime('%Y%m%d')}_W{window_num}"


def _key(provider: str, model: str, metric: str, bucket: str) -> str:
    return f"sutra:usage:{provider}:{model}:{metric}:{bucket}"


async def refresh_rate_limit_cache(db) -> None:
    """Reload rate limit configs from DB into memory cache."""
    global _rate_limit_cache, _cache_expires_at
    from sqlalchemy import select
    from app.models.rate_limit import ModelRateLimit

    result = await db.execute(select(ModelRateLimit))
    limits = result.scalars().all()
    _rate_limit_cache = {}
    for limit in limits:
        cache_key = f"{limit.provider}:{limit.model}"
        _rate_limit_cache[cache_key] = {
            "rpm": limit.requests_per_minute,
            "rpd": limit.requests_per_day,
            "tpm": limit.tokens_per_minute,
            "tpd": limit.tokens_per_day,
            "refresh_interval_hours": limit.refresh_interval_hours,
        }
    _cache_expires_at = time.monotonic() + _CACHE_TTL_SECONDS
    logger.debug(f"Rate limit cache refreshed: {len(_rate_limit_cache)} entries")


async def _ensure_cache(db) -> None:
    """Ensure rate limit cache is populated and fresh."""
    global _cache_expires_at
    if time.monotonic() < _cache_expires_at:
        return
    await refresh_rate_limit_cache(db)


def _get_limits(provider: str, model: str) -> dict | None:
    """Get cached rate limits for a provider+model. Returns None if not configured."""
    return _rate_limit_cache.get(f"{provider}:{model}")


async def check_capacity(
    provider: str, model: str, estimated_tokens: int = 0, db=None
) -> tuple[bool, str]:
    """Check if a provider+model has capacity for a request.

    Returns (has_capacity, reason_string).
    If no limits are configured, returns (True, "").
    """
    if db:
        await _ensure_cache(db)

    limits = _get_limits(provider, model)
    if not limits:
        return True, ""  # No limits configured = unlimited

    redis = await get_redis()
    refresh_hours = limits.get("refresh_interval_hours", 24)
    minute_b = _minute_bucket()
    day_b = _day_bucket(refresh_hours)

    # Check RPM
    rpm_limit = limits.get("rpm")
    if rpm_limit is not None:
        rpm_key = _key(provider, model, "rpm", minute_b)
        current_rpm = int(await redis.get(rpm_key) or 0)
        if current_rpm >= rpm_limit:
            return False, f"RPM limit reached ({current_rpm}/{rpm_limit})"

    # Check RPD
    rpd_limit = limits.get("rpd")
    if rpd_limit is not None:
        rpd_key = _key(provider, model, "rpd", day_b)
        current_rpd = int(await redis.get(rpd_key) or 0)
        if current_rpd >= rpd_limit:
            return False, f"RPD limit reached ({current_rpd}/{rpd_limit})"

    # Check TPM
    tpm_limit = limits.get("tpm")
    if tpm_limit is not None and estimated_tokens > 0:
        tpm_key = _key(provider, model, "tpm", minute_b)
        current_tpm = int(await redis.get(tpm_key) or 0)
        if current_tpm + estimated_tokens > tpm_limit:
            return False, f"TPM limit would be exceeded ({current_tpm}+{estimated_tokens}/{tpm_limit})"

    # Check TPD
    tpd_limit = limits.get("tpd")
    if tpd_limit is not None and estimated_tokens > 0:
        tpd_key = _key(provider, model, "tpd", day_b)
        current_tpd = int(await redis.get(tpd_key) or 0)
        if current_tpd + estimated_tokens > tpd_limit:
            return False, f"TPD limit would be exceeded ({current_tpd}+{estimated_tokens}/{tpd_limit})"

    return True, ""


async def record_usage(provider: str, model: str, tokens_used: int = 0, refresh_interval_hours: int = 24) -> None:
    """Record a completed request's usage in Redis counters."""
    redis = await get_redis()
    minute_b = _minute_bucket()
    day_b = _day_bucket(refresh_interval_hours)

    pipe = redis.pipeline()

    # Increment RPM counter (TTL 120s to cover current + next minute)
    rpm_key = _key(provider, model, "rpm", minute_b)
    pipe.incrby(rpm_key, 1)
    pipe.expire(rpm_key, 120)

    # Increment RPD counter
    rpd_key = _key(provider, model, "rpd", day_b)
    pipe.incrby(rpd_key, 1)
    rpd_ttl = refresh_interval_hours * 3600 + 300  # refresh window + 5 min buffer
    pipe.expire(rpd_key, rpd_ttl)

    if tokens_used > 0:
        # Increment TPM counter
        tpm_key = _key(provider, model, "tpm", minute_b)
        pipe.incrby(tpm_key, tokens_used)
        pipe.expire(tpm_key, 120)

        # Increment TPD counter
        tpd_key = _key(provider, model, "tpd", day_b)
        pipe.incrby(tpd_key, tokens_used)
        pipe.expire(tpd_key, rpd_ttl)

    await pipe.execute()


async def pre_reserve(provider: str, model: str, estimated_tokens: int = 0, refresh_interval_hours: int = 24) -> None:
    """Pre-reserve 1 request count + estimated tokens before the LLM call."""
    await record_usage(provider, model, estimated_tokens, refresh_interval_hours)


async def finalize(provider: str, model: str, estimated_tokens: int, actual_tokens: int, refresh_interval_hours: int = 24) -> None:
    """Adjust token counters after actual usage is known (correct the pre-reserved estimate)."""
    if actual_tokens == estimated_tokens:
        return  # Estimate was accurate

    diff = actual_tokens - estimated_tokens
    if diff == 0:
        return

    redis = await get_redis()
    minute_b = _minute_bucket()
    day_b = _day_bucket(refresh_interval_hours)
    rpd_ttl = refresh_interval_hours * 3600 + 300

    pipe = redis.pipeline()

    # Adjust TPM
    tpm_key = _key(provider, model, "tpm", minute_b)
    pipe.incrby(tpm_key, diff)
    pipe.expire(tpm_key, 120)

    # Adjust TPD
    tpd_key = _key(provider, model, "tpd", day_b)
    pipe.incrby(tpd_key, diff)
    pipe.expire(tpd_key, rpd_ttl)

    await pipe.execute()


async def get_current_usage(provider: str, model: str, refresh_interval_hours: int = 24) -> dict:
    """Get current usage counters for monitoring UI."""
    redis = await get_redis()
    minute_b = _minute_bucket()
    day_b = _day_bucket(refresh_interval_hours)

    rpm_key = _key(provider, model, "rpm", minute_b)
    rpd_key = _key(provider, model, "rpd", day_b)
    tpm_key = _key(provider, model, "tpm", minute_b)
    tpd_key = _key(provider, model, "tpd", day_b)

    values = await redis.mget(rpm_key, rpd_key, tpm_key, tpd_key)

    return {
        "rpm": int(values[0] or 0),
        "rpd": int(values[1] or 0),
        "tpm": int(values[2] or 0),
        "tpd": int(values[3] or 0),
    }
