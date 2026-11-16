"""Built-in executor: Sutra's own Forge pipeline, run in-process.

clone → generate plan → (user approves in Sutra unless auto-approved) →
agentic coding loop → tests → commit → push → PR.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.code_executor.base import CodeExecutor, append_log, broadcast_forge
from app.models.forge import ForgeRequest, ForgeStatus

logger = logging.getLogger(__name__)


class BuiltinExecutor(CodeExecutor):
    name = "builtin"
    reviews_plan = True

    async def start(self, forge_id: str, *, feedback: str = "", wait: bool = False) -> None:
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return
            req.status = ForgeStatus.planning.value
            req.error_log = None
            await db.commit()
            args = (
                req.id, req.repo_url,
                f"{req.description}\n\nUser feedback: {feedback}" if feedback else req.description,
                req.workspace_path or "", req.branch_name or "",
                req.llm_provider, req.llm_model, bool(req.auto_approve_plan),
            )
        broadcast_forge(forge_id, ForgeStatus.planning.value)
        if wait:
            await run_planning(*args)
        else:
            asyncio.create_task(run_planning(*args))

    async def execute(self, forge_id: str) -> None:
        asyncio.create_task(run_coding(forge_id))

    async def cancel(self, forge_id: str) -> None:
        from pathlib import Path

        from app.core.forge_engine import cleanup_workspace
        from app.db.session import async_session_factory

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            path = req.workspace_path if req else None
        if path:
            cleanup_workspace(Path(path))


# ─── Pipeline (moved unchanged from api/routes/forge.py) ─────────────────────


async def run_planning(
    forge_id: str, repo_url: str, description: str, workspace_path: str, branch: str,
    llm_provider: str, llm_model: str, auto_approve_plan: bool,
) -> None:
    """Background: clone (if needed) + generate plan."""
    from app.db.session import async_session_factory
    from app.core.forge_engine import clone_repo, create_branch, generate_plan, workspace_for
    from pathlib import Path

    try:
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return

            ws = Path(workspace_path) if workspace_path else workspace_for(forge_id)

            # Clone only if workspace doesn't exist yet
            if not ws.exists():
                try:
                    await clone_repo(repo_url, ws)
                    await create_branch(ws, branch)
                    append_log(req, "log", "Repo cloned, branch created.")
                except Exception as e:
                    req.status = ForgeStatus.failed.value
                    req.error_log = str(e)
                    await db.commit()
                    broadcast_forge(forge_id, req.status)
                    return

            try:
                plan = await generate_plan(repo_url, description, ws, llm_provider, llm_model)
                req.plan = plan
                append_log(req, "log", f"Plan ready: {plan.get('summary', '')}")

                if auto_approve_plan:
                    req.status = ForgeStatus.coding.value
                    append_log(req, "log", "Auto-approved plan, starting coding...")
                    await db.commit()
                    broadcast_forge(forge_id, req.status)
                    asyncio.create_task(run_coding(forge_id))
                    return
                else:
                    req.status = ForgeStatus.awaiting_plan_approval.value
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)

            await db.commit()
            broadcast_forge(forge_id, req.status)
    except Exception as e:
        logger.error(f"[Forge] _run_planning crashed for {forge_id}: {e}")
        try:
            async with async_session_factory() as db:
                req = await db.get(ForgeRequest, forge_id)
                if req and req.status == ForgeStatus.planning.value:
                    req.status = ForgeStatus.failed.value
                    req.error_log = f"Planning crashed: {e}"
                    await db.commit()
                    broadcast_forge(forge_id, req.status)
        except Exception:
            pass


async def run_coding(forge_id: str) -> None:
    """Background: execute coding plan, run tests, commit, push, open PR."""
    from app.db.session import async_session_factory
    from app.core.forge_engine import (
        run_coding, detect_and_run_tests,
        commit_all, push_branch, workspace_for, _get_semaphore,
    )
    from pathlib import Path

    semaphore = _get_semaphore()
    async with semaphore:
        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_id)
            if not req:
                return
            ws = Path(req.workspace_path) if req.workspace_path else workspace_for(forge_id)
            provider = req.llm_provider
            model = req.llm_model
            plan = req.plan
            desc = req.description
            branch = req.branch_name

        log_entries = list(req.coding_log or [])
        error_msg = None

        async for event in run_coding(ws, plan, desc, provider, model):
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": event["event"],
                "message": event["message"],
            }
            log_entries.append(entry)

            async with async_session_factory() as db:
                req2 = await db.get(ForgeRequest, forge_id)
                if req2:
                    req2.coding_log = log_entries
                    await db.commit()

            if event["event"] == "error":
                error_msg = event["message"]
                break

    async with async_session_factory() as db:
        req3 = await db.get(ForgeRequest, forge_id)
        if not req3:
            return
        if error_msg:
            req3.status = ForgeStatus.failed.value
            req3.error_log = error_msg
            await db.commit()
            broadcast_forge(forge_id, req3.status)
            return

        # Run tests
        req3.status = ForgeStatus.testing.value
        append_log(req3, "log", "Running tests...")
        await db.commit()
        broadcast_forge(forge_id, req3.status)

    try:
        test_results = await detect_and_run_tests(ws)
    except Exception as e:
        test_results = {"framework": "error", "exit_code": -1, "stderr": str(e)}

    async with async_session_factory() as db:
        req4 = await db.get(ForgeRequest, forge_id)
        if not req4:
            return
        req4.test_results = test_results
        fw = test_results.get("framework", "none")
        ec = test_results.get("exit_code")
        if fw == "none":
            append_log(req4, "log", "No test framework detected.")
        else:
            passed = test_results.get("passed")
            failed = test_results.get("failed")
            summary_parts = [f"framework={fw}", f"exit_code={ec}"]
            if passed is not None:
                summary_parts.append(f"passed={passed}")
            if failed is not None:
                summary_parts.append(f"failed={failed}")
            append_log(req4, "log", f"Tests finished: {', '.join(summary_parts)}")

        # Commit + push + open PR
        try:
            plan_summary = (req4.plan or {}).get("summary", req4.title)
            await commit_all(ws, f"feat: {plan_summary}\n\nGenerated by Sutra Forge")
            await push_branch(ws, branch)

            from github import Github
            from app.config import settings
            from app.core.env_utils import get_secret
            gh = Github(await get_secret("GITHUB_TOKEN", settings.github_token or ""))
            repo = gh.get_repo(req4.repo_url)

            # Build PR body with test results
            test_section = ""
            if fw != "none" and fw != "error":
                test_section = f"\n\n## Test Results\n- Framework: {fw}\n- Exit code: {ec}"
                if passed is not None:
                    test_section += f"\n- Passed: {passed}"
                if failed is not None:
                    test_section += f"\n- Failed: {failed}"
                skipped = test_results.get("skipped")
                if skipped is not None:
                    test_section += f"\n- Skipped: {skipped}"

            pr_body = (
                f"## Summary\n{plan_summary}\n\n"
                f"**Feature request:**\n{req4.description}"
                f"{test_section}\n\n"
                f"---\n🤖 Generated by Sutra Forge"
            )
            pr = repo.create_pull(
                title=f"feat: {req4.title}",
                body=pr_body,
                head=branch,
                base=repo.default_branch,
            )
            req4.pr_url = pr.html_url
            req4.pr_number = pr.number
            req4.status = ForgeStatus.completed.value
            append_log(req4, "log", f"PR #{pr.number} created: {pr.html_url}")
        except Exception as e:
            req4.status = ForgeStatus.failed.value
            req4.error_log = str(e)

        await db.commit()
        broadcast_forge(forge_id, req4.status)
