#!/usr/bin/env python3
"""Dispatcher bridge daemon — host-side HTTP server for the runtime_scripts extension.

Runs on the HOST machine (not inside Docker). Listens on 127.0.0.1:PORT.
The backend container reaches it via http://host.docker.internal:PORT.

Usage:
    python3 scripts/dispatcher_bridge.py

Config is read from ../backend/.env (relative to this script's directory):
    DISPATCHER_BASE_PATH    — absolute path to the runtime_scripts checkout
    DISPATCHER_BRIDGE_TOKEN — shared bearer token (any secret string)
    DISPATCHER_BRIDGE_PORT  — port to listen on (default 7475)

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import datetime
import http.server
import json
import os
import re
import subprocess
import sys
from http import HTTPStatus
from pathlib import Path
from threading import Thread


VERSION = "1.0.0"

# ── .env loader ───────────────────────────────────────────────────────────────

def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file. Handles comments, blank lines, and single/double quotes."""
    env: dict[str, str] = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if val and val[0] in ('"', "'"):
                    quote = val[0]
                    end = val.find(quote, 1)
                    val = val[1:end] if end != -1 else val[1:]
                else:
                    # Strip inline comment
                    val = val.split(" #")[0].strip()
                env[key] = val
    except FileNotFoundError:
        pass
    return env


# ── Configuration ─────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH = _SCRIPT_DIR.parent / "backend" / ".env"

_env = _load_env_file(_ENV_PATH)

BASE_PATH_STR: str = _env.get("DISPATCHER_BASE_PATH") or os.environ.get("DISPATCHER_BASE_PATH", "")
BRIDGE_TOKEN: str  = _env.get("DISPATCHER_BRIDGE_TOKEN") or os.environ.get("DISPATCHER_BRIDGE_TOKEN", "")
BRIDGE_PORT: int   = int(_env.get("DISPATCHER_BRIDGE_PORT") or os.environ.get("DISPATCHER_BRIDGE_PORT", "7475"))

BASE_PATH: Path | None = Path(BASE_PATH_STR).expanduser() if BASE_PATH_STR else None


# ── Validation helpers (single source of truth — mirrored by the thin extension) ──

_PROTECTED_BRANCHES = {"main", "master", "develop", "prod", "production"}
_VALID_PRIORITY = {"P0", "P1", "P2"}
_VALID_COMPLEXITY = {"trivial", "normal", "complex"}


def _is_protected_branch(branch: str) -> bool:
    b = branch.strip().lower()
    if b in _PROTECTED_BRANCHES:
        return True
    if b.startswith("release"):
        return True
    return False


