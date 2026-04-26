# Dispatcher (runtime_scripts) — host-execution refactor

Working notes for an in-flight design. Plan agreed on 2026-04-24, **not yet executed**. Pick up from "Implementation start" at the bottom.

## Problem

The `runtime_scripts` extension (display name "Dispatcher") shells out to `scripts/run.sh` from inside the backend Docker container. The runner repo lives on the host. Two failures:

1. **Path invisible inside container.** `_get_base_path` raises `ValueError("Configured base_path does not exist or is not a directory: /Users/gaurav/Coding/git/runtime_scripts")` because `./backend:/app` is the only mount; host paths are not visible to the container.
2. **Even if mounted, host execution requires host binaries** (`git`, `claude`, ssh keys, git credential helper, etc.) that the backend image doesn't have. The runner is fundamentally a host-side process.

Symptom seen in chat: `Smart routing failed: generator didn't stop after throw() — underlying error: Configured base_path does not exist or is not a directory: ...`. The "generator didn't stop" wrapping is a separate streaming bug masking the real cause (see Phase 7).

## Architectural choice

Picked **Option C: host-side HTTP bridge daemon** over (A) sentinel files + fswatch (no return values, no auth) and (B) docker-socket sibling-container (still containerized, doesn't get host's `claude` / ssh / git creds).

Bridge runs on host, listens on `127.0.0.1:7475`, backend talks to it via `http://host.docker.internal:7475` (same pattern Sutra already uses for Ollama). All host-side state and execution live behind the bridge — backend container has zero filesystem visibility into the runner repo.

## Decisions locked

1. Bridge ships in **sutra-os** (`scripts/dispatcher_bridge.py`), not in the runner repo. Extension and bridge evolve together.
2. **One bridge instance, one runner repo.** Multi-runner support deferred until needed.
3. **Single shared token.** Not per-agent.
4. **Zero user action** for setup — auto-bootstrap via env vars + idempotent integration seed (mechanism below).
5. Phases 6 (docs) and 7 (streaming generator-throw bug) included in this PR.

## Auto-bootstrap mechanism (zero UI clicks)

Three pieces share env via `backend/.env` (already loaded by both compose and host-side scripts that source it):

1. **Token generation in `install.sh`** — same pattern as `SECRET_KEY` / `ENCRYPTION_KEY`. On first run (or re-run if missing), append:
   ```
   DISPATCHER_BRIDGE_TOKEN=<token_urlsafe(32)>
   DISPATCHER_BRIDGE_PORT=7475
   DISPATCHER_BASE_PATH=<prompt user once for runner repo path>
   ```
