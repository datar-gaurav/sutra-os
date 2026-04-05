"""Forge Engine — workspace management and coding execution for ForgeRequests.

Handles:
  - Cloning repos into isolated workspaces
  - Branch creation
  - Running an LLM-powered agentic coding loop (any provider/model)
  - Detecting and running tests
  - Committing + pushing the finished branch
  - Workspace cleanup
"""

import asyncio
import json
import logging
import os
import re
import shutil
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


# ─── Concurrency gate ─────────────────────────────────────────────────────────

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.forge_max_concurrent)
    return _semaphore


# ─── Workspace helpers ────────────────────────────────────────────────────────


def _workspace_root() -> Path:
    root = Path(settings.forge_workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def workspace_for(request_id: str) -> Path:
    return _workspace_root() / request_id


def make_branch_name(title: str, request_id: str) -> str:
    """Generate a safe git branch name from a title."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:40]
    short = request_id[:8]
    return f"forge/{slug}-{short}"


async def clone_repo(repo_url: str, workspace_path: Path) -> None:
    """Clone a GitHub repo into workspace_path using GITHUB_TOKEN (full clone)."""
    from app.core.env_utils import get_secret
    token = (await get_secret("GITHUB_TOKEN", settings.github_token or "")).strip()
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured.")

    workspace_path.mkdir(parents=True, exist_ok=True)
    # Embed token in URL using Basic auth (x-oauth-basic is the standard GitHub HTTPS pattern)
    clone_url = f"https://x-oauth-basic:{token}@github.com/{repo_url}.git"

    env = {
        **os.environ,
        "GIT_ASKPASS": "echo",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", clone_url, str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Redact the token from the error before raising
        err = stderr.decode().replace(token, "<REDACTED>")
        raise RuntimeError(f"git clone failed: {err}")


async def create_branch(workspace_path: Path, branch_name: str) -> None:
    """Create and checkout a new branch in the workspace."""
    proc = await asyncio.create_subprocess_exec(
        "git", "checkout", "-b", branch_name,
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git checkout -b failed: {stderr.decode()}")


async def get_repo_tree(workspace_path: Path, max_depth: int = 4) -> str:
    """Return a text tree of the repo (excluding .git, node_modules, __pycache__)."""
    proc = await asyncio.create_subprocess_exec(
        "find", ".", "-not", "-path", "*/.git/*",
        "-not", "-path", "*/node_modules/*",
        "-not", "-path", "*/__pycache__/*",
        "-not", "-path", "*/.next/*",
        "-maxdepth", str(max_depth),
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode()


async def _get_github_identity() -> tuple[str, str]:
    """Return (name, email) of the GitHub token owner via the API."""
    from app.core.env_utils import get_secret
    token = (await get_secret("GITHUB_TOKEN", settings.github_token or "")).strip()
    if token:
        try:
            from github import Github
            gh = Github(token)
            user = gh.get_user()
            name = user.name or user.login
            # GitHub's verified noreply email is always associated with the account
            email = f"{user.id}+{user.login}@users.noreply.github.com"
            return name, email
        except Exception:
            pass
    return "sutra-forge", "sutra-forge@users.noreply.github.com"


async def commit_all(workspace_path: Path, message: str) -> None:
    """Stage all changes and commit."""
    author_name, author_email = await _get_github_identity()
    for cmd in [
        ["git", "config", "user.email", author_email],
        ["git", "config", "user.name", author_name],
        ["git", "add", "-A"],
        ["git", "commit", "--allow-empty", "-m", message],
    ]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 and "nothing to commit" not in stderr.decode():
            raise RuntimeError(f"git command {cmd[1]} failed: {stderr.decode()}")


async def push_branch(workspace_path: Path, branch_name: str) -> None:
    """Push the branch to origin (token is already embedded in the remote URL from clone)."""
    proc = await asyncio.create_subprocess_exec(
        "git", "push", "origin", branch_name,
        cwd=str(workspace_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_ASKPASS": "echo", "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"},
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git push failed: {stderr.decode()}")


def cleanup_workspace(workspace_path: Path) -> None:
    """Remove workspace directory."""
    try:
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
    except Exception as e:
        logger.warning(f"Failed to clean up workspace {workspace_path}: {e}")


# ─── LLM builder ──────────────────────────────────────────────────────────────


def _build_coding_llm(provider: str, model: str):
    """Build a chat model for coding using the LLM registry."""
    from app.core.llm_registry import llm_registry

    llm = llm_registry.get_chat_model(
        provider, model, temperature=0.0, max_tokens=8192, streaming=True
    )
    if hasattr(llm, "max_retries"):
        llm.max_retries = settings.forge_rate_limit_max_retries
    return llm


# ─── Plan generation ──────────────────────────────────────────────────────────


async def generate_plan(
    repo_url: str,
    description: str,
    workspace_path: Path,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """Use an LLM to analyse the repo and produce an implementation plan.

    Returns a dict: {summary, steps: [{file, action, description}]}
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # Use shallow depth to keep the tree small; large repos at depth 4 can overflow context
    tree = await get_repo_tree(workspace_path, max_depth=2)
    tree_snippet = tree[:3000]

    provider = provider or settings.forge_default_provider
    model = model or settings.forge_default_model
    llm = _build_coding_llm(provider, model)

    system = (
        "You are a senior software engineer planning a feature implementation.\n"
        "Given the repository file tree and a feature description, produce a JSON plan.\n"
        "Return ONLY valid JSON with this shape:\n"
        '{"summary": "one-sentence summary", '
        '"steps": [{"file": "path/to/file", "action": "create|modify|delete", '
        '"description": "what to do"}]}\n'
        "Be specific about file paths. Limit to the minimum set of changes."
    )

    human = (
        f"Repository: {repo_url}\n\n"
        f"File tree (top 2 levels):\n{tree_snippet}\n\n"
        f"Feature request:\n{description}"
    )

    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
    raw = response.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        plan = json.loads(raw)
    except Exception:
        # Fallback: wrap raw text in a minimal plan
        plan = {"summary": raw[:200], "steps": []}

    return plan


# ─── Coding engine ─────────────────────────────────────────────────────────────


async def run_coding(
    workspace_path: Path,
    plan: dict,
    description: str,
    provider: str,
    model: str,
) -> AsyncGenerator[dict, None]:
    """Run an LLM ReAct agent to implement the plan.

    Uses any provider/model via the LLM registry. Wraps with rate-limit
    error handling and exponential backoff retry.

    Yields progress events: {event: "log"|"done"|"error", message: str}
    """
    from langgraph.prebuilt import create_react_agent
    from app.tools.os_tools import (
        list_directory, read_file, write_file, run_shell_command, search_files,
    )

    tools = [list_directory, read_file, write_file, search_files, run_shell_command]

    plan_text = _format_plan(plan)
    system_prompt = (
        "You are an autonomous software engineer implementing a feature in a cloned repository.\n"
        f"The repository is already cloned at: {workspace_path}\n\n"
        "RULES:\n"
        "1. Only modify files within the workspace. Do NOT run git commands.\n"
        "2. Do NOT install packages or run servers.\n"
        "3. Follow the plan exactly. Make only the changes described.\n"
        "4. When finished, output exactly: IMPLEMENTATION_COMPLETE\n\n"
        f"Feature description:\n{description}\n\n"
        f"Implementation plan:\n{plan_text}"
    )

    inputs = {
        "messages": [
            ("system", system_prompt),
            ("user", "Please implement the feature now. Start with the first step."),
        ]
    }

    config = {"recursion_limit": settings.forge_recursion_limit}

    max_retries = settings.forge_rate_limit_max_retries
    base_delay = settings.forge_rate_limit_base_delay

    # Temporarily add the workspace to the allowed file paths so os_tools can operate
    original_allowed = settings.allowed_agent_file_paths
    ws_str = str(workspace_path)
    if original_allowed.strip():
        if ws_str not in original_allowed:
            settings.allowed_agent_file_paths = f"{original_allowed},{ws_str}"
    # else: empty means allow-all, no change needed

    try:
        for attempt in range(max_retries + 1):
            try:
                llm = _build_coding_llm(provider, model)
                agent = create_react_agent(llm, tools)

                async for state in agent.astream(inputs, config=config, stream_mode="values"):
                    last = state["messages"][-1]
                    msg_type = type(last).__name__
                    content = getattr(last, "content", "") or ""
                    tool_calls = getattr(last, "tool_calls", [])

                    # Log tool calls with their arguments
                    if tool_calls:
                        for tc in tool_calls:
                            tool_name = tc.get("name", "tool")
                            args = tc.get("args", {})
                            args_summary = ""
                            if tool_name in ("write_file", "read_file"):
                                path = args.get("path", args.get("file_path", ""))
                                args_summary = f" → {path}" if path else ""
                            elif tool_name == "run_shell_command":
                                cmd = args.get("command", "")
                                args_summary = f" → {cmd[:100]}" if cmd else ""
                            elif tool_name == "list_directory":
                                path = args.get("path", args.get("directory_path", "."))
                                args_summary = f" → {path}"
                            elif tool_name == "search_files":
                                pattern = args.get("pattern", args.get("query", ""))
                                args_summary = f" → {pattern}" if pattern else ""
                            else:
                                args_str = str(args)[:100]
                                args_summary = f" → {args_str}" if args else ""
                            yield {"event": "log", "message": f"[tool] {tool_name}{args_summary}"}

                    # Log tool results (ToolMessage)
                    if msg_type == "ToolMessage":
                        tool_name = getattr(last, "name", "tool")
                        result_preview = str(content).strip()[:500]
                        if result_preview:
                            yield {"event": "log", "message": f"[result] {tool_name}: {result_preview}"}

                    # Log AI reasoning/messages
                    if msg_type == "AIMessage" and content and content.strip() and not tool_calls:
                        if "IMPLEMENTATION_COMPLETE" in content:
                            yield {"event": "log", "message": "Implementation complete."}
                            break
                        if len(content.strip()) > 10:
                            yield {"event": "log", "message": content.strip()[:800]}

                yield {"event": "done", "message": "Coding agent finished."}
                return  # Success — exit retry loop

            except Exception as e:
                error_str = str(e).lower()
                is_rate_limit = "rate" in error_str and "limit" in error_str
                is_429 = "429" in str(e)

                if (is_rate_limit or is_429) and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    yield {"event": "log", "message": f"Rate limited. Retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})..."}
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"Coding engine error: {e}")
                yield {"event": "error", "message": str(e)}
                return
    finally:
        # Restore original allowed paths
        settings.allowed_agent_file_paths = original_allowed


