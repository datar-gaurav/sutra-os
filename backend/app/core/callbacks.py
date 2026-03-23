"""Langchain callbacks for tracking LLM model usage and enforcing limits."""

import datetime
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult, LLMResult
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.usage import ModelUsage, ModelLimit
from app.config import settings

logger = logging.getLogger(__name__)


class ProviderLimitExceeded(Exception):
    """Exception raised when a provider's limits are exceeded."""
    pass


class UsageCallbackHandler(AsyncCallbackHandler):
    """
    A Langchain callback handler that intercepts LLM calls to:
    1. Check if the provider's specific model limit has been exceeded.
    2. Record the usage of the specific provider and model.
    3. Capture token counts for cost calculation.
    """
    raise_error: bool = True
    tokens_used: int = 0

    def __init__(self):
        super().__init__()
        self.raise_error = True
        self.tokens_used = 0
        # We don't maintain a session directly since we might be called
        # concurrently, we'll spawn ad-hoc async paths via sessionmaker.

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when chat model starts running."""
        
        provider = None
        model = None

        if tags:
            for tag in tags:
                if tag.startswith("provider:"):
                    provider = tag.split(":", 1)[1]
                elif tag.startswith("model:"):
                    model = tag.split(":", 1)[1]

        if not provider or not model:
            # We didn't tag it properly, so we skip usage tracking
            logger.debug(f"Missing tracking tags in tags: {tags}")
            return

        today = datetime.datetime.now(datetime.timezone.utc).date()

        async with async_session_factory() as session:
            # 1. Check Limits (search for exact model match, then fallback to wildcard)
            limit_stmt = select(ModelLimit).where(
                ModelLimit.provider == provider,
                ModelLimit.model.in_([model, "*"])
            )
            result = await session.execute(limit_stmt)
            limits = result.scalars().all()
            
            # Prefer exact model limit, else fallback to wildcard '*'
            model_limit = next((l for l in limits if l.model == model), None)
            if not model_limit:
                model_limit = next((l for l in limits if l.model == "*"), None)

            # Get exact usage for this provider/model today
            usage_stmt = select(ModelUsage).where(
                ModelUsage.provider == provider, 
                ModelUsage.model == model,
                ModelUsage.usage_date == today
            )
            result = await session.execute(usage_stmt)
            specific_usage = result.scalar_one_or_none()
            
            total_model_usage_today = specific_usage.request_count if specific_usage else 0

            if model_limit and total_model_usage_today >= model_limit.daily_limit:
                logger.warning(
                    f"Model limit exceeded for {provider}/{model}: "
                    f"{total_model_usage_today}/{model_limit.daily_limit} used today."
                )
                # Raising an exception here will trigger the fallback mechanism
                # configured natively in langchain through .with_fallbacks()
                raise ProviderLimitExceeded(
                    f"Daily limit of {model_limit.daily_limit} reached for provider '{provider}' and model '{model}'"
                )

            # 2. Record Usage (UPSERT)
            if specific_usage:
                # Increment existing
                specific_usage.request_count += 1
            else:
                # Create new
                new_usage = ModelUsage(
                    provider=provider,
                    model=model,
                    usage_date=today,
                    request_count=1
                )
                session.add(new_usage)

            await session.commit()
            logger.debug(f"Recorded usage for {provider}/{model}. Total for this model today: {total_model_usage_today + 1}")

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Capture token counts from LLM response for cost tracking."""
        try:
            # Try llm_output dict (OpenAI, Anthropic, etc.)
            if hasattr(response, "llm_output") and response.llm_output:
                usage = (
                    response.llm_output.get("token_usage")
                    or response.llm_output.get("usage")
                    or {}
                )
                total = (
                    usage.get("total_tokens")
                    or usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )
                if total:
                    self.tokens_used = int(total)
                    return

            # Try usage_metadata on individual generation messages (newer LangChain)
            for gen_list in (response.generations or []):
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    meta = getattr(msg, "usage_metadata", None) if msg else None
                    if meta:
                        total = (
                            meta.get("total_tokens")
                            or meta.get("input_tokens", 0) + meta.get("output_tokens", 0)
                        )
                        if total:
                            self.tokens_used = int(total)
                            return
        except Exception as e:
            logger.debug(f"Failed to capture token count: {e}")
