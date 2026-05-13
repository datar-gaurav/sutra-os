"""Fleet dispatcher — signals the host-side worker daemon to run.

Sutra is in Docker; the worker daemon lives on the host (so Gemini CLI can
use the user's OAuth at ~/.gemini). Dispatch is one HTTP call:

    POST {fleet_worker_url}/run  (bearer = fleet_worker_token)

The worker is a thin daemon — it claims the next queued FleetJob from
/api/fleet/claim and runs it. We never pass job-specific data here; the
worker pulls from sutra's queue exactly like the launchd version did.

Failure modes:
  - Daemon offline / port closed → log + fall through. The watchdog cron
    re-tries on its next tick, so an enqueued job is never permanently lost.
  - 5xx from daemon → same as offline.
  - 200 → fire-and-forget; sutra does NOT block on the job lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.fleet import FleetJob, FleetStatus

logger = logging.getLogger(__name__)


async def dispatch_to_host(reason: str = "enqueue") -> bool:
    """Tell the host worker to claim+run the next job. Returns True on 2xx.

    Safe to call concurrently — the host daemon will no-op if it's already busy.
    """
    url = (settings.fleet_worker_url or "").strip().rstrip("/")
    token = (settings.fleet_worker_token or "").strip()
    if not url or not token:
        logger.debug(f"[Fleet] dispatch skipped — url/token not configured (reason={reason})")
        return False

    try:
        async with httpx.AsyncClient(timeout=settings.fleet_dispatch_timeout_sec) as client:
            r = await client.post(
                f"{url}/run",
                headers={"Authorization": f"Bearer {token}"},
                json={"reason": reason},
            )
            if 200 <= r.status_code < 300:
                logger.info(f"[Fleet] dispatched to host worker (reason={reason}, status={r.status_code})")
                return True
            logger.warning(f"[Fleet] host worker returned {r.status_code} (reason={reason}): {r.text[:200]}")
            return False
    except Exception as e:
        logger.warning(f"[Fleet] dispatch to {url} failed (reason={reason}): {e}")
        return False


def fire_dispatch_in_background(reason: str) -> None:
    """Fire-and-forget wrapper for use from sync code paths.

    Use this from places that just enqueued a job and want the worker poked
    without waiting on it. We swallow the result — the watchdog re-tries.
    """
    try:
        asyncio.create_task(dispatch_to_host(reason=reason))
    except RuntimeError:
        # No event loop — happens if called from a sync context outside FastAPI.
        # Use a fresh loop synchronously, very short timeout already enforced.
        asyncio.run(dispatch_to_host(reason=reason))


# ─── Watchdog ────────────────────────────────────────────────────────────────


async def watchdog_tick(db: AsyncSession) -> dict:
    """Look for stuck jobs and re-dispatch.

    Two conditions trigger a kick:
      1. queued jobs older than 1 minute   → the host probably missed the
         enqueue-time dispatch (offline or restarting).
      2. claimed jobs older than 30 minutes → the worker likely crashed
         mid-job. Reset them to queued and dispatch.

    Running/pushing jobs are left alone unless they're older than the run
    timeout — that's a separate concern (the worker enforces its own timeout
    and reports failure).
    """
    now = datetime.now(timezone.utc)
    kicked_queued = 0
    revived_claimed = 0

    # (1) stale queued — dispatch
    stale_queued_cutoff = now - timedelta(minutes=1)
    result = await db.execute(
        select(FleetJob).where(
            FleetJob.status == FleetStatus.queued.value,
            FleetJob.created_at < stale_queued_cutoff,
        ).limit(1)
    )
    if result.scalars().first():
        ok = await dispatch_to_host(reason="watchdog-stale-queue")
        if ok:
            kicked_queued = 1

    # (2) stale claimed — revive
    # claimed_at is stored as ISO string (see model). Parse loosely.
    revive_cutoff = now - timedelta(minutes=30)
    result = await db.execute(
        select(FleetJob).where(FleetJob.status == FleetStatus.claimed.value)
    )
    for job in result.scalars().all():
        if not job.claimed_at:
            continue
        try:
            claimed = datetime.fromisoformat(job.claimed_at)
        except ValueError:
            continue
        if claimed < revive_cutoff:
            logger.warning(f"[Fleet] reviving stuck claimed job {job.id} (claimed_at={job.claimed_at})")
            job.status = FleetStatus.queued.value
            job.claimed_by = None
            job.claimed_at = None
            revived_claimed += 1
    if revived_claimed:
        await db.commit()
        await dispatch_to_host(reason="watchdog-revived")

    return {"kicked_queued": kicked_queued, "revived_claimed": revived_claimed}


# ─── Health probe (used by the UI to show online/offline) ─────────────────────


async def probe_host_worker() -> dict:
    """GET <worker>/health — non-blocking, returns a small dict for the UI."""
    url = (settings.fleet_worker_url or "").strip().rstrip("/")
    if not url:
        return {"online": False, "error": "fleet_worker_url not set"}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/health")
            if r.status_code == 200:
                payload = r.json()
                return {"online": True, **payload}
            return {"online": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"online": False, "error": str(e)[:200]}