# ─── Test runner ──────────────────────────────────────────────────────────────


async def detect_and_run_tests(workspace_path: Path) -> dict:
    """Detect test framework and run tests. Returns result dict.

    Detects: pytest, npm test, cargo test, go test.
    Does NOT fail the forge — just reports results.
    """
    result = {
        "framework": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "passed": None,
        "failed": None,
        "skipped": None,
    }

    ws = str(workspace_path)

    # Detect test framework
    has_pytest = (
        (workspace_path / "pytest.ini").exists()
        or (workspace_path / "conftest.py").exists()
        or (workspace_path / "setup.cfg").exists()
        or any(workspace_path.glob("test_*.py"))
        or any(workspace_path.glob("**/test_*.py"))
    )
    has_npm = (workspace_path / "package.json").exists()
    has_cargo = (workspace_path / "Cargo.toml").exists()
    has_go = any(workspace_path.glob("**/*_test.go"))

    cmd = None
    if has_pytest:
        result["framework"] = "pytest"
        cmd = ["python", "-m", "pytest", "-v", "--tb=short", "-q"]
    elif has_npm:
        # Check if test script exists in package.json
        try:
            pkg = json.loads((workspace_path / "package.json").read_text())
            if "test" in pkg.get("scripts", {}):
                result["framework"] = "npm"
                cmd = ["npm", "test", "--", "--passWithNoTests"]
        except Exception:
            pass
    elif has_cargo:
        result["framework"] = "cargo"
        cmd = ["cargo", "test"]
    elif has_go:
        result["framework"] = "go"
        cmd = ["go", "test", "./..."]

    if not cmd:
        result["framework"] = "none"
        return result

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=ws,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        result["exit_code"] = proc.returncode
        result["stdout"] = stdout.decode()[-5000:]  # cap output
        result["stderr"] = stderr.decode()[-2000:]

        # Try to parse pass/fail counts from pytest output
        if result["framework"] == "pytest":
            combined = result["stdout"] + result["stderr"]
            m = re.search(r"(\d+) passed", combined)
            if m:
                result["passed"] = int(m.group(1))
            m = re.search(r"(\d+) failed", combined)
            if m:
                result["failed"] = int(m.group(1))
            m = re.search(r"(\d+) skipped", combined)
            if m:
                result["skipped"] = int(m.group(1))

    except asyncio.TimeoutError:
        result["exit_code"] = -1
        result["stderr"] = "Test run timed out after 5 minutes."
    except Exception as e:
        result["exit_code"] = -1
        result["stderr"] = str(e)

    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _format_plan(plan: dict) -> str:
    lines = [f"Summary: {plan.get('summary', 'N/A')}", ""]
    for i, step in enumerate(plan.get("steps", []), 1):
        lines.append(f"{i}. [{step.get('action', '?').upper()}] {step.get('file', '?')}")
        lines.append(f"   {step.get('description', '')}")
    return "\n".join(lines)


def _log_entry(event: str, message: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "message": message,
    }
