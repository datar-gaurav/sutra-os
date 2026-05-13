#!/usr/bin/env python3
"""Sutra Fleet — host-side worker daemon.

Runs on the Mac host (NOT in Docker) so Gemini CLI's OAuth at
$GEMINI_HOME/.gemini/oauth_creds.json is reachable. Long-running: bound to
127.0.0.1:$FLEET_WORKER_PORT (default 7476), launchd keeps it alive.

Sutra (in Docker) calls http://host.docker.internal:$PORT/run when it
enqueues a job; the daemon claims and runs it. A watchdog cron inside sutra
covers the case where the daemon was offline at enqueue time.

Per-job lifecycle (same as before):
  1. POST /api/fleet/claim → if null, no-op.
  2. mkdir workspace = $FLEET_WORKSPACE_ROOT/<job_id>
  3. git clone <repo> (token-in-URL, never persisted to config)
  4. Branch off, then run:
        gemini -s -m <model> --yolo -p "<prompt>" (cwd=workspace)
     with a SCRUBBED env so Gemini cannot see GITHUB_TOKEN / SUTRA_URL.
  5. If git diff is dirty: commit, push branch, open PR via `gh`.
  6. Post a decisions+log summary as a PR comment.
  7. POST /status pr_created + pr_url, rmtree workspace.

Endpoints:
  POST /run        bearer-authed; kicks off one job (no-op if already busy)
  GET  /health     no auth; returns {ok, busy, version}

Required env (set in launchd plist or shell rc):
  SUTRA_URL                 e.g. http://localhost:8000
  FLEET_WORKER_TOKEN        shared secret matching settings.fleet_worker_token
  FLEET_WORKER_ID           friendly name, e.g. "mbp-2025"
  GITHUB_TOKEN              PAT with repo scope (used only by git push + gh)
  FLEET_WORKSPACE_ROOT      e.g. ~/agent_workspaces  (auto-mkdir'd)
  GEMINI_HOME               e.g. ~/.gemini-fleet-home

Optional:
  FLEET_WORKER_PORT         default: 7476
  FLEET_GEMINI_MODEL        default: gemini-2.5-pro
  FLEET_RUN_TIMEOUT_SEC     default: 1800
"""

from __future__ import annotations

import fcntl
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib.error
import urllib.request

VERSION = "1.0.0"

# ─── Config ──────────────────────────────────────────────────────────────────

LOCK_PATH = "/tmp/sutra-fleet.lock"
RUN_TIMEOUT_SEC = int(os.environ.get("FLEET_RUN_TIMEOUT_SEC", "1800"))
LOG_FLUSH_LINES = 25
LOG_FLUSH_SECONDS = 2.0

DECISION_MARKER = re.compile(r"^###\s*DECISION:\s*(.+?)(?:\s*\|\s*(.+))?$")

# Prepended to every job prompt so the agent emits machine-parseable decision
# markers the worker can scrape for the PR comment.
PROMPT_PREAMBLE = (
    "You are working inside a sandboxed clone of a single repo (cwd is the "
    "checkout). Make minimal, focused changes. When you make a non-obvious "
    "design call, emit one line in this exact format on its own line:\n"
    "    ### DECISION: <short title> | <one-sentence reason>\n"
    "Use multiple DECISION lines if needed. Do NOT commit or push — the "
    "harness handles that after you exit.\n\n"
    "Task:\n"
)


def _need(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.stderr.write(f"FATAL: env {name} is required.\n")
        sys.exit(2)
    return v


SUTRA_URL = _need("SUTRA_URL").rstrip("/")
WORKER_TOKEN = _need("FLEET_WORKER_TOKEN")
WORKER_ID = _need("FLEET_WORKER_ID")
GITHUB_TOKEN = _need("GITHUB_TOKEN")
WORKSPACE_ROOT = Path(os.path.expanduser(_need("FLEET_WORKSPACE_ROOT")))
GEMINI_HOME = Path(os.path.expanduser(_need("GEMINI_HOME")))
GEMINI_MODEL = os.environ.get("FLEET_GEMINI_MODEL", "gemini-2.5-pro")
WORKER_PORT = int(os.environ.get("FLEET_WORKER_PORT", "7476"))


# ─── HTTP helpers (stdlib only so the host has zero deps) ────────────────────


def _api(method: str, path: str, body: dict | None = None) -> dict | None:
    url = f"{SUTRA_URL}/api/fleet{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {WORKER_TOKEN}")
    req.add_header("X-Worker-Id", WORKER_ID)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode()
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"[fleet] {method} {path} → HTTP {e.code}: {e.read().decode()[:300]}\n")
        return None
    except Exception as e:
        sys.stderr.write(f"[fleet] {method} {path} → {e}\n")
        return None


