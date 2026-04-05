"""Redis-backed refresh token blacklist (jti-based revocation)."""

from datetime import datetime, timezone

from app.core.redis_client import get_redis

_PREFIX = "token:blacklist:"


async def blacklist_token(jti: str, exp: int) -> None:
    """Add a jti to the blacklist; TTL = remaining lifetime of the token."""
    redis = await get_redis()
    remaining = exp - int(datetime.now(timezone.utc).timestamp())
    if remaining > 0:
        await redis.setex(f"{_PREFIX}{jti}", remaining, "1")


async def is_token_blacklisted(jti: str) -> bool:
    """Return True if the given jti has been revoked."""
    redis = await get_redis()
    return await redis.exists(f"{_PREFIX}{jti}") > 0