2. **Bridge reads `backend/.env`** at startup (it's a sibling file to `scripts/dispatcher_bridge.py`). Zero config flags to remember.
3. **Backend startup auto-seeds the integration row** via a new idempotent seed, called from `main.py` lifespan after the Dispatcher-agent seed:
   - No `runtime_scripts` integration row → create with `bridge_url=http://host.docker.internal:$PORT`, `bridge_token=$TOKEN`, `is_active=True`.
   - Row exists but missing `bridge_token` (current state — see "Existing state" below) → update in place.
   - Env vars unset → log warning, skip; nothing breaks.

User experience: re-run `./install.sh`, answer the runner-path prompt, `python3 scripts/dispatcher_bridge.py &` on host, `./start.sh`. Done.

## Bridge protocol

All requests `Authorization: Bearer <token>`. Bridge binds `127.0.0.1` only (loopback / docker bridge).

| Method + Path  | Body / Returns                                                                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health`  | → `{ok, base_path, version}`. Used by `test_connection`.                                                                                                                                              |
| `POST /tasks`  | body `{task_id, repo, branch, goal, priority, complexity, ultrathink, test, note}` → appends YAML block under `## pending` in `tasks.md`. Returns new task id + file location.                       |
| `GET /tasks`   | → `{pending: [...], in_progress: [...], done: [...]}`                                                                                                                                                |
| `POST /trigger`| → spawns `scripts/run.sh` detached on host, returns `{pid, log_path}`. Fire-and-forget; status via polling.                                                                                          |
| `GET /status`  | → `{active_task, plan_progress, needs_human, recent_logs}`                                                                                                                                           |

**All validation lives on the bridge** (protected branches, priority/complexity enums, duplicate ids, abs-path check, `## pending` insertion). Single source of truth — the extension is a thin client.

## File-by-file plan

### Phase 1+2 — Bridge protocol & daemon
- **New** `scripts/dispatcher_bridge.py` — stdlib-only HTTP server (no `python-dotenv`; inline `.env` parser to keep host zero-deps). ~300 LoC. Reads `../backend/.env` for `DISPATCHER_BASE_PATH`, `DISPATCHER_BRIDGE_TOKEN`, `DISPATCHER_BRIDGE_PORT`. All extension validation logic moved here.
- **New** `scripts/dispatcher_bridge.plist` — example macOS launchd plist for persistence.

### Phase 3 — Extension refactor
- **Modified** `backend/app/tools/extensions/runtime_scripts.py`:
  - Delete `_get_base_path`, `_render_task_block`, `_insert_under_pending`, `_extract_task_ids`, `_is_protected_branch`, the `_VALID_*` sets — all moved to bridge.
  - Add `_get_bridge(agent_id) → (url, token)` reading from integration row.
  - Add `_call_bridge(method, path, agent_id, json=None) → dict` using `httpx.AsyncClient` (already a dep). Centralizes auth header, timeout (5s + one retry), HTTP→tool error mapping ("Bridge unreachable at {url} — is dispatcher_bridge.py running on host?", "Bridge rejected token (401)", etc.).
  - Each `@tool` shrinks to: build payload → `_call_bridge(...)` → format response.
  - `test_connection` → single `GET /health`.
  - `EXTENSION_MANIFEST.config_fields = [bridge_url]`, `credential_fields = [bridge_token]`. Drop `base_path` from manifest (lives in bridge env now).
  - Docstrings keep semantics; add one-line "executes on host via bridge daemon" note.

### Phase 4 — Auto-bootstrap seed
- **New** `backend/app/db/seed_runtime_scripts_integration.py` — idempotent upsert. Reads `os.environ` for `DISPATCHER_BRIDGE_TOKEN` and `DISPATCHER_BRIDGE_PORT`. Builds `bridge_url = f"http://host.docker.internal:{port}"`. Writes/updates the `Integration` row. Token stored encrypted via existing credential blob mechanism.
- **Modified** `backend/app/main.py` lifespan — call `seed_runtime_scripts_integration(db)` after the Dispatcher agent seed, own try/except.

### Phase 5 — Compose & install
- **Modified** `install.sh`:
  - Generate `DISPATCHER_BRIDGE_TOKEN` (urlsafe-32) into `backend/.env` if absent.
  - Set `DISPATCHER_BRIDGE_PORT=7475` if absent.
  - Prompt once for `DISPATCHER_BASE_PATH` (default-suggest the existing value if any).
  - Print final hint: `Run the dispatcher bridge on host: python3 scripts/dispatcher_bridge.py`.
- **Modified** `docker-compose.yml` (backend service): add `extra_hosts: ["host.docker.internal:host-gateway"]` for Linux contributors if not already present. Mac/Windows get it free. **No volume mounts for runner repo.**

### Phase 6 — Docs
- **New** `docs/dispatcher.md` — short setup guide:
  - Four-line install.
  - Token generation snippet (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
  - Troubleshooting table: bridge not reachable / 401 / base_path bad / port collision.
  - Security note: bridge binds 127.0.0.1, token gates all writes.
  - launchd plist install one-liner (`launchctl load ...`).

### Phase 7 — Streaming generator-throw fix
- **Modified** `backend/app/core/orchestrator.py` ~line 540-570 (streaming path that produces "{e} — underlying error: {last_runtime_error}").
  - Root cause: when an exception propagates out of `executor.astream(...)` inside an `async for`, the wrapping outer generator must `aclose()` the inner before propagating, otherwise Python raises "generator didn't stop after throw()".
  - Fix: replace bare `raise` in streaming error-handler with `try/finally` that does `await inner_gen.aclose()` first.
  - Confirm exact line + structure when reading during implementation. Small, well-bounded change.

## Existing state to migrate

```
agents:
  Dash         id=543e0368-1c51-4110-a6b2-d71ad8852ec1   running   (does NOT have dispatcher tools)
  Dispatcher   id=0a5bba1e-b709-429e-ba57-824c19c38ea4   running   (seeded with 4 dispatcher tools)

integrations.runtime_scripts:
  id=795e1a2e-e371-4d9f-bd54-7944746277b8
  is_active=true
  extra_config={"base_path": "/Users/gaurav/Coding/git/runtime_scripts"}
  ← needs migration: drop base_path from extra_config, add bridge_url + bridge_token (latter encrypted)

backend/.env:
  ← needs DISPATCHER_BRIDGE_TOKEN, DISPATCHER_BRIDGE_PORT, DISPATCHER_BASE_PATH appended

orphan task created during the failed run:
  id=8c858edf-c530-4121-aaf1-862dcec56ca6
  title="Summarize docs/design.md file" status=todo priority=low
  creator_agent_id=Dash, assignee_agent_id=NULL
  ← cosmetic; can stay or be deleted
```

Migration story: after the changes, re-run `./install.sh` → token generated → start backend → seed updates the existing integration row in place (keeps id=795e1a2e..., sets bridge_url + bridge_token, drops base_path) → start `python3 scripts/dispatcher_bridge.py` on host → ask Dash to dispatch → routes to Dispatcher → tool calls bridge → bridge runs on host with full env. Works.

## Risks / watch-fors during implementation

- **`.env` parsing in the bridge** must handle quoted values, comments, blank lines. Inline parser, no external dep.
- **Token rotation** — re-running `install.sh` won't rotate (only writes if missing). Document: rotate = remove line, re-run install, restart bridge + backend.
- **Bridge not running when backend boots** — fine, integration seeded anyway; tool calls fail clean with "bridge unreachable" until user starts bridge.
- **`host.docker.internal` cold resolution** — set httpx timeout 5s + one retry.
- **Existing integration row** — auto-migrated by seed (don't delete it; update in place to preserve id).
- **macOS file ownership** — irrelevant since we're not bind-mounting; bridge runs as host user, no uid/gid bridging.

## Total surface

~7 files changed/added in sutra-os, ~600 LoC net (mostly bridge.py and install.sh additions; extension shrinks). No new runtime deps in backend (httpx already used). Zero deps on host (stdlib bridge).

## Open follow-up (not in scope)

- Optional `start_with_bridge.sh` wrapper or `Makefile` target that spawns the bridge alongside `start.sh` so it's truly one command. Cheap to add; user said yes is welcome but defer until core lands.

## Implementation start

Begin with Phase 1+2 (bridge daemon) since everything else depends on its protocol shape. Then Phase 3 (extension refactor) so end-to-end smoke-test is possible. Phase 4 (auto-seed) and Phase 5 (install.sh) lock in the zero-action setup. Phase 6 (docs) and Phase 7 (streaming bug) close the PR.

Smoke test after each phase:
- After 1+2: `curl -H "Authorization: Bearer $TOKEN" http://localhost:7475/health` from host.
- After 3+4: ask Dispatcher agent (via Dash → ask_agent) to "queue a trivial test task" and verify `tasks.md` updated on host.
- After 5: full `./install.sh` → fresh `./start.sh` → repeat smoke test, no manual UI clicks.
- After 7: induce a tool error mid-stream (e.g. wrong token) and confirm the SSE response contains the underlying error cleanly, no "generator didn't stop".
