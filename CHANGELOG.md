# Sutra — Release Notes

---

## 2026-03-18 — Token Limit Guard (Prevent 413 Errors)

### Problem
The Dash agent (using `moonshotai/kimi-k2-instruct` via OpenRouter) consistently hit HTTP 413 (Payload Too Large) errors because assembled messages (system prompt + memory context + chat history) were never checked against the model's context window before sending.

### New: Token Guard (`core/token_guard.py`)
- **Model context window registry** — Known input token limits for OpenRouter, OpenAI, Anthropic, Google, Groq, Perplexity models with conservative 32K fallback for unknown models
- **Fast token estimation** — Char-based heuristic (~4 chars/token), no external dependencies
- **Pre-request size guard** — Estimates total tokens and auto-trims before LLM call (80% safety margin)
- **Three-phase trimming** — (1) Remove oldest chat history, (2) truncate memory context to 50%, (3) aggressive stub truncation
- **Emergency trim** — Last-resort recovery for 413 errors: keeps system prompt + last 5 messages

### New: 413 Catch-and-Retry
- Both `route_message()` and `stream_message()` now catch 413 / "too large" / "context_length" errors
- On catch: applies emergency trim and retries once with reduced context
- If retry also fails: returns clean user-facing error instead of raw exception

### Enhanced: Execution Trace — Input Token Tracking
- New `input_tokens` column on `ExecutionTrace` model (nullable integer)
- Estimated input tokens saved alongside actual output tokens on every trace
- DB migration added for `execution_traces.input_tokens`

### Enhanced: Monitor Metrics — Per-Agent Token Stats
- `GET /api/monitor/metrics` now returns per-agent:
  - `total_tokens_today` — Total tokens consumed today
  - `total_input_tokens_today` — Total estimated input tokens today
  - `avg_context_utilization` — Average input tokens as % of model context window
  - `context_limit` — Model's usable context window (for running agents)

### Modified Files
- **`core/token_guard.py`** — NEW: context window registry, token estimation, message trimming, emergency trim
- **`core/orchestrator.py`** — `_guard_token_limit()` helper called in both sync/stream paths; 413 catch-and-retry; `_save_trace()` accepts `input_tokens`
- **`models/trace.py`** — Added `input_tokens` column
- **`core/db_migrations.py`** — Migration for `execution_traces.input_tokens`
- **`api/routes/monitor.py`** — Per-agent token utilization stats in `/metrics`

### Architecture
```
Request → Build Messages → Token Guard (estimate + trim) → LLM Call
                                                              ↓ (if 413)
                                                     Emergency Trim → Retry Once
```

---

## 2026-03-17 — Phase 5.2 + 5.4: Self-Healing & Performance

### New: Retry with Exponential Backoff (`core/retry.py`)
- LLM and tool calls automatically retry on transient errors (connection, timeout)
- Configurable: max 3 retries, exponential delay (1s → 2s → 4s) with jitter
- Only retries safe errors — logic/auth failures fail immediately

### New: Circuit Breaker (`core/circuit_breaker.py`)
- Three-state pattern: CLOSED → OPEN → HALF_OPEN → CLOSED
- Trips after 5 failures within 60s; auto-recovers after 30s cooldown
- Per-service registry (one breaker per LLM provider/model)
- When open, returns user-friendly "temporarily unavailable" instead of crashing

### New: Agent Watchdog (`core/watchdog.py`)
- Background health monitor checks every 60s
- Auto-restarts unresponsive agents (no heartbeat for 3× interval)
- Max 3 consecutive restart attempts before giving up
- Audit log entry created on each auto-restart
- Register/unregister on agent start/stop

### New: Prompt Cache (`core/prompt_cache.py`)
- Redis-backed cache for LLM responses (30-min TTL)
- Cache key: SHA256 of model + system prompt + last 3 messages
- Skips caching for time-sensitive queries ("today", "now", "current")
- Hit/miss stats exposed via monitoring endpoint

### New: Conversation Windowing (`core/conversation_window.py`)
- Long conversations load only last 20 messages + LLM-generated summary of older context
- Summary cached in Redis (1h TTL) to avoid repeated summarization
- Fallback to extractive summary if LLM unavailable
- Replaces previous unbounded history loading in both sync and streaming chat

### New: Database Performance Indexes (`core/db_indexes.py`)
- 9 indexes created on startup (IF NOT EXISTS — safe to re-run):
  - `execution_traces (agent_id, created_at DESC)`
  - `execution_traces (had_error) WHERE had_error = true`
  - `messages (conversation_id, created_at)`
  - `memories (agent_id, created_at DESC)`
  - `usage_records (agent_id, created_at DESC)`
  - `tasks (assignee_agent_id, status)`
  - `audit_log (created_at DESC)`
  - `conversations (agent_id, updated_at DESC)`
  - `approval_requests (status, created_at DESC)`

