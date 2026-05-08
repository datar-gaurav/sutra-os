"""Shared httpx client config for job-discovery adapters.

Centralized so we get one User-Agent, one timeout policy, one set of
connection limits, and easy retry behaviour across every adapter.
"""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
DEFAULT_LIMITS = httpx.Limits(max_connections=8, max_keepalive_connections=4)


def make_client() -> httpx.AsyncClient:
    """Construct an AsyncClient with our default headers / timeouts."""
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        limits=DEFAULT_LIMITS,
        headers={
            "User-Agent": settings.job_discovery_user_agent,
            "Accept": "application/json",
        },
        follow_redirects=True,
    )


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    max_retries: int = 3,
) -> dict | list | None:
    """GET with retry on 429/5xx. Returns parsed JSON or None on failure."""
    delay = 1.0
    last_status: int | None = None
    for attempt in range(max_retries + 1):
        try:
            r = await client.get(url, params=params)
            last_status = r.status_code
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception as e:  # malformed JSON — don't retry
                    logger.warning("Bad JSON from %s: %s", url, e)
                    return None
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt >= max_retries:
                    break
                # Exponential backoff with jitter
                sleep_for = delay + random.uniform(0, 0.5)
                logger.info(
                    "%s returned %d — retrying in %.1fs (attempt %d)",
                    url, r.status_code, sleep_for, attempt + 1,
                )
                await asyncio.sleep(sleep_for)
                delay *= 2
                continue
            # 4xx other than 429 — don't retry, don't even log loudly
            logger.debug("%s returned %d", url, r.status_code)
            return None
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt >= max_retries:
                logger.warning("%s transport error after %d attempts: %s", url, attempt + 1, e)
                return None
            await asyncio.sleep(delay + random.uniform(0, 0.5))
            delay *= 2
    logger.warning("%s gave up after %d attempts (last status: %s)", url, max_retries + 1, last_status)
    return None


def html_to_snippet(html: str | None, max_chars: int = 2000) -> str | None:
    """Strip HTML tags and collapse whitespace into a snippet capped at max_chars."""
    if not html:
        return None
    import re as _re
    text = _re.sub(r"<[^>]+>", " ", html)
    text = _re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    return text[:max_chars]
