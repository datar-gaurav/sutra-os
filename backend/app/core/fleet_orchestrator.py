"""Fleet Orchestrator — triage open issues across N repos and enqueue jobs.

Sutra runs in Docker so it cannot invoke `gemini` (no host OAuth access).
What it *can* do:
  - List open issues across `fleet_repos` via PyGithub
  - Ask a cheap LLM (Gemini Flash by default) to pick the top priority
  - Enqueue a FleetJob the host worker can claim

The host worker is the only thing that touches Gemini CLI itself.
"""

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.fleet import FleetJob, FleetStatus

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_branch_name(title: str, job_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"fleet/{slug}-{job_id[:8]}"


def _parse_repos() -> list[str]:
    from app.core.system_settings import sys_settings
    raw = sys_settings.get("fleet_repos") or settings.fleet_repos or ""
    return [r.strip() for r in raw.split(",") if r.strip()]


async def _github_client():
    """Return a PyGithub client using the stored GITHUB_TOKEN."""
    from github import Github
    from app.core.env_utils import get_secret
    token = (await get_secret("GITHUB_TOKEN", settings.github_token or "")).strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN not configured.")
    return Github(token)


# ─── Triage ───────────────────────────────────────────────────────────────────


async def _collect_open_issues() -> list[dict]:
    """Pull open issues across all fleet_repos. Caller filters/labels further."""
    repos = _parse_repos()
    if not repos:
        return []

    gh = await _github_client()
    out: list[dict] = []
    for repo_url in repos:
        try:
            repo = gh.get_repo(repo_url)
            for issue in repo.get_issues(state="open"):
                if issue.pull_request:
                    continue  # PRs come back from get_issues too — skip them
                out.append({
                    "repo": repo_url,
                    "number": issue.number,
                    "title": issue.title,
                    "labels": [l.name for l in issue.labels],
                    "body": (issue.body or "")[:400],
                })
        except Exception as e:
            logger.warning(f"[Fleet] failed to fetch issues for {repo_url}: {e}")
    return out


def _extract_json_object(text: str) -> dict | None:
    """Pull the first balanced {...} block out of an LLM response. Tolerates
    prose, code fences, and trailing commentary. Returns None if nothing valid."""
    s = text.strip()
    # Try whole-string parse first (cheap path)
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    # Scan for first balanced { ... } honouring string literals
    start = s.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start:i + 1]
                    try:
                        v = json.loads(candidate)
                        if isinstance(v, dict):
                            return v
                    except json.JSONDecodeError:
                        break  # malformed at this start; try next {
        start = s.find("{", start + 1)
    return None


async def _ask_triage_llm(candidates: list[dict]) -> dict | None:
    """Return {repo, number, reason} or None if no candidate is appropriate."""
    from app.core.llm_registry import llm_registry

    llm = llm_registry.get_chat_model(
        settings.fleet_triage_provider,
        settings.fleet_triage_model,
        temperature=0.0,
        max_tokens=400,
    )
    prompt = (
        "You are triaging issues across a fleet of repositories. "
        "Pick the ONE issue that is best suited for an autonomous coding "
        "agent to address in a single PR. If multiple candidates fit, prefer "
        "higher priority and smaller scope. If only one candidate exists and "
        "it is at all reasonable, pick it — do NOT abstain unless every "
        "candidate is clearly inappropriate (e.g. pure question / discussion).\n\n"
        "Respond with ONLY a JSON object — no prose, no markdown:\n"
        '  {"repo": "owner/repo", "number": 123, "reason": "<one short sentence>"}\n'
        'Or, only if every candidate is unsuitable:  {"skip": true, "reason": "..."}\n\n'
        f"Candidates:\n{json.dumps(candidates, indent=2)}"
    )
    resp = await llm.ainvoke(prompt)
    raw = resp.content if hasattr(resp, "content") else str(resp)

    pick = _extract_json_object(raw)
    if pick is None:
        logger.warning(
            "[Fleet] triage LLM returned no parseable JSON. Raw (first 1k chars): %r",
            raw[:1000],
        )
        return None
    if pick.get("skip"):
        logger.info("[Fleet] triage LLM declined: %s", pick.get("reason", ""))
        return None
    if not pick.get("repo") or not pick.get("number"):
        logger.warning("[Fleet] triage LLM returned malformed pick: %r", pick)
        return None
    return pick


