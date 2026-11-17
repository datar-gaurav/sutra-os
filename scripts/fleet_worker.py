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
  POST /run          bearer-authed; kicks off one job (no-op if already busy)
  POST /exec/claude  bearer-authed; one Claude Code turn on the user's Claude
                     subscription, streamed back as NDJSON (purpose provider
                     "claude_code")
  POST /exec/codex   same for Codex on the user's ChatGPT subscription
                     (purpose provider "codex")
  GET  /models/codex bearer-authed; models the host's Codex login offers
  GET  /health       no auth; returns {ok, busy, version, claude_ready, codex_ready}

Required env (set in launchd plist or shell rc):
  SUTRA_URL                 e.g. http://localhost:8000
  FLEET_WORKER_TOKEN        shared secret matching settings.fleet_worker_token
  FLEET_WORKER_ID           friendly name, e.g. "mbp-2025"
  GITHUB_TOKEN              PAT with repo scope (used only by git push + gh)
  FLEET_WORKSPACE_ROOT      e.g. ~/agent_workspaces  (auto-mkdir'd)
  GEMINI_HOME               e.g. ~/.gemini-fleet-home

Optional:
  SHAKHA_BIN                path to the `shakha` command; turns on the Shakha
                            runner (Forge's CODE_EXECUTOR=shakha). With it set,
                            GEMINI_HOME and GITHUB_TOKEN are only needed for
                            the Gemini runner.
  SHAKHA_SYNC_SECONDS       default: 60 (how often Shakha tasks are synced)
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

VERSION = "1.3.0"

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
WORKSPACE_ROOT = Path(os.path.expanduser(_need("FLEET_WORKSPACE_ROOT")))

# Runners this worker can execute; announced on every claim so Sutra never
# hands it a job it can't run. Shakha is opt-in via SHAKHA_BIN.
SHAKHA_BIN = os.path.expanduser(os.environ.get("SHAKHA_BIN", "").strip())
SHAKHA_SYNC_SECONDS = int(os.environ.get("SHAKHA_SYNC_SECONDS", "60"))
_GEMINI_HOME_RAW = os.environ.get("GEMINI_HOME", "").strip()
if not SHAKHA_BIN and not _GEMINI_HOME_RAW:
    _need("GEMINI_HOME")  # exits with the usual message
RUNNERS = (["gemini"] if _GEMINI_HOME_RAW else []) + (["shakha"] if SHAKHA_BIN else [])
GITHUB_TOKEN = _need("GITHUB_TOKEN") if "gemini" in RUNNERS else os.environ.get("GITHUB_TOKEN", "")
GEMINI_HOME = Path(os.path.expanduser(_GEMINI_HOME_RAW)) if _GEMINI_HOME_RAW else None
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
    return _api("POST", "/claim", {"runners": RUNNERS})


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

    if job.get("runner", "gemini") == "shakha":
        return start_shakha_job(job)

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
        msg = str(e).replace(GITHUB_TOKEN, "<REDACTED>") if GITHUB_TOKEN else str(e)
        push_status(job_id, "failed", error=msg[:4000])
        sys.stderr.write(f"[fleet] {job_id} failed: {msg}\n")
        return 1
    finally:
        try:
            shutil.rmtree(workspace, ignore_errors=True)
        except Exception:
            pass


# ─── Shakha runner ───────────────────────────────────────────────────────────
#
# Forge's CODE_EXECUTOR=shakha queues jobs with runner="shakha". This worker
# hands each one to Shakha through the `shakha` command (which talks to
# shakhad over its local socket) and returns at once: Shakha plans, waits for
# your approval, runs checks and review, and opens the draft PR on its own
# schedule. A background loop then keeps Sutra in step with each task.

_SHAKHA_TERMINAL = {"completed", "cancelled", "failed"}
_SHAKHA_DELIVERY_PENDING = {"waiting_for_gate", "waiting_for_acceptance", "publishing", "unknown"}
_shakha_seen: dict[str, tuple] = {}  # job id → last reported state, to report changes only


def _shakha(args: list[str], timeout: int = 60) -> dict:
    """Run `shakha …` and parse its JSON output. Raises on failure."""
    p = subprocess.run([SHAKHA_BIN, *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"shakha {args[0]} {args[1] if len(args) > 1 else ''}: "
                           f"{(p.stderr or p.stdout).strip()[:500]}")
    return json.loads(p.stdout or "{}")


def shakha_ready() -> bool:
    try:
        _shakha(["status"], timeout=10)
        return True
    except Exception:
        return False


def normalize_repo(url: str) -> str:
    """'git@github.com:Owner/Repo.git' / 'https://github.com/owner/repo' → 'owner/repo'."""
    url = url.strip().rstrip("/")
    url = re.sub(r"\.git$", "", url)
    m = re.search(r"[:/]([^/:]+/[^/:]+)$", url)
    return (m.group(1) if m else url).lower()


def resolve_shakha_repo(repo_url: str) -> str:
    """Find the local checkout Shakha knows for 'owner/repo' by its git remotes."""
    wanted = normalize_repo(repo_url)
    for repo in _shakha(["repo", "list"]).get("repos", []):
        if not repo.get("exists"):
            continue
        try:
            remotes = _run(["git", "-C", repo["path"], "remote", "-v"], check=False)
        except Exception:
            continue
        for line in remotes.splitlines():
            parts = line.split()
            if len(parts) >= 2 and normalize_repo(parts[1]) == wanted:
                return repo["path"]
    raise RuntimeError(
        f"Shakha has no repository for {repo_url}. Add your checkout with "
        f"`shakha repo add /path/to/repo`, then retry the Forge request."
    )


def start_shakha_job(job: dict) -> int:
    job_id = job["id"]
    try:
        push_status(job_id, "running", note="Fleet worker picked it up; creating the Shakha task")
        repo_path = resolve_shakha_repo(job["repo_url"])
        # The fleet job id is the idempotency key, so a retry after a crash
        # returns the same Shakha task instead of creating a second one.
        created = _shakha([
            "task", "create", "--repo", repo_path, "--title", job["title"][:200],
            "--prompt", job["prompt"], "--agent", "auto", "--key", f"sutra-fleet-{job_id}",
        ])
        task_id = created["taskId"]
        push_status(job_id, "running", external_ref=task_id,
                    note=f"Shakha task {task_id} created in {repo_path}")
        return 0
    except Exception as e:
        push_status(job_id, "failed", error=str(e)[:4000])
        sys.stderr.write(f"[fleet] shakha job {job_id} failed to start: {e}\n")
        return 1


def shakha_report(task: dict) -> dict:
    """Map a Shakha taskView to a fleet status update."""
    execution = task.get("execution", "")
    detail = task.get("deliveryDetail") or {}
    url = detail.get("url")
    attention = sorted({a.get("type", "") for a in task.get("attentionReasons") or []})
    update: dict = {}
    if url:
        update["pr_url"] = url
        m = re.search(r"/pull/(\d+)", url)
        if m:
            update["pr_number"] = int(m.group(1))

    if execution == "completed":
        if url:
            update["status"] = "pr_created"
        elif detail.get("status") in _SHAKHA_DELIVERY_PENDING:
            update["status"] = "running"
            update["note"] = f"Shakha: finished, delivery {detail.get('status')}"
        else:
            update["status"] = "completed"
    elif execution == "failed":
        update["status"] = "failed"
        reasons = (task.get("gate") or {}).get("reasons") or []
        update["error"] = (detail.get("error") or "; ".join(reasons) or "Shakha task failed")[:4000]
    elif execution == "cancelled":
        update["status"] = "cancelled"
    else:
        update["status"] = "running"
        if execution == "awaiting_approval" or "action_required" in {
            a.get("level") for a in task.get("attentionReasons") or []
        }:
            update["note"] = (f"Shakha: {execution}" + (f" ({', '.join(attention)})" if attention else "")
                              + " — answer in Shakha or Powerdial")
        else:
            update["note"] = f"Shakha: {execution}"
    update["_key"] = (execution, detail.get("state"), detail.get("status"), url, tuple(attention))
    return update


def shakha_sync_once() -> None:
    jobs = _api("GET", "/worker/sync?runner=shakha") or []
    for job in jobs:
        job_id, task_id = job["id"], job.get("external_ref")
        if not task_id:
            continue
        try:
            task = _shakha(["task", "get", task_id])
            if job["status"] == "cancelled":
                if task.get("execution") not in _SHAKHA_TERMINAL:
                    _shakha(["task", "cancel", task_id, "--key", f"sutra-cancel-{job_id}"])
                    push_logs(job_id, [{"timestamp": datetime.now(timezone.utc).isoformat(),
                                        "stream": "event", "line": f"[fleet] cancelled Shakha task {task_id}"}])
                continue
            update = shakha_report(task)
            key = update.pop("_key")
            if _shakha_seen.get(job_id) == key:
                continue
            _shakha_seen[job_id] = key
            push_status(job_id, **update)
            if update["status"] in ("pr_created", "completed", "failed", "cancelled"):
                _shakha_seen.pop(job_id, None)
        except Exception as e:
            sys.stderr.write(f"[fleet] shakha sync {job_id}: {e}\n")


def shakha_sync_loop() -> None:
    while True:
        try:
            shakha_sync_once()
        except Exception as e:
            sys.stderr.write(f"[fleet] shakha sync loop: {e}\n")
        time.sleep(SHAKHA_SYNC_SECONDS)


# ─── CLI agent exec (subscription-backed chat turns) ─────────────────────────
#
# Sutra agents whose purpose slot resolves to provider "claude_code" or "codex"
# send each chat turn here. We run the official CLI headless, logged in with
# the user's own subscription (Claude: macOS keychain / ~/.claude; Codex:
# ~/.codex/auth.json). Those logins stay on this host and never reach Docker.
# The CLI's JSON events are relayed back as NDJSON, framed by our own
# sutra_start / sutra_end events. One working folder per agent and runner, so
# files persist across turns.

_WORKDIR_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._\[\]-]{1,80}$")
_CLAUDE_TOOL_RE = re.compile(r"^[A-Za-z0-9_]+(\([^()\n]{0,200}\))?$")
_FILE_SNAPSHOT_LIMIT = 5000
EXEC_MAX_TIMEOUT_SEC = int(os.environ.get("CLI_MAX_TIMEOUT_SEC", os.environ.get("CLAUDE_MAX_TIMEOUT_SEC", "1800")))
# Secrets that must never reach a CLI. API keys would also switch the CLI from
# the subscription to pay-per-token API billing.
_SCRUBBED_ENV = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
    "GITHUB_TOKEN", "GH_TOKEN", "FLEET_WORKER_TOKEN", "SUTRA_URL",
}


def _find_bin(env_name: str, name: str) -> str:
    return os.path.expanduser(
        os.environ.get(env_name, "").strip() or shutil.which(name) or f"~/.local/bin/{name}"
    )


def _is_exe(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _cli_env(bin_path: str) -> dict:
    """Env for a CLI subprocess: real HOME/USER so it finds the login, no secrets."""
    keep = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL", "TERM", "CODEX_HOME")
    env = {k: os.environ[k] for k in keep if k in os.environ and k not in _SCRUBBED_ENV}
    env.setdefault("PATH", "/usr/bin:/bin:/usr/local/bin")
    bin_dir = os.path.dirname(bin_path)
    if bin_dir and bin_dir not in env["PATH"].split(":"):
        env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return env


class CliRunner:
    """One subscription CLI: how to find it, check it and build its argv."""

    name = ""

    def __init__(self, bin_path: str, workspace_root: Path, max_concurrent: int):
        self.bin = bin_path
        self.workspace_root = workspace_root
        self.max_concurrent = max_concurrent
        self.slots = threading.BoundedSemaphore(max_concurrent)

    def ready(self) -> bool:
        return _is_exe(self.bin)

    def env(self) -> dict:
        return _cli_env(self.bin)

    def build(self, req: dict, workdir: Path) -> tuple[list[str], str]:
        """Validate the request; return (argv, stdin text). Raises ValueError."""
        raise NotImplementedError


class ClaudeRunner(CliRunner):
    name = "claude"
    allow_bypass = os.environ.get("CLAUDE_ALLOW_BYPASS", "").strip() == "1"

    def env(self) -> dict:
        env = super().env()
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return env

    def build(self, req: dict, workdir: Path) -> tuple[list[str], str]:
        model = str(req.get("model") or "sonnet").strip()
        if not _MODEL_RE.match(model):
            raise ValueError(f"invalid model {model!r}")
        mode = str(req.get("permission_mode") or "acceptEdits").strip()
        allowed = {"default", "acceptEdits", "plan"} | ({"bypassPermissions"} if self.allow_bypass else set())
        if mode not in allowed:
            raise ValueError(f"permission_mode {mode!r} not allowed (allowed: {sorted(allowed)})")
        cmd = [
            self.bin, "-p",
            "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--model", model,
            "--permission-mode", mode,
        ]
        tools = [str(t).strip() for t in (req.get("allowed_tools") or []) if str(t).strip()]
        for t in tools:
            if not _CLAUDE_TOOL_RE.match(t):
                raise ValueError(f"invalid allowed tool {t!r}")
        if tools:
            cmd += ["--allowedTools", ",".join(tools)]
        if req.get("max_turns"):
            cmd += ["--max-turns", str(max(1, min(int(req["max_turns"]), 200)))]
        system_prompt = str(req.get("system_prompt") or "").strip()
        if system_prompt:
            cmd += ["--append-system-prompt", system_prompt]
        return cmd, str(req.get("prompt") or "")


class CodexRunner(CliRunner):
    name = "codex"
    allow_full_access = os.environ.get("CODEX_ALLOW_FULL_ACCESS", "").strip() == "1"

    def build(self, req: dict, workdir: Path) -> tuple[list[str], str]:
        sandbox = str(req.get("sandbox") or "workspace-write").strip()
        allowed = {"read-only", "workspace-write"} | ({"danger-full-access"} if self.allow_full_access else set())
        if sandbox not in allowed:
            raise ValueError(f"sandbox {sandbox!r} not allowed (allowed: {sorted(allowed)})")
        cmd = [
            self.bin, "exec", "--json", "--color", "never", "--skip-git-repo-check", "--ephemeral",
            "-s", sandbox, "-C", str(workdir),
        ]
        model = str(req.get("model") or "default").strip()
        if model != "default":
            if not _MODEL_RE.match(model):
                raise ValueError(f"invalid model {model!r}")
            cmd += ["-m", model]
        effort = str(req.get("reasoning_effort") or "").strip()
        if effort:
            if not re.match(r"^[a-z]{1,16}$", effort):
                raise ValueError(f"invalid reasoning_effort {effort!r}")
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        cmd.append("-")  # read the prompt from stdin
        # `codex exec` has no system-prompt flag: put the agent's instructions first.
        prompt = str(req.get("prompt") or "")
        system_prompt = str(req.get("system_prompt") or "").strip()
        if system_prompt:
            prompt = f"<agent_instructions>\n{system_prompt}\n</agent_instructions>\n\n{prompt}"
        return cmd, prompt

    def models(self) -> list[dict]:
        """Models this Codex login offers, from the CLI's own cache."""
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        try:
            data = json.loads((home / "models_cache.json").read_text())
        except (OSError, ValueError):
            return []
        out = []
        for m in data.get("models") or []:
            if isinstance(m, dict) and m.get("slug") and m.get("visibility", "list") == "list":
                out.append({"id": m["slug"], "name": m.get("display_name") or m["slug"],
                            "description": m.get("description", "")})
        return out


_WS_DEFAULT = WORKSPACE_ROOT
RUNNERS_EXEC: dict[str, CliRunner] = {
    "claude": ClaudeRunner(
        _find_bin("CLAUDE_BIN", "claude"),
        Path(os.path.expanduser(os.environ.get("CLAUDE_WORKSPACE_ROOT", "").strip() or str(_WS_DEFAULT / "claude-code"))),
        int(os.environ.get("CLAUDE_MAX_CONCURRENT", "2")),
    ),
    "codex": CodexRunner(
        _find_bin("CODEX_BIN", "codex"),
        Path(os.path.expanduser(os.environ.get("CODEX_WORKSPACE_ROOT", "").strip() or str(_WS_DEFAULT / "codex"))),
        int(os.environ.get("CODEX_MAX_CONCURRENT", "2")),
    ),
}


def claude_ready() -> bool:
    return RUNNERS_EXEC["claude"].ready()


def _snapshot_files(root: Path) -> dict[str, float]:
    """{relative path: mtime} for files under root, skipping dot-directories."""
    out: dict[str, float] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                out[str(p.relative_to(root))] = p.stat().st_mtime
            except OSError:
                continue
            if len(out) >= _FILE_SNAPSHOT_LIMIT:
                return out
    return out


def handle_cli_exec(handler: "Handler", req: dict, runner: CliRunner) -> None:
    """Run one CLI agent turn and stream NDJSON events back to the caller."""
    key = str(req.get("workdir_key") or "")
    if not str(req.get("prompt") or "").strip():
        handler._json(400, {"error": "prompt is required"})
        return
    if not _WORKDIR_KEY_RE.match(key):
        handler._json(400, {"error": "workdir_key must match [A-Za-z0-9_-]{1,64}"})
        return
    if not runner.ready():
        handler._json(503, {"error": f"{runner.name} CLI not available at {runner.bin} (not available)"})
        return
    workdir = runner.workspace_root / key
    try:
        cmd, stdin_text = runner.build(req, workdir)
    except (ValueError, TypeError) as e:
        handler._json(400, {"error": str(e)})
        return
    if not runner.slots.acquire(blocking=False):
        handler._json(429, {"error": f"{runner.name} at capacity ({runner.max_concurrent} concurrent runs)"})
        return

    try:
        timeout = max(30, min(int(req.get("timeout_sec") or 900), EXEC_MAX_TIMEOUT_SEC))
        workdir.mkdir(parents=True, exist_ok=True)
        before = _snapshot_files(workdir)

        proc = subprocess.Popen(
            cmd, cwd=str(workdir), env=runner.env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        timed_out = threading.Event()

        def _kill_on_timeout():
            timed_out.set()
            proc.kill()

        timer = threading.Timer(timeout, _kill_on_timeout)
        timer.daemon = True
        timer.start()
        stderr_tail: list[str] = []

        def _drain_stderr():
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_tail.append(line.rstrip())
                del stderr_tail[:-40]

        threading.Thread(target=_drain_stderr, daemon=True).start()

        # HTTP/1.0 response with no Content-Length: the body ends when we close.
        handler.send_response(200)
        handler.send_header("Content-Type", "application/x-ndjson")
        handler.end_headers()

        def emit(obj: dict) -> None:
            handler.wfile.write((json.dumps(obj) + "\n").encode())
            handler.wfile.flush()

        try:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(stdin_text)
            proc.stdin.close()
            emit({"type": "sutra_start", "runner": runner.name, "workdir": str(workdir), "model": req.get("model")})
            for line in proc.stdout:
                line = line.strip()
                if line:
                    handler.wfile.write((line + "\n").encode())
                    handler.wfile.flush()
            code = proc.wait()
            after = _snapshot_files(workdir)
            changed = sorted(p for p, m in after.items() if before.get(p) != m)
            emit({
                "type": "sutra_end",
                "runner": runner.name,
                "exit_code": code,
                "timed_out": timed_out.is_set(),
                "timeout_sec": timeout,
                "workdir": str(workdir),
                "files": [str(workdir / p) for p in changed[:200]],
                "stderr_tail": "\n".join(stderr_tail[-15:]),
            })
        except (BrokenPipeError, ConnectionResetError):
            sys.stderr.write(f"[fleet] {runner.name} exec ({key}): caller disconnected, stopping run\n")
            proc.kill()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
    finally:
        runner.slots.release()


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
            auth_ready = bool(GEMINI_HOME) and (GEMINI_HOME / ".gemini" / "oauth_creds.json").exists()
            self._json(200, {
                "ok": True,
                "busy": busy_now,
                "version": VERSION,
                "worker_id": WORKER_ID,
                "runners": RUNNERS,
                "auth_ready": auth_ready,
                "gemini_home": str(GEMINI_HOME) if GEMINI_HOME else None,
                "shakha_ready": shakha_ready() if SHAKHA_BIN else None,
                "claude_ready": claude_ready(),
                "codex_ready": RUNNERS_EXEC["codex"].ready(),
            })
            return
        if self.path == "/models/codex":
            if not self._auth_ok():
                self._json(403, {"error": "invalid bearer"})
                return
            self._json(200, {"models": RUNNERS_EXEC["codex"].models()})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path in ("/exec/claude", "/exec/codex"):
            if not self._auth_ok():
                self._json(403, {"error": "invalid bearer"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 4_000_000:
                    raise ValueError("body must be 1 byte to 4 MB of JSON")
                req = json.loads(self.rfile.read(length).decode())
                if not isinstance(req, dict):
                    raise ValueError("body must be a JSON object")
            except (ValueError, UnicodeDecodeError) as e:
                self._json(400, {"error": f"bad request: {e}"})
                return
            handle_cli_exec(self, req, RUNNERS_EXEC[self.path.rsplit("/", 1)[1]])
            return
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


class _ReuseAddrServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    # Threaded so a long Claude Code turn on /exec/claude doesn't block
    # /health or /run. Job execution itself is still serialized by _busy.
    allow_reuse_address = True
    daemon_threads = True


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    lock = acquire_daemon_lock()
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(f"[fleet] daemon up, listening on 127.0.0.1:{WORKER_PORT} (worker_id={WORKER_ID}, runners={RUNNERS})\n")
    if "shakha" in RUNNERS:
        threading.Thread(target=shakha_sync_loop, name="shakha-sync", daemon=True).start()
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
