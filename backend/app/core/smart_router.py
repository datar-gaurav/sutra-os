"""Smart Router — resolves the best available model for a given purpose."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.usage_tracker import check_capacity
from app.models.llm_purpose import LLMPurpose

logger = logging.getLogger(__name__)


class SmartRouterError(Exception):
    """Raised when no model slot has capacity for a request."""

    def __init__(self, purpose_name: str, reasons: list[str]):
        self.purpose_name = purpose_name
        self.reasons = reasons
        super().__init__(
            f"All model slots exhausted for purpose '{purpose_name}': "
            + "; ".join(reasons)
        )


async def resolve_model(
    purpose_id: str,
    estimated_tokens: int,
    db: AsyncSession,
    exclude: set[tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Walk priority slots for a purpose, return first model with capacity.

    Args:
        purpose_id: The purpose to resolve a model for.
        estimated_tokens: Estimated token count for capacity checking.
        db: Database session.
        exclude: Optional set of (provider, model) tuples to skip
                 (e.g. models that failed at runtime).

    Returns:
        (provider, model) tuple.

    Raises:
        SmartRouterError: if all slots are exhausted or purpose not found.
    """
    exclude = exclude or set()

    purpose = await db.get(LLMPurpose, purpose_id)
    if not purpose:
        raise SmartRouterError(
            purpose_name=purpose_id,
            reasons=[f"Purpose '{purpose_id}' not found"],
        )

    slots = purpose.get_slots()
    if not slots:
        raise SmartRouterError(
            purpose_name=purpose.name,
            reasons=["No model slots configured"],
        )

    rejection_reasons: list[str] = []

    for i, slot in enumerate(slots, 1):
        provider = slot["provider"]
        model = slot["model"]

        if (provider, model) in exclude:
            rejection_reasons.append(
                f"P{i} {provider}/{model}: skipped (failed at runtime)"
            )
            continue

        has_capacity, reason = await check_capacity(
            provider, model, estimated_tokens, db=db
        )

        if has_capacity:
            if i > 1 or exclude:
                logger.info(
                    f"Purpose '{purpose.name}': fell back to P{i} "
                    f"({provider}/{model})"
                )
            return provider, model

        rejection_reasons.append(f"P{i} {provider}/{model}: {reason}")
        logger.debug(f"Purpose '{purpose.name}' P{i} rejected: {reason}")

    raise SmartRouterError(
        purpose_name=purpose.name,
        reasons=rejection_reasons,
    )
