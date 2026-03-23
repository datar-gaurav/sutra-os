"""LLM Queue — serialized model acquisition to prevent race conditions."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.smart_router import resolve_model
from app.core.usage_tracker import finalize, pre_reserve

logger = logging.getLogger(__name__)

# Global lock to serialize model resolution
_lock = asyncio.Lock()


async def acquire_model(
    purpose_id: str,
    estimated_tokens: int,
    db: AsyncSession,
    exclude: set[tuple[str, str]] | None = None,
) -> tuple[str, str, int]:
    """Resolve the best available model under lock, pre-reserve capacity.

    Returns:
        (provider, model, refresh_interval_hours) tuple.
    """
    async with _lock:
        provider, model = await resolve_model(
            purpose_id, estimated_tokens, db, exclude=exclude
        )

        # Get refresh interval from cache for pre-reservation TTL
        from app.core.usage_tracker import _get_limits
        limits = _get_limits(provider, model)
        refresh_hours = limits.get("refresh_interval_hours", 24) if limits else 24

        # Pre-reserve 1 request + estimated tokens
        await pre_reserve(provider, model, estimated_tokens, refresh_hours)

        logger.debug(
            f"Acquired {provider}/{model} for purpose {purpose_id} "
            f"(est. {estimated_tokens} tokens)"
        )
        return provider, model, refresh_hours


async def finalize_usage(
    provider: str,
    model: str,
    estimated_tokens: int,
    actual_tokens: int,
    refresh_interval_hours: int = 24,
) -> None:
    """Record actual token usage, adjusting the pre-reserved estimate."""
    await finalize(provider, model, estimated_tokens, actual_tokens, refresh_interval_hours)
