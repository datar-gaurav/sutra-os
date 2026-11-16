"""Shakha executor (optional plugin, off by default; CODE_EXECUTOR=shakha).

Sutra never talks to Shakha directly. It queues a FleetJob with
``runner="shakha"``; the fleet worker on the Mac (scripts/fleet_worker.py)
claims it and drives Shakha through the ``shakha`` command over Shakha's local
socket. Shakha plans, asks for approval, runs checks and review, and opens the
draft PR itself, so Sutra shows no plan-approval step. The worker reports back
through /api/fleet/*, and those updates are mirrored onto the ForgeRequest
(see fleet_orchestrator.update_status).

Contract with the worker (versioned by ``RUNNER``):
  FleetJob.runner          "shakha"
  FleetJob.forge_request_id  the ForgeRequest this job serves
  FleetJob.external_ref    Shakha's task id, reported by the worker
  idempotency key          the FleetJob id, so a retried create never duplicates
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.config import settings
from app.core.code_executor.base import CodeExecutor, append_log, broadcast_forge
from app.models.fleet import FleetJob, FleetStatus
from app.models.forge import ForgeRequest, ForgeStatus

logger = logging.getLogger(__name__)

RUNNER = "shakha"
_ACTIVE = (FleetStatus.queued.value, FleetStatus.claimed.value, FleetStatus.running.value,
           FleetStatus.pushing.value)


class ShakhaExecutor(CodeExecutor):
    name = "shakha"
    reviews_plan = False

    def availability(self) -> tuple[bool, str]:
        if not (settings.fleet_worker_token or "").strip():
            return False, (
                "CODE_EXECUTOR=shakha needs the fleet worker on the Mac: set FLEET_WORKER_TOKEN "
                "here and run scripts/fleet_worker.py with SHAKHA_BIN (see docs)."
            )
        return True, ""

    async def start(self, forge_id: str, *, feedback: str = "", wait: bool = False) -> None:
        self.require_available()
        from app.core.fleet_dispatcher import dispatch_to_host
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return
            existing = (await db.execute(
                select(FleetJob).where(
                    FleetJob.forge_request_id == forge_id, FleetJob.status.in_(_ACTIVE)
                )
            )).scalars().first()
            if existing:
                job_id = existing.id
            else:
                prompt = req.description + (f"\n\nUser feedback: {feedback}" if feedback else "")
                job = FleetJob(
                    repo_url=req.repo_url,
                    prompt=prompt,
                    title=req.title,
                    runner=RUNNER,
                    forge_request_id=forge_id,
                    creator_user_id=req.creator_user_id,
                    decisions=[],
                    run_log=[],
                )
                db.add(job)
                await db.flush()
                job_id = job.id
                append_log(req, "log", f"Handed to Shakha through the fleet worker (job {job_id[:8]}). "
                                       "Plan review and approvals happen in Shakha or Powerdial.")
            req.status = ForgeStatus.coding.value
            req.error_log = None
            await db.commit()

        broadcast_forge(forge_id, ForgeStatus.coding.value)
        try:
            await dispatch_to_host(reason=f"forge:{forge_id}")
        except Exception as e:  # watchdog cron retries queued jobs
            logger.warning("Shakha dispatch for %s deferred: %s", job_id, e)

    async def cancel(self, forge_id: str) -> None:
        """Mark the fleet job cancelled; the worker's sync cancels the Shakha task."""
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            jobs = (await db.execute(
                select(FleetJob).where(
                    FleetJob.forge_request_id == forge_id, FleetJob.status.in_(_ACTIVE)
                )
            )).scalars().all()
            for job in jobs:
                job.status = FleetStatus.cancelled.value
            await db.commit()