### New: Resilience Monitoring Endpoint
- `GET /api/monitor/health/resilience` — returns circuit breaker states, prompt cache stats, and watchdog status

### Modified Files
- **`orchestrator.py`** — LLM calls wrapped in retry + circuit breaker; prompt cache check before invocation; watchdog heartbeat on success; graceful CircuitOpenError handling for both sync and streaming
- **`agent_manager.py`** — Watchdog register on agent start, unregister on stop
- **`chat.py`** — Replaced unbounded `SELECT * FROM messages` with windowed history (20 recent + summary)
- **`main.py`** — DB indexes created on startup; watchdog started after agent restore; watchdog stopped on shutdown
- **`monitor.py`** — Added `/health/resilience` endpoint

### Architecture
```
Request → Prompt Cache Check → Circuit Breaker → Retry (backoff) → LLM → Watchdog Heartbeat
                                     ↓ (if open)
                              "Temporarily unavailable"
```

---

## 2026-03-17 — Phase 5.2 + 5.4 (cont.): Approval Timeouts & Batch Embeddings

### Enhanced: Approval Gate Timeouts (`core/scheduler.py`)
- **Expiry warnings**: 15 minutes before an approval expires, a Telegram notification is sent to the default chat
- **Expiry notifications**: When an approval auto-expires, a notification is sent with title, category, and risk level
- **Idempotent warnings**: Uses `_expiry_warned` flag in context JSON to avoid duplicate notifications
- Existing `expire_pending_approvals()` job (runs every 5 min) now handles the full lifecycle: warn → expire → notify

### New: Batch Embedding Queue (`core/embeddings.py`)
- **EmbeddingBatcher** class queues individual `aembed()` calls and processes them in batches
- Reduces API calls from N individual requests to ceil(N/20) batch calls
- Auto-flushes when queue reaches 20 items OR after 300ms of inactivity
- Each caller gets an asyncio.Future that resolves when their batch completes
- Falls back to individual embedding if batch call fails
- Stats tracked: `batches_processed`, `items_processed`, `queue_size`
- **embed_batch()** method added to EmbeddingService for synchronous batch embedding via `embed_documents()`
- `aembed()` now routes through the batcher instead of running individual calls

### Modified Files
- **`core/embeddings.py`** — Added `EmbeddingBatcher` class, `embed_batch()` method, `aembed()` now uses batcher
- **`core/scheduler.py`** — `expire_pending_approvals()` enhanced with warning + expiry notification pipeline

---

## 2026-03-17 — Phase 5.1: Memory Revolution (Three-Tier Self-Editing Memory)

### New: Three-Tier Memory Architecture
- **Core tier** — Always injected into agent context (like RAM). Agent identity, key facts, active goals.
- **Recall tier** — Searchable conversation history + extracted facts. Default tier for new memories.
- **Archival tier** — Long-term compressed storage. Infrequently accessed, consolidated from old recall memories.

### New: Self-Editing Memory Tools (`tools/memory_tools.py`)
- **`save_memory`** — Enhanced with `tier` parameter (core/recall/archival), source tracking
- **`search_memory`** — Now includes memory IDs and tier labels in results; supports tier filtering
- **`memory_update`** — Rewrite existing memory content (re-embeds automatically)
- **`memory_forget`** — Soft-delete a memory with a reason (agent can prune its own knowledge)
- **`memory_promote`** — Move memory between tiers (e.g., recall → core, core → archival)

### New: Memory Decay System
- Decay score = importance × recency_factor × frequency_factor
- Recency: 7-day half-life (`0.5^(days_since_access / 7)`)
- Frequency: logarithmic boost from access count (`log10(access_count + 1)`)
- Core memories exempt from decay (always score 1.0)

### New: Memory Consolidation (`core/memory_service.py`)
- Background job (daily 3 AM Pacific) consolidates old low-decay recall memories
- LLM-generated summary of grouped memories → single archival memory
- Expired archival memories (past TTL) cleaned up automatically
- Cross-agent knowledge sharing via `share_knowledge()` method

### Enhanced: Context Injection (`core/orchestrator.py`)
- Core memories (Tier 1) always injected as "Core identity & knowledge" system message
- Recall search results shown separately as "Relevant memories from past interactions"
- Two-section memory context gives agents persistent identity + situational recall

### Enhanced: Memory API (`api/routes/memory.py`)
- `GET /api/memory/` — Added `tier` query parameter for filtering
- `GET /api/memory/search` — Added `tier` query parameter
- `POST /api/memory/` — Added `tier` field (defaults to recall)
- `PATCH /api/memory/{id}/promote` — New endpoint to move memory between tiers

