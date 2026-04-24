"""Runtime Scripts extension for Sutra OS.

Lets agents queue work for the autonomous runtime_scripts runner (see
https://github.com/ — local path configured per-integration) by appending
tasks to its tasks.md file and firing its scripts/run.sh orchestrator.

Configure via Settings > Integrations > Extensions with the absolute path
to the runtime_scripts checkout.

Provides:
  - runtime_scripts_add_task:      append a task block under `## pending`
  - runtime_scripts_trigger_run:   fire-and-forget scripts/run.sh
  - runtime_scripts_list_tasks:    show pending / in_progress / done
  - runtime_scripts_get_status:    show active task, plan, needs-human, logs
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from langchain_core.tools import tool

EXTENSION_MANIFEST = {
    "id": "runtime_scripts",
    "name": "Runtime Scripts",
    "description": "Queue autonomous coding tasks and trigger the runtime_scripts runner (tasks.md + scripts/run.sh)",
    "icon": "workflow",
    "version": "1.0.0",
    "author": "Sutra Community",
    "credential_fields": [],
    "config_fields": [
        {
            "key": "base_path",
            "label": "runtime_scripts repo path",
            "secret": False,
            "placeholder": "/Users/you/Coding/git/runtime_scripts",
        },
    ],
    "tool_ids": [
        "runtime_scripts_add_task",
        "runtime_scripts_trigger_run",
        "runtime_scripts_list_tasks",
        "runtime_scripts_get_status",
    ],
    "is_dangerous": True,
}

_PROTECTED_BRANCHES = {"main", "master", "develop", "prod", "production"}
_VALID_PRIORITY = {"P0", "P1", "P2"}
_VALID_COMPLEXITY = {"trivial", "normal", "complex"}


async def _get_base_path(agent_id: str) -> Path:
    """Look up the configured base_path for this extension.

    Checks agent-specific integration first, falls back to system-wide. Unlike
    ``get_extension_creds`` this does not require an encrypted credential blob —
    the extension has no secrets, only a config path.
    """
    from sqlalchemy import nullslast, select

    from app.db.session import async_session_factory
    from app.models.integration import Integration

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == "runtime_scripts", Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row:
        raise ValueError(
            "No active 'runtime_scripts' integration. Configure it in Settings > Integrations."
        )

    base = ((row.extra_config or {}).get("base_path") or "").strip()
    if not base:
        raise ValueError(
            "'base_path' is not set on the runtime_scripts integration — edit it in Settings > Integrations."
        )

    path = Path(base).expanduser()
    if not path.is_dir():
        raise ValueError(f"Configured base_path does not exist or is not a directory: {path}")
    if not (path / "scripts" / "run.sh").is_file():
        raise ValueError(f"base_path is missing scripts/run.sh: {path}")
    return path


def _is_protected_branch(branch: str) -> bool:
    b = branch.strip().lower()
    if b in _PROTECTED_BRANCHES:
        return True
    if b.startswith("release"):  # matches 'release' and 'release/*'
        return True
    return False


def _indent_block(text: str, indent: str = "    ") -> str:
    """Indent every line of `text` so it sits under a YAML-ish `goal: |` key."""
    stripped = text.strip("\n")
    if not stripped:
        return ""
    return "\n".join(f"{indent}{line}" if line.strip() else "" for line in stripped.splitlines())


def _render_task_block(
    *,
    task_id: str,
    priority: str,
    complexity: str,
    ultrathink: bool,
    repo: str,
    branch: str,
    test: str,
    goal: str,
    note: str,
) -> str:
    lines = [
        f"- [ ] id: {task_id}",
        f"  priority: {priority}",
        f"  complexity: {complexity}",
        f"  ultrathink: {'true' if ultrathink else 'false'}",
        f"  repo: {repo}",
        f"  branch: {branch}",
        f"  test: {test}",
        "  goal: |",
        _indent_block(goal, "    "),
    ]
    if note.strip():
        lines.append("  note: |")
        lines.append(_indent_block(note, "    "))
    return "\n".join(lines) + "\n"


def _insert_under_pending(contents: str, block: str) -> str:
    """Insert `block` at the end of the `## pending` section of tasks.md."""
    lines = contents.splitlines(keepends=True)
    pending_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().lower() == "## pending"),
        None,
    )
    if pending_idx is None:
        raise ValueError("tasks.md has no '## pending' section — cannot insert task.")

    # Find the next `## ` header after pending, or EOF.
    end_idx = len(lines)
    for i in range(pending_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    # Walk back past trailing blank lines so the new block tucks in cleanly.
    insert_at = end_idx
    while insert_at > pending_idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    prefix = "".join(lines[:insert_at])
    suffix = "".join(lines[insert_at:])
    # Ensure a single blank line separator before and after.
    if prefix and not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"
    if suffix and not block.endswith("\n"):
        block += "\n"
    if suffix and not suffix.startswith("\n"):
        block = block + "\n"
    return prefix + block + suffix


def _extract_task_ids(contents: str) -> set[str]:
    return set(re.findall(r"^\s*-\s*\[[ x~]\]\s*id:\s*(\S+)", contents, flags=re.MULTILINE))


def create_tools(agent_id: str):
    @tool
    async def runtime_scripts_add_task(
        task_id: str,
        repo: str,
        branch: str,
        goal: str,
        priority: str = "P2",
        complexity: str = "normal",
        ultrathink: bool = False,
        test: str = "npm test",
        note: str = "",
    ) -> str:
        """Append a task to the runtime_scripts tasks.md queue under `## pending`.

        The autonomous runner picks the highest-priority pending task on its
        next run. Task IDs must be unique across the whole tasks.md file.

        Args:
            task_id: Unique slug for this task (e.g. 'fix-login-500').
            repo: Absolute path to the target repo the runner should modify.
            branch: Task branch. MUST NOT be main/master/develop/release*/prod/production.
            goal: What to do. 1-5 lines; specific enough that no follow-up is needed.
            priority: P0 (urgent), P1, or P2 (default). Lower number = higher priority.
            complexity: 'trivial' (one-shot, skips planner), 'normal' (default), or 'complex'.
            ultrathink: Only honored when complexity='complex'; enables Opus deep-thinking.
            test: Test command run from repo root. Default 'npm test'.
            note: Optional constraints / context for the planner.
        """
        base = await _get_base_path(agent_id)
        tasks_path = base / "tasks.md"
        if not tasks_path.is_file():
            return f"Error: tasks.md not found at {tasks_path}"

        tid = task_id.strip()
        if not tid or any(ch.isspace() for ch in tid):
            return f"Error: task_id must be a single non-empty token, got {task_id!r}"
        if priority not in _VALID_PRIORITY:
            return f"Error: priority must be one of {sorted(_VALID_PRIORITY)}, got {priority!r}"
        if complexity not in _VALID_COMPLEXITY:
            return f"Error: complexity must be one of {sorted(_VALID_COMPLEXITY)}, got {complexity!r}"
        if _is_protected_branch(branch):
            return f"Error: '{branch}' is a protected branch — safe-git-push.sh would refuse it."
        if not repo.startswith("/"):
            return f"Error: repo must be an absolute path, got {repo!r}"
        if not goal.strip():
            return "Error: goal is required."

        contents = tasks_path.read_text()
        if tid in _extract_task_ids(contents):
            return f"Error: task id '{tid}' already exists in tasks.md."

        block = _render_task_block(
            task_id=tid,
            priority=priority,
            complexity=complexity,
            ultrathink=ultrathink,
            repo=repo,
            branch=branch,
            test=test,
            goal=goal,
            note=note,
        )
        new_contents = _insert_under_pending(contents, block)
        tasks_path.write_text(new_contents)
        return (
            f"Added task '{tid}' ({priority}, {complexity}) to {tasks_path}. "
            "Call runtime_scripts_trigger_run to execute it."
        )

    @tool
    async def runtime_scripts_trigger_run() -> str:
        """Fire the runtime_scripts orchestrator (scripts/run.sh).

        Spawns run.sh as a detached background process and returns immediately
        with a log path. run.sh enforces its own safety gates (lockfile,
        session-reset window, weekly budget, needs-human escalation) and may
        no-op. Use runtime_scripts_get_status to inspect progress afterwards.
        """
        base = await _get_base_path(agent_id)
        script = base / "scripts" / "run.sh"
        logs_dir = base / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = logs_dir / f"trigger-{stamp}.log"
        log_fh = open(log_path, "wb")

        proc = await asyncio.create_subprocess_exec(
            "/bin/bash",
            str(script),
            cwd=str(base),
            stdout=log_fh,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ},
        )
        log_fh.close()  # subprocess keeps its own fd
        return (
            f"Launched {script} (pid {proc.pid}). Output streaming to {log_path}. "
            "run.sh may no-op if the session-reset gate hasn't elapsed; check "
            "runtime_scripts_get_status for the outcome."
        )

    @tool
    async def runtime_scripts_list_tasks() -> str:
        """Show tasks.md content by section (pending / in_progress / done)."""
        base = await _get_base_path(agent_id)
        tasks_path = base / "tasks.md"
        if not tasks_path.is_file():
            return f"tasks.md not found at {tasks_path}"
        contents = tasks_path.read_text()

        sections: dict[str, list[str]] = {"pending": [], "in_progress": [], "done": []}
        current: str | None = None
        for ln in contents.splitlines():
            header = ln.strip().lower()
            if header.startswith("## "):
                key = header[3:].strip()
                current = key if key in sections else None
                continue
            if current and ln.strip():
                sections[current].append(ln.rstrip())

        def _summarize(block_lines: list[str]) -> list[str]:
            ids = re.findall(r"^\s*-\s*\[[ x~]\]\s*id:\s*(\S+)", "\n".join(block_lines), flags=re.MULTILINE)
            return ids

        out = [f"tasks.md at {tasks_path}:"]
        for key in ("pending", "in_progress", "done"):
            ids = _summarize(sections[key])
            out.append(f"  {key}: {len(ids)} task(s)" + (f" — {', '.join(ids)}" if ids else ""))
        return "\n".join(out)

    @tool
    async def runtime_scripts_get_status() -> str:
        """Report runner status: active task, plan presence, escalations, recent logs."""
        base = await _get_base_path(agent_id)
        state = base / "state"
        logs = base / "logs"

        lines = [f"runtime_scripts status at {base}:"]

        active_file = state / "active.txt"
        active = active_file.read_text().strip() if active_file.is_file() else ""
        lines.append(f"  active task: {active or '(none)'}")

        plan_file = state / "Plan.md"
        if plan_file.is_file():
            text = plan_file.read_text()
            total = len(re.findall(r"^\s*-\s*\[[ x~]\]", text, flags=re.MULTILINE))
            done = len(re.findall(r"^\s*-\s*\[x\]", text, flags=re.MULTILINE))
            lines.append(f"  plan: {done}/{total} subtasks complete")
        else:
            lines.append("  plan: (none)")

        nh = state / "needs-human.md"
        if nh.is_file():
            excerpt = nh.read_text().strip().splitlines()
            head = " ".join(excerpt[:3])[:240]
            lines.append(f"  needs-human: YES — {head}")
        else:
            lines.append("  needs-human: no")

        if logs.is_dir():
            log_files = sorted(
                (p for p in logs.iterdir() if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:5]
            if log_files:
                lines.append("  recent logs:")
                for p in log_files:
                    size = p.stat().st_size
                    lines.append(f"    {p.name} ({size} bytes)")
            else:
                lines.append("  recent logs: (none)")
        return "\n".join(lines)

    return [
        runtime_scripts_add_task,
        runtime_scripts_trigger_run,
        runtime_scripts_list_tasks,
        runtime_scripts_get_status,
    ]


async def test_connection(creds: dict, config: dict) -> dict:
    """Verify base_path is a directory containing scripts/run.sh."""
    base = (config.get("base_path") or "").strip()
    if not base:
        return {"ok": False, "detail": "base_path is empty."}
    path = Path(base).expanduser()
    if not path.is_dir():
        return {"ok": False, "detail": f"Not a directory: {path}"}
    run_sh = path / "scripts" / "run.sh"
    tasks_md = path / "tasks.md"
    if not run_sh.is_file():
        return {"ok": False, "detail": f"Missing scripts/run.sh at {run_sh}"}
    if not tasks_md.is_file():
        return {"ok": False, "detail": f"Missing tasks.md at {tasks_md}"}
    return {"ok": True, "detail": f"Connected: {path} (run.sh + tasks.md present)"}