def claim_job() -> dict | None:
    return _api("POST", "/claim")


def push_logs(job_id: str, lines: list[dict]) -> None:
    if lines:
        _api("POST", f"/{job_id}/logs", {"lines": lines})


def push_decision(job_id: str, decision: str, detail: str = "") -> None:
    _api("POST", f"/{job_id}/decision", {"decision": decision, "detail": detail})


def push_status(job_id: str, status: str, **extra) -> None:
    _api("POST", f"/{job_id}/status", {"status": status, **extra})


# ─── Git / sandbox helpers ───────────────────────────────────────────────────


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None, check: bool = True) -> str:
    """Synchronous subprocess. Returns combined output; raises on non-zero."""
    p = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        capture_output=True, text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        # Redact the GitHub token if it ever leaks into output.
        raise RuntimeError(out.replace(GITHUB_TOKEN, "<REDACTED>"))
    return out


def clone_repo(repo: str, dest: Path) -> None:
    """Shallow clone. Token is on the URL only — never written to .git/config."""
    auth_url = f"https://x-oauth-basic:{GITHUB_TOKEN}@github.com/{repo}.git"
    dest.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_ASKPASS": "echo",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    _run(
        ["git", "clone", "--depth", "50", "--single-branch", auth_url, str(dest)],
        env=env,
    )
    # Strip the credential out of the persisted remote so a casual `git remote -v`
    # post-mortem doesn't reveal it. We re-attach it ad-hoc at push time.
    safe_url = f"https://github.com/{repo}.git"
    _run(["git", "remote", "set-url", "origin", safe_url], cwd=dest, env=env)


def create_branch(workspace: Path, branch: str) -> None:
    _run(["git", "checkout", "-b", branch], cwd=workspace)


_token_identity_cache: tuple[str, str] | None = None


def _token_identity() -> tuple[str, str]:
    """Resolve the GitHub identity behind GITHUB_TOKEN as (name, email).

    Email uses the canonical `<id>+<login>@users.noreply.github.com` form so
    downstream consumers (Vercel, GitHub) recognise the commit as authored by
    the token's owner. Cached for the worker's lifetime.
    """
    global _token_identity_cache
    if _token_identity_cache is not None:
        return _token_identity_cache
    env = {**os.environ, "GH_TOKEN": GITHUB_TOKEN}
    raw = _run(["gh", "api", "user"], env=env)
    info = json.loads(raw)
    login = info["login"]
    user_id = info["id"]
    name = info.get("name") or login
    email = f"{user_id}+{login}@users.noreply.github.com"
    _token_identity_cache = (name, email)
    return _token_identity_cache


def commit_and_push(workspace: Path, repo: str, branch: str, message: str) -> None:
    """Commit working-tree changes and push. Token is provided on the command
    line for push only, never persisted."""
    name, email = _token_identity()
    _run(["git", "config", "user.email", email], cwd=workspace)
    _run(["git", "config", "user.name", name], cwd=workspace)
    _run(["git", "add", "-A"], cwd=workspace)
    _run(["git", "commit", "-m", message], cwd=workspace)

    auth_url = f"https://x-oauth-basic:{GITHUB_TOKEN}@github.com/{repo}.git"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    _run(["git", "push", auth_url, f"HEAD:{branch}"], cwd=workspace, env=env)


def working_tree_dirty(workspace: Path) -> bool:
    out = _run(["git", "status", "--porcelain"], cwd=workspace, check=False)
    return bool(out.strip())


def open_pr(repo: str, branch: str, title: str, body: str, cwd: Path) -> tuple[str, int]:
    """Open PR via `gh`. Returns (url, number)."""
    env = {**os.environ, "GH_TOKEN": GITHUB_TOKEN}
    url = _run(
        ["gh", "pr", "create",
         "--repo", repo, "--head", branch,
         "--title", title, "--body", body],
        cwd=cwd, env=env, check=False,
    ).strip()
    # `gh pr create` prints the URL on success, e.g. https://github.com/x/y/pull/42
    m = re.search(r"https://github\.com/[^\s]+/pull/(\d+)", url)
    if not m:
        raise RuntimeError(f"gh pr create returned no URL:\n{url}")
    return m.group(0), int(m.group(1))


