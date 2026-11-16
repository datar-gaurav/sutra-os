"""CodeExecutor selection, and fleet → Forge mirroring for Shakha-run jobs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core import fleet_orchestrator as fleet
from app.core.code_executor import CodeExecutorUnavailable, get_executor
from app.models.fleet import FleetJob


# ─── Selection ───────────────────────────────────────────────────────────────


def test_executor_selection_and_fail_closed():
    assert get_executor("builtin").name == "builtin"
    assert get_executor("builtin").reviews_plan is True
    assert get_executor("shakha").reviews_plan is False
    assert get_executor("disabled").availability()[0] is False
    # A typo must never fall through to running code.
    assert get_executor("shakah").name == "disabled"
    assert get_executor(" Shakha ").name == "shakha"


def test_builtin_is_default():
    from app.config import Settings

    assert Settings.model_fields["code_executor"].default == "builtin"


async def test_disabled_refuses_to_start():
    with pytest.raises(CodeExecutorUnavailable):
        await get_executor("disabled").start("f1")


def test_shakha_needs_fleet_worker_token():
    with patch("app.core.code_executor.shakha.settings") as s:
        s.fleet_worker_token = ""
        ok, reason = get_executor("shakha").availability()
    assert ok is False and "FLEET_WORKER_TOKEN" in reason


def test_plan_routes_refuse_when_executor_reviews_itself():
    from app.api.routes import forge as forge_routes

    with patch.object(forge_routes, "get_executor", return_value=get_executor("shakha")):
        with pytest.raises(HTTPException) as e:
            forge_routes._plan_reviewing_executor()
    assert e.value.status_code == 409


# ─── Fleet claim ─────────────────────────────────────────────────────────────


async def test_old_workers_only_claim_gemini_jobs():
    db = SimpleNamespace(execute=AsyncMock())
    db.execute.return_value.scalars = lambda: SimpleNamespace(first=lambda: None)
    await fleet.claim_next_job(db, "w1")
    sql = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "runner IN ('gemini')" in sql

    await fleet.claim_next_job(db, "w1", ["gemini", "shakha"])
    sql = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "runner IN ('gemini', 'shakha')" in sql


# ─── Status mirroring ────────────────────────────────────────────────────────


def _db(job, req):
    objects = {(FleetJob, job.id): job}
    if req is not None:
        from app.models.forge import ForgeRequest

        objects[(ForgeRequest, req.id)] = req

    async def get(model, key):
        return objects.get((model, key))

    return SimpleNamespace(get=get, commit=AsyncMock())


def _job(**kw):
    base = dict(id="j1", status="claimed", error_log=None, pr_url=None, pr_number=None,
                external_ref=None, forge_request_id="f1", runner="shakha")
    base.update(kw)
    return SimpleNamespace(**base)


def _req(**kw):
    base = dict(id="f1", status="coding", pr_url=None, pr_number=None, error_log=None, coding_log=[])
    base.update(kw)
    return SimpleNamespace(**base)


async def test_pr_and_external_ref_are_mirrored_to_forge():
    job, req = _job(), _req()
    with patch("app.core.code_executor.broadcast_forge") as bc:
        await fleet.update_status(_db(job, req), "j1", "running", external_ref="task_X")
        await fleet.update_status(_db(job, req), "j1", "running", external_ref="task_Y")
        await fleet.update_status(_db(job, req), "j1", "pr_created", pr_url="https://gh/pr/7", pr_number=7)
    assert job.external_ref == "task_X", "the runner id is set once, never overwritten"
    assert req.status == "pr_created"
    assert (req.pr_url, req.pr_number) == ("https://gh/pr/7", 7)
    assert any("https://gh/pr/7" in e["message"] for e in req.coding_log)
    bc.assert_called_with("f1", "pr_created")


async def test_failure_error_reaches_forge():
    job, req = _job(), _req()
    with patch("app.core.code_executor.broadcast_forge"):
        await fleet.update_status(_db(job, req), "j1", "failed", error="checks failed")
    assert req.status == "failed" and req.error_log == "checks failed"


async def test_cancel_wins_over_late_worker_progress():
    job, req = _job(status="cancelled"), _req(status="cancelled")
    with patch("app.core.code_executor.broadcast_forge"):
        await fleet.update_status(_db(job, req), "j1", "running", note="still going")
    assert job.status == "cancelled"
    assert req.status == "cancelled" and req.coding_log == []


async def test_notes_are_logged_without_status_change():
    job, req = _job(status="running"), _req()
    with patch("app.core.code_executor.broadcast_forge"):
        await fleet.update_status(_db(job, req), "j1", "running", note="Shakha: awaiting your plan approval")
    assert req.coding_log[-1]["message"] == "Shakha: awaiting your plan approval"


async def test_plain_fleet_jobs_do_not_touch_forge():
    job = _job(runner="gemini", forge_request_id=None)
    await fleet.update_status(_db(job, None), "j1", "pr_created", pr_url="u")
    assert job.status == "pr_created"


async def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        await fleet.update_status(_db(_job(), _req()), "j1", "exploded")
