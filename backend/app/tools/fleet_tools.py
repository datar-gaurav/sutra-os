"""Fleet tools — enqueue and inspect fleet jobs from inside an agent."""

import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FLEET_TOOL_IDS = {
    "fleet_enqueue_job",
    "fleet_list_jobs",
}


class EnqueueJobInput(BaseModel):
    repo: str = Field(
        ...,
        description=(
            "Short repo name (e.g. 'sutra-os') or full 'owner/repo'. "
            "Short names are matched against the fleet_repos system setting."
        ),
    )
    prompt: str = Field(..., description="Instruction for the Gemini CLI worker")
    title: str = Field("", description="Short human-readable title (auto-derived from prompt if omitted)")
    issue_ref: str = Field("", description="Optional GitHub issue reference, e.g. '#42'")


class ListJobsInput(BaseModel):
    status: str = Field("", description="Filter by status: queued|claimed|running|pushing|pr_created|failed|cancelled (empty = all)")
    limit: int = Field(10, description="Max jobs to return")


def _resolve_repo(repo: str) -> tuple[str, str | None]:
    """Return (resolved_owner_repo, error_message).

    Tries exact match first, then suffix match against fleet_repos setting.
    """
    from app.core.system_settings import sys_settings
    from app.config import settings as cfg

    raw = sys_settings.get("fleet_repos") or cfg.fleet_repos or ""
    fleet_repos = [r.strip() for r in raw.split(",") if r.strip()]

    # Already a full owner/repo — pass through
    if "/" in repo:
        return repo, None

    # Match by repo-name portion (last segment after /)
    matched = next((r for r in fleet_repos if r.split("/")[-1] == repo), None)
    if matched:
        return matched, None

    if fleet_repos:
        return "", f"'{repo}' did not match any fleet_repos entry. Configured: {raw}. Pass 'owner/repo' explicitly or add it to Fleet settings."
    return "", "fleet_repos is not configured. Add repos via Settings → Fleet or set the FLEET_REPOS env var."


async def _enqueue_job(repo: str, prompt: str, title: str = "", issue_ref: str = "") -> str:
    repo_url, err = _resolve_repo(repo)
    if err:
        return json.dumps({"error": err})

    try:
        from app.db.session import async_session_factory
        from app.models.fleet import FleetJob, FleetStatus
        from app.core import fleet_orchestrator as fleet

        async with async_session_factory() as db:
            job = FleetJob(
                repo_url=repo_url,
                issue_ref=issue_ref or None,
                title=(title or prompt)[:200],
                prompt=prompt,
                status=FleetStatus.queued.value,
                decisions=[],
                run_log=[],
            )
            db.add(job)
            await db.flush()
            job.branch_name = fleet.make_branch_name(job.title, job.id)
            await db.commit()
            await db.refresh(job)

        from app.core.fleet_dispatcher import dispatch_to_host
        await dispatch_to_host(reason=f"agent-enqueued-{job.id[:8]}")

        return json.dumps({
            "status": "queued",
            "job_id": job.id,
            "repo_url": job.repo_url,
            "title": job.title,
            "branch_name": job.branch_name,
            "message": f"Fleet job queued for {job.repo_url}. Worker will claim it shortly.",
        })
    except Exception as e:
        logger.exception("fleet_enqueue_job failed")
        return json.dumps({"error": str(e)})


async def _list_jobs(status: str = "", limit: int = 10) -> str:
    try:
        from app.db.session import async_session_factory
        from app.models.fleet import FleetJob
        from sqlalchemy import select

        async with async_session_factory() as db:
            q = select(FleetJob).order_by(FleetJob.created_at.desc()).limit(limit)
            if status:
                q = q.where(FleetJob.status == status)
            result = await db.execute(q)
            jobs = result.scalars().all()

        return json.dumps([
            {
                "id": j.id,
                "repo_url": j.repo_url,
                "title": j.title,
                "status": j.status,
                "issue_ref": j.issue_ref,
                "pr_url": j.pr_url,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ], indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def create_fleet_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=_enqueue_job,
            name="fleet_enqueue_job",
            description=(
                "Enqueue a fleet job for a repository. Accepts a short repo name "
                "(e.g. 'sutra-os') or full 'owner/repo'. The Gemini CLI worker will "
                "clone the repo, execute the prompt, push a branch, and open a PR."
            ),
            args_schema=EnqueueJobInput,
        ),
        StructuredTool.from_function(
            coroutine=_list_jobs,
            name="fleet_list_jobs",
            description="List recent fleet jobs with their status, repo, and PR URL.",
            args_schema=ListJobsInput,
        ),
    ]