def pr_comment(repo: str, pr_number: int, body: str) -> None:
    env = {**os.environ, "GH_TOKEN": GITHUB_TOKEN}
    _run(
        ["gh", "pr", "comment", str(pr_number), "--repo", repo, "--body", body],
        env=env, check=False,
    )


# ─── Gemini CLI invocation ───────────────────────────────────────────────────


def _gemini_env() -> dict:
    """Scrubbed env passed to the Gemini subprocess.

    Critically: NO GITHUB_TOKEN, NO SUTRA_URL, NO FLEET_WORKER_TOKEN. Gemini
    only gets PATH + a redirected HOME so its OAuth creds and config live
    under GEMINI_HOME, separate from the user's real ~/.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": str(GEMINI_HOME),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def run_gemini(job: dict, workspace: Path) -> tuple[int, list[dict]]:
    """Run `gemini -s ...` inside the workspace. Returns (exit_code, decisions).

    Streams output line-by-line:
      - batches log lines and POSTs them to /logs every N lines or N seconds
      - watches for `### DECISION: ...` markers and forwards them to /decision
    """
    cmd = [
        "gemini",
        "-s",                                  # macOS Seatbelt sandbox
        "-m", GEMINI_MODEL,
        "--yolo",                              # auto-approve internal tool calls
        "-p", PROMPT_PREAMBLE + job["prompt"],
    ]
    env = _gemini_env()
    proc = subprocess.Popen(
        cmd, cwd=str(workspace), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    assert proc.stdout is not None

    job_id = job["id"]
    batch: list[dict] = []
    decisions_found: list[dict] = []
    last_flush = time.time()
    start = time.time()

    def flush():
        nonlocal batch, last_flush
        if batch:
            push_logs(job_id, batch)
            batch = []
        last_flush = time.time()

    while True:
        if time.time() - start > RUN_TIMEOUT_SEC:
            proc.kill()
            push_logs(job_id, [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stream": "event",
                "line": f"[fleet] killed after {RUN_TIMEOUT_SEC}s timeout",
            }])
            flush()
            return 124, decisions_found

        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
            continue

        ts = datetime.now(timezone.utc).isoformat()
        line_clean = line.rstrip("\n")
        batch.append({"timestamp": ts, "stream": "stdout", "line": line_clean})

        m = DECISION_MARKER.match(line_clean)
        if m:
            decision = m.group(1).strip()
            detail = (m.group(2) or "").strip()
            decisions_found.append({"decision": decision, "detail": detail, "timestamp": ts})
            push_decision(job_id, decision, detail)

        if len(batch) >= LOG_FLUSH_LINES or (time.time() - last_flush) > LOG_FLUSH_SECONDS:
            flush()

    flush()
    return proc.returncode, decisions_found


# ─── PR comment composition ──────────────────────────────────────────────────


def compose_pr_comment(job: dict, decisions: list[dict], run_tail: list[str]) -> str:
    triage = (job.get("triage") or {}).get("reason", "(manual job — no triage reason)")
    lines = [
        "## 🤖 Sutra Fleet — agent decisions & notes",
        "",
        f"**Job:** `{job['id']}`",
        f"**Triage reason:** {triage}",
        "",
    ]
    if decisions:
        lines += ["### Decisions recorded by the agent", ""]
        lines += ["| Decision | Detail |", "| --- | --- |"]
        for d in decisions:
            lines.append(f"| {d['decision']} | {d.get('detail','')} |")
        lines.append("")
    else:
        lines += ["_The agent did not emit any `### DECISION:` markers._", ""]
    if run_tail:
        lines += ["### Last lines of agent reasoning", "", "```"]
        lines += run_tail[-40:]
        lines += ["```"]
    return "\n".join(lines)


# ─── Lock ────────────────────────────────────────────────────────────────────


def acquire_daemon_lock():
    """Process-level lock so only one daemon binds the port. Held for life."""
    fd = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.stderr.write("[fleet] another daemon holds the lock; exiting.\n")
        sys.exit(0)
    fd.write(str(os.getpid()))
    fd.flush()
    return fd


# ─── Per-job execution ───────────────────────────────────────────────────────


_busy_lock = threading.Lock()
_busy = False


def run_one_job() -> int:
    """Claim one job, run it end-to-end. Returns exit code (0 = success/no-op)."""
    global _busy
    with _busy_lock:
        if _busy:
            return 0
        _busy = True
    try:
        return _run_one_job_inner()
    finally:
        with _busy_lock:
            _busy = False


def _run_one_job_inner() -> int:
    job = claim_job()
    if not job:
        sys.stderr.write("[fleet] queue empty.\n")
        return 0

    job_id = job["id"]
    repo = job["repo_url"]
    branch = job["branch_name"] or f"fleet/{job_id[:8]}"
    workspace = WORKSPACE_ROOT / job_id
    run_tail: list[str] = []

    try:
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        if workspace.exists():
            shutil.rmtree(workspace)

        push_status(job_id, "running")
        clone_repo(repo, workspace)
        create_branch(workspace, branch)
        push_logs(job_id, [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stream": "event",
            "line": f"[fleet] cloned {repo}, branch {branch}, starting gemini",
        }])

        exit_code, decisions = run_gemini(job, workspace)
        if exit_code != 0:
            push_status(job_id, "failed", error=f"gemini exited {exit_code}")
            return 1

        if not working_tree_dirty(workspace):
            push_status(job_id, "failed", error="agent made no changes")
            return 1

        push_status(job_id, "pushing")
        plan_summary = job["title"]
        commit_and_push(
            workspace, repo, branch,
            f"feat: {plan_summary}\n\nGenerated by Sutra Fleet (job {job_id})",
        )
        pr_url, pr_number = open_pr(repo, branch, f"feat: {plan_summary}",
                                    f"Resolves {job.get('issue_ref') or ''}\n\nAgent prompt:\n{job['prompt']}",
                                    cwd=workspace)

        # Pull the last chunk of run_log for the PR comment.
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"{SUTRA_URL}/api/fleet/{job_id}",
                    headers={"Authorization": f"Bearer {WORKER_TOKEN}", "X-Worker-Id": WORKER_ID},
                ), timeout=15,
            ) as r:
                refreshed = json.loads(r.read())
                run_tail = [e["line"] for e in (refreshed.get("run_log") or [])][-40:]
        except Exception:
            pass

        pr_comment(repo, pr_number, compose_pr_comment(job, decisions, run_tail))
        push_status(job_id, "pr_created", pr_url=pr_url, pr_number=pr_number)
        return 0

    except Exception as e:
        msg = str(e).replace(GITHUB_TOKEN, "<REDACTED>")
        push_status(job_id, "failed", error=msg[:4000])
        sys.stderr.write(f"[fleet] {job_id} failed: {msg}\n")
        return 1
    finally:
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass


# ─── HTTP server ─────────────────────────────────────────────────────────────


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = f"sutra-fleet-worker/{VERSION}"

    def log_message(self, fmt, *args):
        # Quieter than the default — only log at warn/error
        sys.stderr.write(f"[fleet] {self.address_string()} {fmt % args}\n")

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _auth_ok(self) -> bool:
        h = self.headers.get("Authorization", "")
        if not h.lower().startswith("bearer "):
            return False
        presented = h.split(" ", 1)[1].strip()
        # constant-time compare without importing secrets just for one call
        if len(presented) != len(WORKER_TOKEN):
            return False
        result = 0
        for x, y in zip(presented.encode(), WORKER_TOKEN.encode()):
            result |= x ^ y
        return result == 0

    def do_GET(self):
        if self.path == "/health":
            with _busy_lock:
                busy_now = _busy
            auth_ready = (GEMINI_HOME / ".gemini" / "oauth_creds.json").exists()
            self._json(200, {
                "ok": True,
                "busy": busy_now,
                "version": VERSION,
                "worker_id": WORKER_ID,
                "auth_ready": auth_ready,
                "gemini_home": str(GEMINI_HOME),
            })
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            self._json(404, {"error": "not found"})
            return
        if not self._auth_ok():
            self._json(403, {"error": "invalid bearer"})
            return

        with _busy_lock:
            already = _busy
        if already:
            # Idempotent: tell caller we're already on it.
            self._json(202, {"started": False, "busy": True})
            return

        # Acknowledge immediately, run the job in a background thread.
        self._json(202, {"started": True})
        t = threading.Thread(target=run_one_job, name="fleet-job", daemon=True)
        t.start()


class _ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    lock = acquire_daemon_lock()
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"[fleet] daemon up, listening on 127.0.0.1:{WORKER_PORT} (worker_id={WORKER_ID})\n")
    server = _ReuseAddrServer(("127.0.0.1", WORKER_PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("[fleet] shutting down.\n")
    finally:
        server.server_close()
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
