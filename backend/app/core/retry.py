"""Retry logic with exponential backoff and jitter for tool calls and external services."""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import httpx

logger = logging.getLogger(__name__)

# Default set of errors that are safe to retry
RETRYABLE_ERRORS = (
    ConnectionError,
    TimeoutError,
    OSError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0       # seconds
    max_delay: float = 30.0       # seconds
    jitter: bool = True
    retryable_exceptions: tuple = RETRYABLE_ERRORS


async def retry_with_backoff(
    func: Callable[..., Coroutine],
    config: RetryConfig | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Execute an async function with exponential backoff retry.

    Usage:
        result = await retry_with_backoff(some_async_func, config, arg1, arg2, key=val)
    """
    config = config or RetryConfig()

    last_exception = None
    for attempt in range(config.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e
            if attempt == config.max_retries:
                logger.warning(
                    f"All {config.max_retries} retries exhausted for {func.__name__}: {e}"
                )
                raise
            delay = min(config.base_delay * (2 ** attempt), config.max_delay)
            if config.jitter:
                delay *= random.uniform(0.5, 1.5)
            logger.info(
                f"Retry {attempt + 1}/{config.max_retries} for {func.__name__} "
                f"after {delay:.1f}s: {type(e).__name__}: {e}"
            )
            await asyncio.sleep(delay)

    # Should never reach here, but just in case
    raise last_exception  # type: ignore[misc]
