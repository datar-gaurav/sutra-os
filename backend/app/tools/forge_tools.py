"""Forge agent tools — given to the built-in Forge agent for autonomous feature building."""

import json
import logging
from datetime import datetime, timezone

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

FORGE_TOOL_IDS: set[str] = {
    "forge_start",
    "forge_generate_plan",
    "forge_execute_plan",
    "forge_create_pr",
    "forge_cancel",
}


def create_forge_tools(creator_user_id: str | None = None):
    """Return forge tool instances bound to the given user."""

    @tool
    async def forge_start(repo_url: str, description: str, llm_provider: str = "groq", llm_model: str = "qwen/qwen3-32b") -> str:
        """Start a new forge request: clone the repo, generate an implementation plan.

        Args:
            repo_url: GitHub repository in 'owner/repo' format (e.g. 'acme/my-app').
            description: Full natural-language description of the feature to implement.
            llm_provider: LLM provider to use for coding (default: 'groq'). E.g. 'openai', 'anthropic', 'google', 'groq'.
            llm_model: LLM model to use for coding (default: 'qwen/qwen3-32b').
        """
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import (
            clone_repo, create_branch, generate_plan,
            make_branch_name, workspace_for,
        )

        async with async_session_factory() as db:
            req = ForgeRequest(
                title=description[:80],
                description=description,
                repo_url=repo_url,
                llm_provider=llm_provider,
                llm_model=llm_model,
                status=ForgeStatus.planning.value,
                creator_user_id=creator_user_id,
                source_channel="agent",
                coding_log=[],
                plan_feedback=[],
            )
            db.add(req)
            await db.flush()
            await db.refresh(req)

            branch = make_branch_name(description, req.id)
            workspace = workspace_for(req.id)
            req.branch_name = branch
            req.workspace_path = str(workspace)

            # Clone repo
            _append_log(req, "log", f"Cloning {repo_url}...")
            try:
                await clone_repo(repo_url, workspace)
                await create_branch(workspace, branch)
                _append_log(req, "log", "Repo cloned, branch created.")
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)
                await db.commit()
                return json.dumps({"error": f"Clone failed: {e}", "forge_request_id": req.id})

            # Generate plan
            _append_log(req, "log", "Generating implementation plan...")
            try:
                plan = await generate_plan(repo_url, description, workspace, llm_provider, llm_model)
                req.plan = plan
                _append_log(req, "log", f"Plan ready: {plan.get('summary', '')}")
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)
                await db.commit()
                return json.dumps({"error": f"Plan generation failed: {e}", "forge_request_id": req.id})

            req.status = ForgeStatus.awaiting_plan_approval.value
            await db.commit()

            # Broadcast to UI
            _broadcast_forge_update(req.id, req.status)

            return json.dumps({
                "forge_request_id": req.id,
                "status": req.status,
                "branch": branch,
                "plan": plan,
                "message": "Plan generated. Awaiting user approval to proceed with coding.",
            })

    @tool
    async def forge_generate_plan(forge_request_id: str, feedback: str = "") -> str:
        """Re-generate the implementation plan, optionally incorporating user feedback.

        Args:
            forge_request_id: The ID of the ForgeRequest to update.
            feedback: Optional user feedback to incorporate into the revised plan.
        """
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import generate_plan, workspace_for
        from pathlib import Path

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_request_id)
            if not req:
                return json.dumps({"error": "ForgeRequest not found"})

            workspace = Path(req.workspace_path) if req.workspace_path else workspace_for(req.id)

            description = req.description
            if feedback:
                description = f"{req.description}\n\nUser feedback: {feedback}"
                rounds = list(req.plan_feedback or [])
                rounds.append({"round": len(rounds) + 1, "feedback": feedback})
                req.plan_feedback = rounds

            _append_log(req, "log", "Revising plan...")
            try:
                plan = await generate_plan(req.repo_url, description, workspace, req.llm_provider, req.llm_model)
                req.plan = plan
                req.status = ForgeStatus.awaiting_plan_approval.value
                await db.commit()
                _broadcast_forge_update(req.id, req.status)
                return json.dumps({
                    "forge_request_id": req.id,
                    "plan": plan,
                    "message": "Plan revised. Awaiting user approval.",
                })
            except Exception as e:
                await db.commit()
                return json.dumps({"error": str(e)})

    @tool
    async def forge_execute_plan(forge_request_id: str) -> str:
        """Execute the approved implementation plan using the configured LLM provider/model.

        This acquires a concurrency slot and runs the coding agent.
        Progress is streamed and stored in coding_log.
        After coding, tests are run and results stored.

        Args:
            forge_request_id: The ID of the approved ForgeRequest.
        """
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import (
            run_coding, detect_and_run_tests,
            workspace_for, _get_semaphore,
        )
        from pathlib import Path

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_request_id)
            if not req:
                return json.dumps({"error": "ForgeRequest not found"})
            if not req.plan:
                return json.dumps({"error": "No plan found. Call forge_start first."})

            req.status = ForgeStatus.coding.value
            await db.commit()
            _broadcast_forge_update(req.id, req.status)

        # Run coding outside the DB session (can take minutes)
        semaphore = _get_semaphore()
        async with semaphore:
            workspace = Path(req.workspace_path) if req.workspace_path else workspace_for(req.id)
            provider = req.llm_provider
            model = req.llm_model
            plan = req.plan
            desc = req.description

            log_entries = list(req.coding_log or [])
            error_msg = None

            async for event in run_coding(workspace, plan, desc, provider, model):
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event": event["event"],
                    "message": event["message"],
                }
                log_entries.append(entry)

                # Persist progress incrementally
                async with async_session_factory() as db:
                    req2 = await db.get(ForgeRequest, forge_request_id)
                    if req2:
                        req2.coding_log = log_entries
                        await db.commit()

                if event["event"] == "error":
                    error_msg = event["message"]
                    break

        async with async_session_factory() as db:
            req3 = await db.get(ForgeRequest, forge_request_id)
            if req3:
                if error_msg:
                    req3.status = ForgeStatus.failed.value
                    req3.error_log = error_msg
                    await db.commit()
                    _broadcast_forge_update(req3.id, req3.status)
                    return json.dumps({"error": error_msg, "forge_request_id": forge_request_id})

                # Run tests
                req3.status = ForgeStatus.testing.value
                _append_log(req3, "log", "Running tests...")
                await db.commit()
                _broadcast_forge_update(req3.id, req3.status)

        try:
            test_results = await detect_and_run_tests(workspace)
        except Exception as e:
            test_results = {"framework": "error", "exit_code": -1, "stderr": str(e)}

        async with async_session_factory() as db:
            req4 = await db.get(ForgeRequest, forge_request_id)
            if req4:
                req4.test_results = test_results
                req4.status = ForgeStatus.coding.value  # back to coding until PR
                _append_log(req4, "log", f"Tests done: {test_results.get('framework', 'none')}, exit={test_results.get('exit_code')}")
                await db.commit()
                _broadcast_forge_update(req4.id, req4.status)

        return json.dumps({
            "forge_request_id": forge_request_id,
            "test_results": test_results,
            "message": "Coding and testing complete. Call forge_create_pr to commit changes and open a PR.",
        })

    @tool
    async def forge_create_pr(forge_request_id: str) -> str:
        """Commit all changes, push the branch, and open a GitHub pull request.

        Includes test results in the PR body if available.

        Args:
            forge_request_id: The ID of the ForgeRequest after coding is complete.
        """
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import commit_all, push_branch, workspace_for
        from pathlib import Path

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_request_id)
            if not req:
                return json.dumps({"error": "ForgeRequest not found"})

            workspace = Path(req.workspace_path) if req.workspace_path else workspace_for(req.id)
            branch = req.branch_name
            plan_summary = (req.plan or {}).get("summary", req.title)
            test_results = req.test_results

            _append_log(req, "log", "Committing and pushing changes...")

            try:
                await commit_all(workspace, f"feat: {plan_summary}\n\nGenerated by Sutra Forge")
                await push_branch(workspace, branch)
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)
                await db.commit()
                return json.dumps({"error": f"Push failed: {e}"})

            # Build PR body with test results
            test_section = ""
            if test_results and test_results.get("framework") not in (None, "none", "error"):
                fw = test_results.get("framework")
                ec = test_results.get("exit_code")
                test_section = f"\n\n## Test Results\n- Framework: {fw}\n- Exit code: {ec}"
                if test_results.get("passed") is not None:
                    test_section += f"\n- Passed: {test_results['passed']}"
                if test_results.get("failed") is not None:
                    test_section += f"\n- Failed: {test_results['failed']}"
                if test_results.get("skipped") is not None:
                    test_section += f"\n- Skipped: {test_results['skipped']}"

            # Open PR via PyGithub
            try:
                from github import Github
                from app.config import settings as cfg
                from app.core.env_utils import get_secret
                gh = Github(await get_secret("GITHUB_TOKEN", cfg.github_token or ""))
                repo = gh.get_repo(req.repo_url)
                pr_body = (
                    f"## Summary\n{plan_summary}\n\n"
                    f"**Feature request:**\n{req.description}"
                    f"{test_section}\n\n"
                    f"---\n🤖 Generated by Sutra Forge"
                )
                pr = repo.create_pull(
                    title=f"feat: {req.title}",
                    body=pr_body,
                    head=branch,
                    base=repo.default_branch,
                )
                req.pr_url = pr.html_url
                req.pr_number = pr.number
                req.status = ForgeStatus.completed.value
                _append_log(req, "log", f"PR #{pr.number} created: {pr.html_url}")
            except Exception as e:
                req.status = ForgeStatus.failed.value
                req.error_log = str(e)
                await db.commit()
                return json.dumps({"error": f"PR creation failed: {e}"})

            await db.commit()
            _broadcast_forge_update(req.id, req.status)

            return json.dumps({
                "forge_request_id": req.id,
                "pr_url": req.pr_url,
                "pr_number": req.pr_number,
                "message": "PR created successfully. User can review and merge on GitHub.",
            })

    @tool
    async def forge_cancel(forge_request_id: str, reason: str = "") -> str:
        """Cancel a forge request and clean up the workspace.

        Args:
            forge_request_id: The ID of the ForgeRequest to cancel.
            reason: Optional reason for cancellation.
        """
        from app.db.session import async_session_factory
        from app.models.forge import ForgeRequest, ForgeStatus
        from app.core.forge_engine import cleanup_workspace, workspace_for
        from pathlib import Path

        async with async_session_factory() as db:
            req = await db.get(ForgeRequest, forge_request_id)
            if not req:
                return json.dumps({"error": "ForgeRequest not found"})

            req.status = ForgeStatus.cancelled.value
            if reason:
                req.error_log = f"Cancelled: {reason}"
            await db.commit()

            # Clean up workspace
            ws = Path(req.workspace_path) if req.workspace_path else workspace_for(req.id)
            cleanup_workspace(ws)

            _broadcast_forge_update(req.id, req.status)

            return json.dumps({
                "forge_request_id": req.id,
                "status": "cancelled",
                "message": "Forge request cancelled and workspace cleaned up.",
            })

    return [
        forge_start,
        forge_generate_plan,
        forge_execute_plan,
        forge_create_pr,
        forge_cancel,
    ]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _append_log(req, event: str, message: str) -> None:
    """Append a log entry to req.coding_log in-place."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "message": message,
    }
    req.coding_log = list(req.coding_log or []) + [entry]


def _broadcast_forge_update(forge_request_id: str, status: str) -> None:
    """Fire-and-forget WebSocket broadcast for forge status changes."""
    import asyncio

    async def _do():
        try:
            from app.api.websocket import ws_manager
            await ws_manager.broadcast({
                "type": "forge_update",
                "forge_request_id": forge_request_id,
                "status": status,
            })
        except Exception:
            pass

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_do())
    except Exception:
        pass


async def _send_telegram_forge_notification(req, is_plan_review: bool) -> None:
    """Send an inline-keyboard message to the Telegram chat."""
    try:
        from app.integrations.telegram_bot import _application
        if not _application:
            return

        if is_plan_review:
            plan = req.plan or {}
            steps = plan.get("steps", [])
            steps_text = "\n".join(
                f"{i+1}. [{s.get('action','?').upper()}] {s.get('file','?')}: {s.get('description','')}"
                for i, s in enumerate(steps[:8])
            )
            text = (
                f"🔧 *Forge Plan Ready*\n"
                f"*{req.title}*\n"
                f"Repo: `{req.repo_url}`\n\n"
                f"📋 *Plan:*\n{steps_text or plan.get('summary','')}\n\n"
                f"Reply with approval decision:"
            )
            callback_prefix = f"forge_plan_{req.id}"
        else:
            text = (
                f"✅ *PR Created*\n"
                f"*{req.title}*\n"
                f"PR: {req.pr_url}\n\n"
                f"Review and merge on GitHub."
            )
            callback_prefix = f"forge_pr_{req.id}"

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"{callback_prefix}_approve"),
                InlineKeyboardButton("✏️ Suggest Changes", callback_data=f"{callback_prefix}_feedback"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"{callback_prefix}_cancel"),
            ]
        ])

        from app.integrations.telegram_bot import escape_markdown
        await _application.bot.send_message(
            chat_id=req.telegram_chat_id,
            text=escape_markdown(text),
            parse_mode="MarkdownV2",
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"Failed to send Telegram forge notification: {e}")