async def triage_and_enqueue(db: AsyncSession) -> FleetJob | None:
    """Run one triage pass. Returns the new job or None.

    Skips entirely if the queue already has an unfinished job, so we never
    enqueue on top of in-flight work.
    """
    # Skip if any non-terminal job exists
    active = await db.execute(
        select(FleetJob).where(
            FleetJob.status.in_([
                FleetStatus.queued.value,
                FleetStatus.claimed.value,
                FleetStatus.running.value,
                FleetStatus.pushing.value,
            ])
        ).limit(1)
    )
    if active.scalars().first():
        logger.info("[Fleet] active job present, skipping triage.")
        return None

    candidates = await _collect_open_issues()
    if not candidates:
        logger.info("[Fleet] no open issues across fleet_repos.")
        return None

    pick = await _ask_triage_llm(candidates)
    if not pick:
        return None

    # Confirm the pick exists in the candidate list (LLM occasionally hallucinates)
    matched = next(
        (c for c in candidates
         if c["repo"] == pick["repo"] and c["number"] == pick["number"]),
        None,
    )
    if not matched:
        logger.warning(f"[Fleet] LLM picked unknown issue {pick}")
        return None

    job = FleetJob(
        repo_url=matched["repo"],
        issue_ref=f"#{matched['number']}",
        title=matched["title"][:200],
        prompt=(
            f"Fix issue #{matched['number']} in {matched['repo']}.\n\n"
            f"Title: {matched['title']}\n\n"
            f"Description:\n{matched['body']}\n\n"
            "Make minimal changes. Do not refactor unrelated code. "
            "Write or update tests if the repo has a test framework."
        ),
        status=FleetStatus.queued.value,
        triage={
            "reason": pick.get("reason"),
            "candidate_count": len(candidates),
            "model": f"{settings.fleet_triage_provider}/{settings.fleet_triage_model}",
        },
        decisions=[],
        run_log=[],
    )
    db.add(job)
    await db.flush()
    job.branch_name = make_branch_name(matched["title"], job.id)
    await db.commit()
    await db.refresh(job)
    logger.info(f"[Fleet] enqueued {job.id} → {job.repo_url} {job.issue_ref}")

    # Fire the host worker immediately — no waiting for the watchdog tick.
    from app.core.fleet_dispatcher import dispatch_to_host
    await dispatch_to_host(reason=f"triage-enqueued-{job.id[:8]}")

    return job


# ─── Claim (host worker → /api/fleet/claim) ───────────────────────────────────


async def claim_next_job(db: AsyncSession, worker_id: str) -> FleetJob | None:
    """Atomically claim the oldest queued job. Returns None if queue empty.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple workers (even though
    fleet_max_concurrent caps at 1 by default) cannot grab the same row.
    """
    stmt = (
        select(FleetJob)
        .where(FleetJob.status == FleetStatus.queued.value)
        .order_by(FleetJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await db.execute(stmt)
    job = result.scalars().first()
    if not job:
        return None

    job.status = FleetStatus.claimed.value
    job.claimed_by = worker_id
    job.claimed_at = datetime.now(timezone.utc).isoformat()
    await db.commit()
    await db.refresh(job)
    return job


# ─── Worker callbacks ─────────────────────────────────────────────────────────


async def append_run_log(db: AsyncSession, job_id: str, lines: list[dict]) -> None:
    """Append batched log lines coming from the host worker.

    Each entry: {timestamp, stream: "stdout"|"stderr"|"event", line: str}
    """
    job = await db.get(FleetJob, job_id)
    if not job:
        return
    log = list(job.run_log or [])
    log.extend(lines)
    job.run_log = log[-2000:]   # keep last 2k lines, drop the rest
    await db.commit()


async def record_decision(db: AsyncSession, job_id: str, decision: str, detail: str = "") -> None:
    """Worker records an important decision / note. Posted as a PR comment later."""
    job = await db.get(FleetJob, job_id)
    if not job:
        return
    items = list(job.decisions or [])
    items.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "detail": detail,
    })
    job.decisions = items
    await db.commit()


async def update_status(
    db: AsyncSession, job_id: str, status: str,
    error: str | None = None, pr_url: str | None = None, pr_number: int | None = None,
) -> None:
    if status not in {s.value for s in FleetStatus}:
        raise ValueError(f"invalid fleet status: {status}")
    job = await db.get(FleetJob, job_id)
    if not job:
        return
    job.status = status
    if error is not None:
        job.error_log = error
    if pr_url is not None:
        job.pr_url = pr_url
    if pr_number is not None:
        job.pr_number = pr_number
    await db.commit()