### Enhanced: Memory Model (`models/memory.py`)
- New `MemoryTier` enum: core, recall, archival
- New fields: `tier`, `decay_score`, `source` (auto/agent/user/consolidation), `is_deleted`, `deleted_reason`, `consolidated_from` (JSON list of source memory IDs), `ttl_days`

### Enhanced: Frontend Memory Page
- Tier stats bar with toggle filters (Core / Recall / Archival)
- Tier badges and decay score bar on each memory card
- Promote/demote buttons on hover
- Tier selector in Add Memory form
- Source attribution display

### Modified Files
- **`models/memory.py`** — MemoryTier enum, 7 new fields on Memory model
- **`core/memory_service.py`** — Complete rewrite: three-tier CRUD, decay calculation, consolidation pipeline, cross-agent sharing
- **`tools/memory_tools.py`** — 3 new tools (memory_update, memory_forget, memory_promote), enhanced save_memory/search_memory
- **`tools/registry.py`** — MEMORY_TOOL_IDS expanded (2→5), 3 new TOOL_CATALOG entries
- **`core/orchestrator.py`** — `_fetch_memory_context()` now fetches core memories + recall search
- **`api/routes/memory.py`** — Tier filtering, promote endpoint, tier in create
- **`api/schemas.py`** — MemoryCreate.tier, MemoryResponse +tier/decay_score/source/is_deleted
- **`core/scheduler.py`** — `run_memory_maintenance()` daily job (decay update + consolidation)
- **`frontend/lib/api.ts`** — MemoryTier type, Memory interface extended, memoryApi.promote()
- **`frontend/app/memory/page.tsx`** — Tier UI: stats bar, filters, badges, decay bar, promote/demote

### Architecture
```
Agent message → Core memories (always) + Recall search (query-relevant)
                    ↓
              Injected as SystemMessage into LangGraph context
                    ↓
Agent tools: save_memory → recall tier
             memory_promote → core/recall/archival
             memory_forget → soft-delete
             memory_update → re-embed
                    ↓
Daily 3 AM: decay update → consolidation → TTL cleanup
```

---

## 2026-03-17 — System Configuration UI (Runtime Settings)

### Overview
All previously hardcoded configuration values are now configurable from the Settings page at runtime. Changes are persisted to the database and take effect immediately without requiring a server restart.

### 27 Configurable Settings across 7 categories:

**Resilience** — LLM retry (max retries, base delay, max delay), circuit breaker (failure threshold, window, cooldown)

**Watchdog** — Health check interval, timeout multiplier, max auto-restarts

**Cache** — Prompt cache TTL, cache key message count

**Conversation** — Chat window size, summary LLM provider/model, summary cache TTL

**Memory** — Decay half-life, consolidation age/threshold, archival delete days, core max tokens, maintenance cron

**Embeddings** — Batch size, flush interval

**Rate Limits** — Chat, login, register, token refresh rate limits

### New Files
- **`backend/app/models/system_config.py`** — SystemConfig model (single-row JSON overrides table)
- **`backend/app/core/system_settings.py`** — Settings service with in-memory cache, DB overrides, schema validation
- **`backend/app/api/routes/system_settings.py`** — `GET/PATCH/DELETE /api/settings/system` endpoints

### Modified Files
- **`backend/app/config.py`** — 27 new fields with env var defaults for all configurable values
- **`backend/app/main.py`** — Loads system settings on startup, registers new route
- **`backend/app/models/__init__.py`** — Imports SystemConfig
- **`backend/app/core/orchestrator.py`** — Reads retry/circuit breaker config from sys_settings
- **`backend/app/core/watchdog.py`** — Properties read from sys_settings dynamically
- **`backend/app/core/prompt_cache.py`** — TTL/max_messages as properties from sys_settings
- **`backend/app/core/conversation_window.py`** — Window size, summary LLM, cache TTL from sys_settings
- **`backend/app/core/memory_service.py`** — Decay/consolidation constants from sys_settings
- **`backend/app/core/embeddings.py`** — Batcher config from sys_settings
- **`backend/app/core/scheduler.py`** — Memory maintenance cron from config
- **`backend/app/api/routes/auth.py`** — Rate limits from config (lambda-based)
- **`backend/app/api/routes/chat.py`** — Rate limits from config (lambda-based)
- **`frontend/lib/api.ts`** — SystemSettingSchema type, systemSettingsApi
- **`frontend/app/settings/page.tsx`** — Full System Configuration UI with grouped settings, save/reset, override badges