def _indent_block(text: str, indent: str = "    ") -> str:
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
    lines = contents.splitlines(keepends=True)
    pending_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().lower() == "## pending"),
        None,
    )
    if pending_idx is None:
        raise ValueError("tasks.md has no '## pending' section — cannot insert task.")

    end_idx = len(lines)
    for i in range(pending_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    insert_at = end_idx
    while insert_at > pending_idx + 1 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    prefix = "".join(lines[:insert_at])
    suffix = "".join(lines[insert_at:])
    if prefix and not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"
    if suffix and not block.endswith("\n"):
        block += "\n"
    if suffix and not suffix.startswith("\n"):
        block = block + "\n"
    return prefix + block + suffix


def _extract_task_ids(contents: str) -> set[str]:
    return set(re.findall(r"^\s*-\s*\[[ x~]\]\s*id:\s*(\S+)", contents, flags=re.MULTILINE))


# ── HTTP handler ──────────────────────────────────────────────────────────────

class BridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[bridge] {self.address_string()} — {fmt % args}", flush=True)

    def _auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not BRIDGE_TOKEN:
            return True  # no token configured → open (useful for local dev testing)
        return auth == f"Bearer {BRIDGE_TOKEN}"

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw)

    def _base_path_or_error(self) -> Path | None:
        if not BASE_PATH:
            self._send_json({"detail": "DISPATCHER_BASE_PATH not configured in backend/.env"}, 503)
            return None
        if not BASE_PATH.is_dir():
            self._send_json({"detail": f"DISPATCHER_BASE_PATH does not exist: {BASE_PATH}"}, 503)
            return None
        return BASE_PATH

    # ── Route dispatch ────────────────────────────────────────────────────────

    def do_GET(self):  # noqa: N802
        if not self._auth():
            self._send_json({"detail": "Unauthorized"}, 401)
            return
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/tasks":
            self._handle_list_tasks()
        elif self.path == "/status":
            self._handle_get_status()
        else:
            self._send_json({"detail": "Not found"}, 404)

    def do_POST(self):  # noqa: N802
        if not self._auth():
            self._send_json({"detail": "Unauthorized"}, 401)
            return
        if self.path == "/tasks":
            self._handle_add_task()
        elif self.path == "/trigger":
            self._handle_trigger()
        else:
            self._send_json({"detail": "Not found"}, 404)

    # ── /health ───────────────────────────────────────────────────────────────

    def _handle_health(self) -> None:
        self._send_json({
            "ok": BASE_PATH is not None and BASE_PATH.is_dir(),
            "base_path": str(BASE_PATH) if BASE_PATH else None,
            "version": VERSION,
        })

    # ── POST /tasks ───────────────────────────────────────────────────────────

    def _handle_add_task(self) -> None:
        base = self._base_path_or_error()
        if not base:
            return
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"detail": f"Invalid JSON: {e}"}, 400)
            return

        task_id   = (body.get("task_id") or "").strip()
        repo      = (body.get("repo") or "").strip()
        branch    = (body.get("branch") or "").strip()
        goal      = (body.get("goal") or "").strip()
        priority  = (body.get("priority") or "P2").strip()
        complexity = (body.get("complexity") or "normal").strip()
        ultrathink = bool(body.get("ultrathink", False))
        test      = (body.get("test") or "npm test").strip()
        note      = (body.get("note") or "").strip()

        if not task_id or any(ch.isspace() for ch in task_id):
            self._send_json({"detail": f"task_id must be a non-empty token without spaces, got {task_id!r}"}, 400)
            return
        if priority not in _VALID_PRIORITY:
            self._send_json({"detail": f"priority must be one of {sorted(_VALID_PRIORITY)}, got {priority!r}"}, 400)
            return
        if complexity not in _VALID_COMPLEXITY:
            self._send_json({"detail": f"complexity must be one of {sorted(_VALID_COMPLEXITY)}, got {complexity!r}"}, 400)
            return
        if _is_protected_branch(branch):
            self._send_json({"detail": f"'{branch}' is a protected branch — safe-git-push.sh would refuse it."}, 400)
            return
        if not repo.startswith("/"):
            self._send_json({"detail": f"repo must be an absolute path, got {repo!r}"}, 400)
            return
        if not goal:
            self._send_json({"detail": "goal is required."}, 400)
            return

        tasks_path = base / "tasks.md"
        if not tasks_path.is_file():
            self._send_json({"detail": f"tasks.md not found at {tasks_path}"}, 503)
            return

        contents = tasks_path.read_text()
        if task_id in _extract_task_ids(contents):
            self._send_json({"detail": f"task id '{task_id}' already exists in tasks.md."}, 409)
            return

        block = _render_task_block(
            task_id=task_id, priority=priority, complexity=complexity,
            ultrathink=ultrathink, repo=repo, branch=branch,
            test=test, goal=goal, note=note,
        )
        try:
            new_contents = _insert_under_pending(contents, block)
        except ValueError as e:
            self._send_json({"detail": str(e)}, 422)
            return

        tasks_path.write_text(new_contents)
        self._send_json({
            "task_id": task_id,
            "file": str(tasks_path),
            "message": f"Task '{task_id}' ({priority}, {complexity}) added to tasks.md.",
        }, 201)

    # ── GET /tasks ────────────────────────────────────────────────────────────

    def _handle_list_tasks(self) -> None:
        base = self._base_path_or_error()
        if not base:
            return
        tasks_path = base / "tasks.md"
        if not tasks_path.is_file():
            self._send_json({"detail": f"tasks.md not found at {tasks_path}"}, 503)
            return

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

        def _ids(block_lines: list[str]) -> list[str]:
            return re.findall(
                r"^\s*-\s*\[[ x~]\]\s*id:\s*(\S+)",
                "\n".join(block_lines), flags=re.MULTILINE,
            )

        self._send_json({
            "pending":     _ids(sections["pending"]),
            "in_progress": _ids(sections["in_progress"]),
            "done":        _ids(sections["done"]),
        })

    # ── POST /trigger ─────────────────────────────────────────────────────────

    def _handle_trigger(self) -> None:
        base = self._base_path_or_error()
        if not base:
            return
        script = base / "scripts" / "run.sh"
        if not script.is_file():
            self._send_json({"detail": f"scripts/run.sh not found at {script}"}, 503)
            return

        logs_dir = base / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = logs_dir / f"trigger-{stamp}.log"

        with open(log_path, "wb") as log_fh:
            proc = subprocess.Popen(
                ["/bin/bash", str(script)],
                cwd=str(base),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        self._send_json({"pid": proc.pid, "log_path": str(log_path)})

    # ── GET /status ───────────────────────────────────────────────────────────

    def _handle_get_status(self) -> None:
        base = self._base_path_or_error()
        if not base:
            return
        state = base / "state"
        logs = base / "logs"

        active = ""
        active_file = state / "active.txt"
        if active_file.is_file():
            active = active_file.read_text().strip()

        plan_progress: str | None = None
        plan_file = state / "Plan.md"
        if plan_file.is_file():
            text = plan_file.read_text()
            total = len(re.findall(r"^\s*-\s*\[[ x~]\]", text, flags=re.MULTILINE))
            done = len(re.findall(r"^\s*-\s*\[x\]", text, flags=re.MULTILINE))
            plan_progress = f"{done}/{total}"

        needs_human: str | None = None
        nh = state / "needs-human.md"
        if nh.is_file():
            excerpt = nh.read_text().strip().splitlines()
            needs_human = " ".join(excerpt[:3])[:240]

        recent_logs: list[dict] = []
        if logs.is_dir():
            log_files = sorted(
                (p for p in logs.iterdir() if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:5]
            recent_logs = [{"name": p.name, "bytes": p.stat().st_size} for p in log_files]

        self._send_json({
            "active_task":    active or None,
            "plan_progress":  plan_progress,
            "needs_human":    needs_human,
            "recent_logs":    recent_logs,
        })


# ── Startup ───────────────────────────────────────────────────────────────────

def main() -> None:
    if not BRIDGE_TOKEN:
        print(
            "[bridge] WARNING: DISPATCHER_BRIDGE_TOKEN is not set — all requests accepted.\n"
            "         Set it in backend/.env or generate with: "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"",
            file=sys.stderr,
        )
    if not BASE_PATH_STR:
        print(
            "[bridge] ERROR: DISPATCHER_BASE_PATH is not set in backend/.env.\n"
            "         Re-run ./install.sh or add DISPATCHER_BASE_PATH=/path/to/runtime_scripts.",
            file=sys.stderr,
        )
    elif not (BASE_PATH and BASE_PATH.is_dir()):
        print(
            f"[bridge] WARNING: DISPATCHER_BASE_PATH={BASE_PATH_STR!r} does not exist. "
            "Bridge will start but /health will report not-ok.",
            file=sys.stderr,
        )
    else:
        print(f"[bridge] BASE_PATH: {BASE_PATH}", flush=True)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
    print(f"[bridge] Listening on http://127.0.0.1:{BRIDGE_PORT}  (version {VERSION})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] Stopped.", flush=True)


if __name__ == "__main__":
    main()
