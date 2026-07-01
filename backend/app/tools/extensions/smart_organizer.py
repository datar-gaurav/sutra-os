"""Smart Email/Notification Organizer extension for Sutra OS.

Ingests Apple Mail, classifies it locally, extracts actionable tasks to Apple
Reminders, logs important-but-non-actionable items to a daily Apple Note, and
learns per-user importance over time — while keeping ~90%+ of processing on
local models and reserving frontier calls for low-confidence/high-stakes items.

Architecture (Docker-aware)
---------------------------
The Sutra backend runs in a Linux container, which cannot reach macOS apps
(`osascript`, Mail, Reminders, Notes) or `~/Library/Mail`. So this extension is
a thin **bridge client**: all intelligence + state live here (classification,
priors, few-shot, the plugin SQLite store), while the macOS I/O is delegated to
a host-side daemon — `scripts/smart_organizer_bridge.py` — over
`http://host.docker.internal:PORT` with a shared bearer token, mirroring the
`runtime_scripts` / `dispatcher_bridge.py` pattern. Configure:
  - bridge_url   (config)      — e.g. http://host.docker.internal:7477
  - bridge_token (credential)  — shared token, set by install.sh

LLM configuration
-----------------
Every model call routes through Sutra's existing purpose-based LLM settings and
keys. Configure two LLM Purposes and reference them here:
  - batch_purpose_id    → Tier 1 local classify/extract (point slots at Ollama)
  - frontier_purpose_id → Tier 3 escalation (system-wide default frontier)
The extension holds no provider API keys of its own; rate limits, fallback
chains, and circuit breaking come for free via the smart router.

Scheduling
----------
The batch cycle reuses the existing container-side Job scheduler: create a Job
(execution_type='prompt', cron e.g. "0 */4 * * *") targeting a Smart-Organizer-
enabled agent. Real-time urgency is driven by a Mail.app rule that posts to the
host bridge's /arrival endpoint.

Provides:
  - smart_organizer_ingest:           Tier 0 — read new mail, filter, enqueue
  - smart_organizer_triage_urgent:    Urgency pre-check + immediate classify
  - smart_organizer_run_batch:        Tier 1 (+3) — classify/extract/route batch
  - smart_organizer_record_feedback:  Log a correction, update priors/embeddings
  - smart_organizer_feedback_summary: Pull-based "what changed" summary
  - smart_organizer_test_rules:       Dry-run the Tier 0 rule set
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from typing import Any
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

EXTENSION_ID = "smart_organizer"

EXTENSION_MANIFEST = {
    "id": EXTENSION_ID,
    "name": "Smart Organizer",
    "description": (
        "Triage Apple Mail locally: extract tasks to Reminders, log FYIs to "
        "a daily Note, and learn what matters — using Sutra's purpose-based LLMs."
    ),
    "icon": "inbox",
    "version": "0.1.0",
    "author": "Gaurav Datar",
    # The only secret is the shared token for the host bridge daemon; frontier
    # keys come from the referenced LLM Purpose, not from this extension.
    "credential_fields": [
        {
            "key": "bridge_token",
            "label": "Host Bridge Token",
            "secret": True,
            "placeholder": "Shared bearer token (SMART_ORGANIZER_BRIDGE_TOKEN, set by install.sh)",
        },
    ],
    "config_fields": [
        {
            "key": "bridge_url",
            "label": "Host Bridge URL",
            "secret": False,
            "placeholder": "http://host.docker.internal:7477",
        },
        {
            "key": "batch_purpose_id",
            "label": "Batch LLM Purpose (Tier 1, local)",
            "secret": False,
            "placeholder": "LLM Purpose id whose slots point at a local Ollama model",
        },
        {
            "key": "frontier_purpose_id",
            "label": "Frontier LLM Purpose (Tier 3, escalation)",
            "secret": False,
            "placeholder": "LLM Purpose id for the system-wide default frontier model",
        },
        {
            "key": "frontier_enabled",
            "label": "Enable frontier escalation (true/false)",
            "secret": False,
            "placeholder": "true",
        },
        {
            "key": "confidence_threshold",
            "label": "Escalation confidence threshold (0-1)",
            "secret": False,
            "placeholder": "0.7",
        },
        {
            "key": "batch_cadence_hours",
            "label": "Batch cycle cadence (hours)",
            "secret": False,
            "placeholder": "4",
        },
        {
            "key": "urgency_window_hours",
            "label": "Urgency deadline window (hours)",
            "secret": False,
            "placeholder": "2",
        },
        {
            "key": "sender_allowlist",
            "label": "Sender allowlist (one per line)",
            "secret": False,
            "placeholder": "boss@example.com",
        },
        {
            "key": "sender_blocklist",
            "label": "Sender blocklist (one per line)",
            "secret": False,
            "placeholder": "no-reply@promo.example.com",
        },
        {
            "key": "regex_rules",
            "label": "Tier 0 discard regex rules (one per line)",
            "secret": False,
            "placeholder": r"unsubscribe|view in browser",
        },
        {
            "key": "sqlite_path",
            "label": "Plugin data store path (in-container)",
            "secret": False,
            "placeholder": ".local/smart_organizer/smart_organizer.db",
        },
        {
            "key": "log_retention_days",
            "label": "Decision-log retention (days)",
            "secret": False,
            "placeholder": "90",
        },
    ],
    "tool_ids": [
        "smart_organizer_ingest",
        "smart_organizer_triage_urgent",
        "smart_organizer_run_batch",
        "smart_organizer_record_feedback",
        "smart_organizer_feedback_summary",
        "smart_organizer_test_rules",
    ],
    # Routes tasks into the user's Reminders/Notes — side-effecting.
    "is_dangerous": True,
}

# ─── Defaults (all overridable via config_fields) ────────────────────────────
DEFAULT_SQLITE_PATH = ".local/smart_organizer/smart_organizer.db"
DEFAULT_CONFIDENCE_THRESHOLD = 0.7
DEFAULT_BATCH_CADENCE_HOURS = 4
DEFAULT_URGENCY_WINDOW_HOURS = 2
DEFAULT_LOG_RETENTION_DAYS = 90
FEEDBACK_NAMESPACE = "smart-organizer-feedback"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_ref   TEXT UNIQUE,
    sender        TEXT,
    subject       TEXT,
    received_at   TEXT,
    body_snippet  TEXT,
    urgency       TEXT,
    state         TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sender        TEXT,
    subject       TEXT,
    body_snippet  TEXT,
    model_label   TEXT,
    user_label    TEXT,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sender_priors (
    sender        TEXT PRIMARY KEY,
    score         REAL NOT NULL DEFAULT 0.0,
    sample_count  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS decision_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_ref   TEXT,
    tier          TEXT,
    decision      TEXT,
    confidence    REAL,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS classifications (
    message_ref     TEXT PRIMARY KEY,
    label           TEXT,
    type            TEXT,
    summary         TEXT,
    due_date        TEXT,
    priority        TEXT,
    confidence      REAL,
    source          TEXT,
    escalated       INTEGER NOT NULL DEFAULT 0,
    needs_review    INTEGER NOT NULL DEFAULT 0,
    reminder_id     TEXT,
    reminder_scanned INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Few-shot vectors for corrected examples. Plugin-local table = the
-- 'smart-organizer-feedback' namespace (FR-26): isolated by construction.
CREATE TABLE IF NOT EXISTS feedback_embeddings (
    feedback_id   INTEGER PRIMARY KEY,
    embedding     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key           TEXT PRIMARY KEY,
    value         TEXT
);
"""


# ─── Config plumbing ─────────────────────────────────────────────────────────
async def _get_config(agent_id: str) -> dict:
    """Fetch this extension's extra_config (agent-specific, else system-wide).

    Unlike ``get_extension_creds`` this does not require stored credentials —
    the Smart Organizer has none — so it reads the Integration row directly.
    """
    from sqlalchemy import nullslast, select

    from app.db.session import async_session_factory
    from app.models.integration import Integration

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == EXTENSION_ID, Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row:
        raise ValueError(
            f"No active '{EXTENSION_ID}' integration found. "
            f"Please configure it in Settings > Integrations."
        )
    return dict(row.extra_config or {})


# ─── Host bridge client (macOS I/O over http://host.docker.internal:PORT) ─────
async def _get_bridge(agent_id: str) -> tuple[str, str]:
    """Return (bridge_url, bridge_token) from the integration row."""
    from sqlalchemy import nullslast, select

    from app.core.vault import decrypt_secret
    from app.db.session import async_session_factory
    from app.models.integration import Integration

    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == EXTENSION_ID, Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()

    agent_specific = next((r for r in rows if r.agent_id == agent_id), None)
    system_wide = next((r for r in rows if r.agent_id is None), None)
    row = agent_specific or system_wide
    if not row:
        raise ValueError(f"No active '{EXTENSION_ID}' integration found.")

    url = ((row.extra_config or {}).get("bridge_url") or "").rstrip("/")
    if not url:
        raise ValueError(
            "Smart Organizer integration is missing bridge_url. Set it in "
            "Settings > Integrations (e.g. http://host.docker.internal:7477)."
        )
    token = ""
    if row.credentials_enc:
        try:
            token = json.loads(decrypt_secret(row.credentials_enc)).get("bridge_token") or ""
        except Exception:  # noqa: BLE001
            pass
    return url, token


async def _call_bridge(
    method: str,
    path: str,
    agent_id: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> Any:
    """Call the host bridge with auth and one retry on network errors."""
    import httpx

    url, token = await _get_bridge(agent_id)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    full_url = f"{url}{path}"

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(full_url, headers=headers, params=params)
                else:
                    resp = await client.post(full_url, headers=headers, json=json_body or {})
            break
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise ValueError(
                f"Host bridge unreachable at {url} — is scripts/smart_organizer_bridge.py "
                "running on the host?"
            ) from exc

    if resp.status_code == 401:
        raise ValueError("Host bridge rejected the token (401) — check SMART_ORGANIZER_BRIDGE_TOKEN.")
    if not resp.is_success:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise ValueError(f"Host bridge error {resp.status_code}: {detail}")
    return resp.json()


def _resolve_sqlite_path(config: dict) -> Path:
    raw = (config.get("sqlite_path") or "").strip() or DEFAULT_SQLITE_PATH
    return Path(os.path.expanduser(raw))


def _get_float(value, default: float) -> float:
    """Coerce a config/model value to float, falling back to default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_bool(value, default: bool) -> bool:
    """Coerce a config value to bool; accepts true/false/1/0/yes/no strings."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _connect(config: dict) -> sqlite3.Connection:
    """Open (creating if needed) the plugin-local SQLite store with schema applied.

    Kept synchronous for the scaffold; volume is low and local. A later PR may
    move to aiosqlite if batch sizes warrant it.
    """
    path = _resolve_sqlite_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for stores created by an earlier version."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(classifications)")}
    additions = {
        "needs_review": "INTEGER NOT NULL DEFAULT 0",
        "reminder_id": "TEXT",
        "reminder_scanned": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, decl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE classifications ADD COLUMN {name} {decl}")


# ─── Tier 0: rule engine (pure, unit-testable) ───────────────────────────────
def _parse_lines(raw: str | None) -> list[str]:
    """Split a newline-delimited config textarea into trimmed, non-empty lines."""
    if not raw:
        return []
    return [ln.strip() for ln in str(raw).splitlines() if ln.strip()]


def _compile_regex_rules(patterns: list[str]) -> list[tuple[str, re.Pattern]]:
    """Compile discard regexes (case-insensitive); skip invalid ones with a log."""
    compiled: list[tuple[str, re.Pattern]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat, re.IGNORECASE)))
        except re.error as e:
            logger.warning("smart_organizer: invalid Tier 0 regex %r skipped: %s", pat, e)
    return compiled


def _sender_matches(sender: str, entry: str) -> bool:
    """Case-insensitive substring match — supports full addresses or bare domains."""
    return entry.lower() in (sender or "").lower()


def evaluate_rules(sender: str, subject: str, config: dict) -> tuple[str, str]:
    """Decide a message's Tier 0 fate from the configured rules.

    Precedence: allowlist (keep, wins over everything) > blocklist (discard) >
    discard regex on sender/subject (discard) > default keep.

    Returns:
        (decision, reason) where decision is "keep" or "discard".
    """
    allow = _parse_lines(config.get("sender_allowlist"))
    block = _parse_lines(config.get("sender_blocklist"))
    regexes = _compile_regex_rules(_parse_lines(config.get("regex_rules")))

    for entry in allow:
        if _sender_matches(sender, entry):
            return "keep", f"allowlist:{entry}"
    for entry in block:
        if _sender_matches(sender, entry):
            return "discard", f"blocklist:{entry}"
    haystack = f"{sender}\n{subject}"
    for pat, rx in regexes:
        if rx.search(haystack):
            return "discard", f"regex:{pat}"
    return "keep", "default"


# ─── Tier 0: new mail via host bridge ────────────────────────────────────────
async def _bridge_get_new_mail(agent_id: str, after_rowid: int, limit: int) -> list[dict]:
    """Fetch new messages (ROWID > after_rowid) from the host bridge.

    The bridge reads Mail's Envelope Index on the host and returns dicts with
    rowid, message_id, sender, subject, received_at (ISO 8601), and read.
    """
    data = await _call_bridge(
        "GET", "/mail/new", agent_id,
        params={"after": after_rowid, "limit": max(1, limit)},
    )
    if isinstance(data, dict):
        return data.get("messages", [])
    return data or []


async def _bridge_get_body(agent_id: str, message_id: str) -> str:
    """Fetch a stripped message body from the host bridge; "" on any failure."""
    if not message_id or message_id.startswith("rowid:"):
        return ""
    try:
        data = await _call_bridge(
            "GET", "/mail/body", agent_id, params={"message_id": message_id}
        )
    except ValueError as e:
        logger.debug("smart_organizer: body fetch failed for %s: %s", message_id, e)
        return ""
    return (data.get("body") if isinstance(data, dict) else "") or ""


# ─── Plugin-store helpers ────────────────────────────────────────────────────
def _meta_get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def _purge_old_logs(conn: sqlite3.Connection, retention_days: int) -> int:
    """Delete decision-log rows older than the retention window (NFR-5)."""
    days = max(1, int(retention_days))
    cur = conn.execute(
        "DELETE FROM decision_log WHERE timestamp < datetime('now', ?)",
        (f"-{days} days",),
    )
    return cur.rowcount or 0


# ─── Tier 1: classification & extraction ─────────────────────────────────────
LABELS = ("Actionable", "Important-FYI", "Junk")


def _load_sender_priors(conn: sqlite3.Connection, senders: list[str]) -> dict[str, float]:
    """Return {sender: importance_score} for the given senders that have priors."""
    priors: dict[str, float] = {}
    for sender in set(s for s in senders if s):
        row = conn.execute(
            "SELECT score FROM sender_priors WHERE sender = ?", (sender,)
        ).fetchone()
        if row is not None:
            priors[sender] = row["score"]
    return priors


def _fetch_feedback_candidates(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Fetch recent corrections (with any stored embedding) for few-shot use."""
    rows = conn.execute(
        "SELECT f.id, f.sender, f.subject, f.body_snippet, f.user_label, e.embedding "
        "FROM feedback f LEFT JOIN feedback_embeddings e ON e.feedback_id = f.id "
        "ORDER BY f.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _safe_embed(text: str) -> list[float] | None:
    """Embed text via Sutra's embedding service; None on any failure."""
    if not text.strip():
        return None
    try:
        from app.core.embeddings import embedding_service

        return await embedding_service.aembed(text)
    except Exception as e:  # noqa: BLE001
        logger.debug("smart_organizer: embedding failed: %s", e)
        return None


async def _rank_fewshot(candidates: list[dict], query_text: str, k: int = 3) -> list[dict]:
    """Return up to k corrections most similar to the batch (FR-15/FR-26).

    Uses the namespaced feedback embeddings when available; otherwise falls back
    to the most recent corrections (candidates are pre-sorted newest-first).
    """
    if not candidates:
        return []
    qvec = await _safe_embed(query_text)
    embedded = [c for c in candidates if c.get("embedding")]
    if not qvec or not embedded:
        return candidates[:k]
    scored = []
    for c in embedded:
        try:
            vec = json.loads(c["embedding"])
        except (json.JSONDecodeError, TypeError):
            continue
        scored.append((_cosine(qvec, vec), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def _signal_for_label(label: str) -> float:
    """Map a corrected label to a sender-importance signal in [-1, 1]."""
    return {"Actionable": 1.0, "Important-FYI": 0.5, "Junk": -1.0}.get(label, 0.0)


def _update_sender_prior(conn: sqlite3.Connection, sender: str, signal: float) -> tuple[float, int]:
    """Fold a signal into the sender's rolling importance mean. Returns (score, n)."""
    if not sender:
        return 0.0, 0
    row = conn.execute(
        "SELECT score, sample_count FROM sender_priors WHERE sender = ?", (sender,)
    ).fetchone()
    score, n = (row["score"], row["sample_count"]) if row else (0.0, 0)
    new_score = (score * n + signal) / (n + 1)
    new_n = n + 1
    conn.execute(
        "INSERT INTO sender_priors (sender, score, sample_count, updated_at) "
        "VALUES (?, ?, ?, datetime('now')) "
        "ON CONFLICT(sender) DO UPDATE SET "
        "score=excluded.score, sample_count=excluded.sample_count, updated_at=excluded.updated_at",
        (sender, new_score, new_n),
    )
    return new_score, new_n


_SYSTEM_PROMPT = (
    "You are an on-device email triage classifier. For EACH input message, "
    "classify it and extract structured fields. Respond with ONLY a JSON array "
    "(no prose, no markdown fences). Each element must be an object with keys:\n"
    '  id (int, echo the input id exactly)\n'
    "  label (one of \"Actionable\", \"Important-FYI\", \"Junk\")\n"
    '  type ("task" or "fyi")\n'
    "  summary (string, one line)\n"
    "  due_date (ISO-8601 date/time or null)\n"
    '  priority ("high", "medium", or "low")\n'
    "  confidence (number 0..1 — your certainty in the label)\n"
    "  source_sender (string)\n"
    "  source_subject (string)\n"
    "Actionable = the user must do something; Important-FYI = worth knowing but "
    "no action; Junk = promotional/automated/no value. Be conservative with "
    "confidence when signals conflict."
)


def _build_user_prompt(items: list[dict], priors: dict[str, float], fewshot: list[dict]) -> str:
    """Assemble the batch user prompt with sender priors + few-shot corrections."""
    parts: list[str] = []
    if priors:
        prior_lines = "\n".join(
            f"  {s}: importance {score:+.2f}" for s, score in priors.items()
        )
        parts.append(
            "Per-sender importance priors (learned from this user; higher = more "
            "important). Weight these:\n" + prior_lines
        )
    if fewshot:
        ex_lines = "\n".join(
            f'  from {e["sender"]!r} subj {e["subject"]!r} → correct label: {e["user_label"]}'
            for e in fewshot
        )
        parts.append("Recent user corrections (learn from these):\n" + ex_lines)

    batch = [
        {
            "id": it["id"],
            "sender": it["sender"],
            "subject": it["subject"],
            "body": it["body"],
        }
        for it in items
    ]
    parts.append(
        "Classify every message in this batch and return the JSON array:\n"
        + json.dumps(batch, ensure_ascii=False, indent=2)
    )
    return "\n\n".join(parts)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    return text


def _parse_classifications(text: str) -> list[dict]:
    """Parse the model's JSON array; tolerate fences and a single trailing object.

    Returns [] if nothing parseable is found (caller degrades gracefully).
    """
    cleaned = _strip_json_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to salvage the first JSON array in the text.
        match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)]


def _normalize_label(raw) -> str:
    """Map a model label onto the canonical set; default to Important-FYI."""
    val = str(raw or "").strip().lower()
    for label in LABELS:
        if label.lower() == val:
            return label
    if "action" in val:
        return "Actionable"
    if "junk" in val or "spam" in val:
        return "Junk"
    return "Important-FYI"


async def _run_classifier(
    purpose_id: str,
    system_prompt: str,
    items: list[dict],
    priors: dict[str, float],
    fewshot: list[dict],
) -> tuple[str, str, list[dict]]:
    """Resolve a model for ``purpose_id`` and classify ``items`` in one pass.

    Shared by Tier 1 (local batch) and Tier 3 (frontier escalation) — both route
    through the smart router so they honor rate limits, fallback slots, and the
    existing provider keys. Raises on routing/model failure; the caller decides
    how to degrade.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.core.callbacks import UsageCallbackHandler
    from app.core.llm_registry import llm_registry
    from app.core.smart_router import resolve_model
    from app.db.session import async_session_factory

    user_prompt = _build_user_prompt(items, priors, fewshot)
    est_tokens = (len(system_prompt) + len(user_prompt)) // 4 + 256 * len(items)
    async with async_session_factory() as db:
        provider, model = await resolve_model(purpose_id, est_tokens, db)

    llm = llm_registry.get_chat_model(
        provider, model, temperature=0.0, max_tokens=4096, streaming=False
    )
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)],
        config={"callbacks": [UsageCallbackHandler()]},
    )
    content = response.content
    if isinstance(content, list):
        content = "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return provider, model, _parse_classifications(str(content))


# ─── Tier 3: escalation gate ─────────────────────────────────────────────────
_ESCALATION_SNIPPET_CHARS = 800
_ESCALATION_SYSTEM_PROMPT = (
    "These are hard triage cases a smaller model was unsure about, or that carry "
    "legal/financial weight. Read carefully and give your most reliable "
    "classification.\n\n" + _SYSTEM_PROMPT
)
_LEGAL_FINANCIAL_RE = re.compile(
    r"\b(lawsuit|subpoena|contract|invoice|payment|wire\s+transfer|overdue|past\s+due|"
    r"tax|irs|legal|attorney|settlement|refund|penalt|liabilit|deadline)\w*",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b"
)


def _needs_escalation(res: dict, item: dict, threshold: float) -> tuple[bool, str]:
    """Decide whether a Tier 1 result should be escalated to the frontier model.

    Triggers: low confidence, legal/financial language, or ambiguous/
    self-contradictory extraction (label↔type mismatch, Junk with a due date,
    or conflicting date signals).
    """
    confidence = _get_float(res.get("confidence"), 0.0)
    if confidence < threshold:
        return True, f"low_confidence({confidence:.2f}<{threshold})"

    text = f"{item['subject']}\n{item['body']}"
    if _LEGAL_FINANCIAL_RE.search(text):
        return True, "legal_financial"

    label = _normalize_label(res.get("label"))
    typ = str(res.get("type") or "").strip().lower()
    if (label == "Actionable" and typ == "fyi") or (label == "Important-FYI" and typ == "task"):
        return True, "label_type_mismatch"
    if label == "Junk" and res.get("due_date"):
        return True, "junk_with_due_date"
    if len(set(_DATE_RE.findall(text))) >= 2:
        return True, "conflicting_dates"
    return False, ""


def _upsert_classification(
    conn: sqlite3.Connection,
    message_ref: str,
    res: dict,
    label: str,
    confidence: float,
    source: str,
    escalated: int = 0,
) -> None:
    """Insert or replace a classification row, resetting review state."""
    conn.execute(
        "INSERT INTO classifications "
        "(message_ref, label, type, summary, due_date, priority, confidence, "
        " source, escalated, needs_review) "
        "VALUES (?,?,?,?,?,?,?,?,?,0) "
        "ON CONFLICT(message_ref) DO UPDATE SET "
        "label=excluded.label, type=excluded.type, summary=excluded.summary, "
        "due_date=excluded.due_date, priority=excluded.priority, "
        "confidence=excluded.confidence, source=excluded.source, "
        "escalated=excluded.escalated, needs_review=0",
        (
            message_ref,
            label,
            str(res.get("type") or ""),
            str(res.get("summary") or ""),
            res.get("due_date"),
            str(res.get("priority") or ""),
            confidence,
            source,
            escalated,
        ),
    )


def _flag_needs_review(conn: sqlite3.Connection, message_ref: str, reason: str) -> None:
    """Mark a classified item for manual review (frontier off/unavailable)."""
    conn.execute(
        "UPDATE classifications SET needs_review=1 WHERE message_ref=?", (message_ref,)
    )
    conn.execute(
        "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
        "VALUES (?, 'tier3', ?, NULL)",
        (message_ref, f"needs-review:{reason}"),
    )


def _mark_all_review(config: dict, candidates: list[tuple[dict, str]]) -> int:
    """Flag every escalation candidate for manual review; returns the count."""
    conn = _connect(config)
    try:
        for item, reason in candidates:
            _flag_needs_review(conn, item["message_ref"], reason)
        conn.commit()
    finally:
        conn.close()
    return len(candidates)


# ─── Output routing seams (via host bridge) ──────────────────────────────────
async def _bridge_create_reminder(
    agent_id: str, title: str, due_iso: str | None
) -> tuple[bool, str]:
    """Create a reminder on the host; returns (ok, reminder_id)."""
    try:
        data = await _call_bridge(
            "POST", "/reminders", agent_id,
            json_body={"title": title or "(no subject)", "due": due_iso or ""},
        )
    except ValueError as e:
        logger.warning("smart_organizer: reminder creation failed: %s", e)
        return False, ""
    if not isinstance(data, dict):
        return False, ""
    return bool(data.get("ok", False)), (data.get("id") or "")


async def _bridge_append_note(agent_id: str, line: str) -> bool:
    """Append a line to today's digest note on the host."""
    try:
        data = await _call_bridge("POST", "/notes/append", agent_id, json_body={"line": line})
    except ValueError as e:
        logger.warning("smart_organizer: note append failed: %s", e)
        return False
    return bool(data.get("ok", True)) if isinstance(data, dict) else True


async def _bridge_reminder_status(agent_id: str, reminder_id: str) -> str:
    """Return 'completed' | 'open' | 'missing' | 'unknown' for a reminder id."""
    if not reminder_id:
        return "unknown"
    try:
        data = await _call_bridge(
            "GET", "/reminders/status", agent_id, params={"id": reminder_id}
        )
    except ValueError:
        return "unknown"
    status = (data.get("status") if isinstance(data, dict) else "") or ""
    return status if status in ("completed", "open", "missing") else "unknown"


async def _route_classified(config: dict, agent_id: str, limit: int = 200) -> dict[str, int]:
    """Route already-classified items to Reminders / the daily Note / audit.

    Operates on queue rows in state 'classified' (independent of which run
    produced them), so a routing failure is retried on the next pass. Only
    successfully-routed items advance to state 'routed'.

    Routing map:
      needs_review   → daily Note with a "[needs review]" marker
      Actionable     → Apple Reminder (with due date when extracted)
      Important-FYI  → daily Note (one line, appended)
      Junk           → audit-only, nothing written to a user surface
    """
    counts = {"reminders": 0, "fyi": 0, "review": 0, "junk": 0, "failed": 0}
    conn = _connect(config)
    try:
        rows = conn.execute(
            "SELECT q.id AS qid, q.message_ref, q.sender, q.subject, "
            "       c.label, c.summary, c.due_date, c.needs_review "
            "FROM queue q JOIN classifications c ON c.message_ref = q.message_ref "
            "WHERE q.state = 'classified' ORDER BY q.id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        for r in rows:
            label = r["label"]
            headline = r["summary"] or r["subject"] or "(no subject)"
            reminder_id = ""
            if r["needs_review"]:
                ok = await _bridge_append_note(
                    agent_id, f"[needs review] {label or '?'} — {r['sender']}: {headline}"
                )
                bucket, decision = "review", "route:fyi-review"
            elif label == "Actionable":
                ok, reminder_id = await _bridge_create_reminder(agent_id, headline, r["due_date"])
                bucket, decision = "reminders", "route:reminder"
            elif label == "Junk":
                ok, bucket, decision = True, "junk", "route:junk-discard"
            else:  # Important-FYI (and any unexpected label) → digest
                ok = await _bridge_append_note(agent_id, f"{r['sender']}: {headline}")
                bucket, decision = "fyi", "route:fyi"

            if ok:
                conn.execute("UPDATE queue SET state='routed' WHERE id=?", (r["qid"],))
                if reminder_id:
                    conn.execute(
                        "UPDATE classifications SET reminder_id=? WHERE message_ref=?",
                        (reminder_id, r["message_ref"]),
                    )
                conn.execute(
                    "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                    "VALUES (?, 'route', ?, NULL)",
                    (r["message_ref"], decision),
                )
                counts[bucket] += 1
            else:
                counts["failed"] += 1
        conn.commit()
    finally:
        conn.close()
    return counts


def _format_routing(counts: dict[str, int]) -> str:
    total = counts["reminders"] + counts["fyi"] + counts["review"] + counts["junk"]
    if total == 0 and counts["failed"] == 0:
        return "nothing to route"
    parts = (
        f"{counts['reminders']} reminder(s), {counts['fyi']} FYI note(s), "
        f"{counts['review']} needs-review, {counts['junk']} junk discarded"
    )
    if counts["failed"]:
        parts += f", {counts['failed']} failed (left for retry)"
    return parts


# ─── Feedback loop ───────────────────────────────────────────────────────────
async def _scan_reminder_feedback(config: dict, agent_id: str) -> dict[str, int]:
    """Harvest implicit feedback from Reminders state (FR-23), best-effort.

    For routed Actionable items with a known reminder id that haven't been
    scanned yet:
      completed → confirms Actionable (positive signal + a feedback row)
      missing   → deleted without completing (weak negative on the sender prior)
      open      → unresolved; leave for a later scan
    """
    result = {"completed": 0, "deleted": 0}
    conn = _connect(config)
    try:
        rows = conn.execute(
            "SELECT c.message_ref, c.reminder_id, q.sender, q.subject "
            "FROM classifications c JOIN queue q ON q.message_ref = c.message_ref "
            "WHERE c.label='Actionable' AND c.reminder_id IS NOT NULL "
            "AND c.reminder_scanned=0"
        ).fetchall()
        for r in rows:
            status = await _bridge_reminder_status(agent_id, r["reminder_id"])
            if status in ("unknown", "open"):
                continue  # can't tell yet — re-check next time
            if status == "completed":
                conn.execute(
                    "INSERT INTO feedback (sender, subject, body_snippet, model_label, user_label) "
                    "VALUES (?, ?, '', 'Actionable', 'Actionable')",
                    (r["sender"], r["subject"]),
                )
                _update_sender_prior(conn, r["sender"], _signal_for_label("Actionable"))
                conn.execute(
                    "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                    "VALUES (?, 'feedback', 'implicit:completed', NULL)",
                    (r["message_ref"],),
                )
                result["completed"] += 1
            else:  # missing → deleted without completion
                _update_sender_prior(conn, r["sender"], -0.3)
                conn.execute(
                    "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                    "VALUES (?, 'feedback', 'implicit:deleted', NULL)",
                    (r["message_ref"],),
                )
                result["deleted"] += 1
            conn.execute(
                "UPDATE classifications SET reminder_scanned=1 WHERE message_ref=?",
                (r["message_ref"],),
            )
        conn.commit()
    finally:
        conn.close()
    return result


# ─── Tools ───────────────────────────────────────────────────────────────────
def create_tools(agent_id: str):
    _STUB = (
        "Smart Organizer is scaffolded (PR #1). This tool's tier logic lands "
        "in a later PR; the plugin data store and config are wired up."
    )

    @tool
    async def smart_organizer_ingest(limit: int = 50) -> str:
        """Tier 0 — read newly-arrived Apple Mail, apply the discard rules, and
        enqueue survivors for the next batch cycle.

        Reads message metadata (sender, subject, date) from Mail's Envelope
        Index via the host bridge without invoking any LLM, applies the
        configured allow/block/regex rules, discards junk (logged for audit),
        and queues the rest for Tier 1 classification. Only messages newer than
        the last ingest are considered.

        Args:
            limit: Max number of new messages to pull this pass (default 50).
        """
        config = await _get_config(agent_id)

        conn = _connect(config)
        try:
            after = int(_meta_get(conn, "last_rowid", "0") or 0)
        finally:
            conn.close()

        try:
            messages = await _bridge_get_new_mail(agent_id, after, limit)
        except ValueError as e:
            return f"Could not reach the host bridge to read mail: {e}"
        if not messages:
            return f"No new mail since last ingest (high-water ROWID {after})."

        conn = _connect(config)
        try:
            discarded = 0
            max_rowid = after
            for msg in messages:
                max_rowid = max(max_rowid, int(msg["rowid"]))
                decision, reason = evaluate_rules(msg["sender"], msg["subject"], config)
                conn.execute(
                    "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                    "VALUES (?, 'tier0', ?, NULL)",
                    (msg["message_id"], f"{decision}:{reason}"),
                )
                if decision == "discard":
                    discarded += 1
                    continue
                # Body is fetched lazily at Tier 1; store the subject as the
                # initial snippet so the queue row is human-readable.
                conn.execute(
                    "INSERT INTO queue "
                    "(message_ref, sender, subject, received_at, body_snippet, urgency, state) "
                    "VALUES (?, ?, ?, ?, ?, NULL, 'pending') "
                    "ON CONFLICT(message_ref) DO NOTHING",
                    (
                        msg["message_id"],
                        msg["sender"],
                        msg["subject"],
                        msg["received_at"],
                        msg["subject"],
                    ),
                )
            _meta_set(conn, "last_rowid", str(max_rowid))
            conn.commit()
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM queue WHERE state = 'pending'"
            ).fetchone()["n"]
        finally:
            conn.close()

        kept = len(messages) - discarded
        return (
            f"Ingested {len(messages)} new message(s): kept {kept}, discarded {discarded} "
            f"by Tier 0 rules. Queue now holds {pending} pending item(s) "
            f"(high-water ROWID {max_rowid})."
        )

    @tool
    async def smart_organizer_triage_urgent(message_ref: str) -> str:
        """Run the free urgency pre-check on a single just-arrived message and,
        if urgent, classify it immediately (bypassing the batch queue).

        Args:
            message_ref: Stable identifier of the message (from the Mail rule handler).
        """
        return _STUB

    @tool
    async def smart_organizer_run_batch(limit: int = 50) -> str:
        """Tier 1 (+ Tier 3) — classify the queued batch in a single local-model
        pass routed through the configured Batch LLM Purpose, then escalate the
        hard cases to the Frontier LLM Purpose.

        Fetches message bodies lazily (Apple Mail, macOS), injects per-sender
        importance priors and recent user corrections, and asks the model for a
        strict JSON array. Items with low confidence, legal/financial language,
        or contradictory extractions are escalated to the frontier model (only a
        stripped snippet is sent). If escalation is disabled or has no purpose,
        those items are flagged for manual review instead. On any model/routing
        failure, affected items stay queued for the next cycle.

        Args:
            limit: Max queued items to classify this pass (default 50).
        """
        config = await _get_config(agent_id)
        batch_purpose_id = (config.get("batch_purpose_id") or "").strip()
        if not batch_purpose_id:
            return "No Batch LLM Purpose configured (batch_purpose_id); cannot classify."
        threshold = _get_float(config.get("confidence_threshold"), DEFAULT_CONFIDENCE_THRESHOLD)
        frontier_enabled = _get_bool(config.get("frontier_enabled"), True)
        frontier_purpose_id = (config.get("frontier_purpose_id") or "").strip()

        conn = _connect(config)
        try:
            _purge_old_logs(
                conn, _get_float(config.get("log_retention_days"), DEFAULT_LOG_RETENTION_DAYS)
            )
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, message_ref, sender, subject, body_snippet "
                    "FROM queue WHERE state = 'pending' ORDER BY id ASC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
            ]
            priors = _load_sender_priors(conn, [r["sender"] for r in rows])
            fb_candidates = _fetch_feedback_candidates(conn)
            conn.commit()
        finally:
            conn.close()  # don't hold the store open across bridge/model calls

        # Nothing new to classify — still flush any previously-classified items
        # whose routing may have failed on an earlier pass.
        if not rows:
            routed = await _route_classified(config, agent_id)
            return (
                "No new items to classify. "
                f"Routing pass: {_format_routing(routed)}."
            )

        # Lazily fetch bodies from the host bridge (falls back to snippet/subject).
        items = []
        for r in rows:
            body = await _bridge_get_body(agent_id, r["message_ref"]) or (
                r["body_snippet"] or r["subject"] or ""
            )
            items.append(
                {
                    "id": r["id"],
                    "message_ref": r["message_ref"],
                    "sender": r["sender"] or "",
                    "subject": r["subject"] or "",
                    "body": body,
                }
            )

        # Semantic few-shot: corrections most similar to this batch (FR-15/FR-26).
        query_text = " ".join(f"{it['sender']} {it['subject']}" for it in items)
        fewshot = await _rank_fewshot(fb_candidates, query_text)

        # ── Tier 1: local batch classification ──────────────────────────────
        try:
            provider, model, results = await _run_classifier(
                batch_purpose_id, _SYSTEM_PROMPT, items, priors, fewshot
            )
        except Exception as e:  # noqa: BLE001
            return (
                f"Tier 1 batch classification failed ({e}). Items remain queued."
            )
        if not results:
            return (
                f"Model ({provider}/{model}) returned no parseable classifications; "
                "items remain queued."
            )

        by_id = {it["id"]: it for it in items}
        counts = {label: 0 for label in LABELS}
        classified = 0
        candidates: list[tuple[dict, str]] = []  # (item, escalation_reason)
        conn = _connect(config)
        try:
            for res in results:
                item = by_id.get(res.get("id"))
                if item is None:
                    continue
                label = _normalize_label(res.get("label"))
                confidence = _get_float(res.get("confidence"), 0.0)
                _upsert_classification(
                    conn, item["message_ref"], res, label, confidence, f"{provider}/{model}"
                )
                conn.execute("UPDATE queue SET state='classified' WHERE id=?", (item["id"],))
                conn.execute(
                    "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                    "VALUES (?, 'tier1', ?, ?)",
                    (item["message_ref"], label, confidence),
                )
                counts[label] += 1
                classified += 1
                should, reason = _needs_escalation(res, item, threshold)
                if should:
                    candidates.append((item, reason))
            conn.commit()
        finally:
            conn.close()

        # ── Tier 3: frontier escalation (only stripped snippets leave device) ─
        escalated = review = 0
        tier3_note = ""
        if candidates:
            if frontier_enabled and frontier_purpose_id:
                esc_items = [
                    {**item, "body": (item["body"] or "")[:_ESCALATION_SNIPPET_CHARS]}
                    for item, _ in candidates
                ]
                cand_by_id = {it["id"]: it for it in esc_items}
                try:
                    fprovider, fmodel, fresults = await _run_classifier(
                        frontier_purpose_id, _ESCALATION_SYSTEM_PROMPT, esc_items, priors, fewshot
                    )
                except Exception as e:  # noqa: BLE001
                    fresults = []
                    tier3_note = f" Frontier escalation failed ({e}); flagged for manual review."
                if fresults:
                    conn = _connect(config)
                    try:
                        seen_ids = set()
                        for res in fresults:
                            item = cand_by_id.get(res.get("id"))
                            if item is None:
                                continue
                            seen_ids.add(item["id"])
                            label = _normalize_label(res.get("label"))
                            confidence = _get_float(res.get("confidence"), 0.0)
                            _upsert_classification(
                                conn, item["message_ref"], res, label, confidence,
                                f"{fprovider}/{fmodel}", escalated=1,
                            )
                            conn.execute(
                                "INSERT INTO decision_log (message_ref, tier, decision, confidence) "
                                "VALUES (?, 'tier3', ?, ?)",
                                (item["message_ref"], label, confidence),
                            )
                            escalated += 1
                        # Any candidate the frontier didn't return → manual review.
                        for item, reason in candidates:
                            if item["id"] not in seen_ids:
                                _flag_needs_review(conn, item["message_ref"], reason)
                                review += 1
                        conn.commit()
                    finally:
                        conn.close()
                    tier3_note = f" Escalated {escalated} to {fprovider}/{fmodel}."
                else:
                    review += _mark_all_review(config, candidates)
            else:
                why = "disabled" if not frontier_enabled else "no frontier purpose set"
                review += _mark_all_review(config, candidates)
                tier3_note = f" Escalation {why}; {review} flagged for manual review."

        # ── Output routing: Reminders / daily Note / audit ──────────────────
        routed = await _route_classified(config, agent_id)

        breakdown = ", ".join(f"{k}: {v}" for k, v in counts.items())
        return (
            f"Classified {classified}/{len(items)} queued item(s) via {provider}/{model}. "
            f"{breakdown}. {len(candidates)} hard case(s) gated for Tier 3.{tier3_note} "
            f"Routed: {_format_routing(routed)}."
        )

    @tool
    async def smart_organizer_record_feedback(
        sender: str,
        user_label: str,
        subject: str = "",
        body_snippet: str = "",
        model_label: str = "",
    ) -> str:
        """Record a classification correction so importance learning improves.

        Logs the correction, folds it into the sender's rolling importance prior,
        and stores an embedding of the example for future few-shot retrieval.

        Args:
            sender: The message sender's address.
            user_label: The correct label — one of Actionable, Important-FYI, Junk.
            subject: Message subject (optional context).
            body_snippet: Short stripped snippet (optional context).
            model_label: What the model originally predicted (optional).
        """
        config = await _get_config(agent_id)
        label = _normalize_label(user_label)

        conn = _connect(config)
        try:
            cur = conn.execute(
                "INSERT INTO feedback (sender, subject, body_snippet, model_label, user_label) "
                "VALUES (?, ?, ?, ?, ?)",
                (sender, subject, body_snippet, model_label, label),
            )
            feedback_id = cur.lastrowid
            new_score, n = _update_sender_prior(conn, sender, _signal_for_label(label))
            conn.commit()
        finally:
            conn.close()

        # Embed the correction for semantic few-shot (namespaced feedback store).
        vec = await _safe_embed(f"{sender} {subject} {body_snippet}".strip())
        embedded = False
        if vec:
            conn = _connect(config)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO feedback_embeddings (feedback_id, embedding) "
                    "VALUES (?, ?)",
                    (feedback_id, json.dumps(vec)),
                )
                conn.commit()
                embedded = True
            finally:
                conn.close()

        return (
            f"Recorded correction: {sender or '(unknown)'} → {label}. "
            f"Sender importance now {new_score:+.2f} over {n} sample(s)."
            + ("" if embedded else " (embedding unavailable; using recency for few-shot.)")
        )

    @tool
    async def smart_organizer_feedback_summary() -> str:
        """Return a pull-based summary of corrections since it was last viewed:
        implicit Reminder-based signals harvested, reclassifications tallied,
        sender priors updated, and few-shot coverage.
        """
        config = await _get_config(agent_id)
        implicit = await _scan_reminder_feedback(config, agent_id)  # FR-23, best-effort

        conn = _connect(config)
        try:
            last = int(_meta_get(conn, "feedback_summary_last_id", "0") or 0)
            rows = conn.execute(
                "SELECT id, sender, model_label, user_label FROM feedback "
                "WHERE id > ? ORDER BY id",
                (last,),
            ).fetchall()
            new_last = max((r["id"] for r in rows), default=last)
            reclassified = sum(
                1 for r in rows if r["model_label"] and r["model_label"] != r["user_label"]
            )
            senders = {r["sender"] for r in rows if r["sender"]}
            by_label = {label: 0 for label in LABELS}
            for r in rows:
                by_label[_normalize_label(r["user_label"])] += 1
            total_priors = conn.execute(
                "SELECT COUNT(*) AS n FROM sender_priors"
            ).fetchone()["n"]
            fewshot_n = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback_embeddings"
            ).fetchone()["n"]
            top_priors = conn.execute(
                "SELECT sender, score, sample_count FROM sender_priors "
                "ORDER BY sample_count DESC, ABS(score) DESC LIMIT 5"
            ).fetchall()
            _meta_set(conn, "feedback_summary_last_id", str(new_last))
            conn.commit()
        finally:
            conn.close()

        lines = []
        implicit_total = implicit["completed"] + implicit["deleted"]
        if implicit_total:
            lines.append(
                f"Implicit signals harvested: {implicit['completed']} reminder(s) completed "
                f"(confirmed Actionable), {implicit['deleted']} deleted (possible misclassification)."
            )
        if rows:
            label_str = ", ".join(f"{k}: {v}" for k, v in by_label.items())
            lines.append(
                f"{len(rows)} new correction(s) across {len(senders)} sender(s) — {label_str}. "
                f"{reclassified} changed the model's label."
            )
        else:
            lines.append("No new corrections since last viewed.")
        if top_priors:
            pr = "; ".join(
                f"{p['sender']} {p['score']:+.2f} (n={p['sample_count']})" for p in top_priors
            )
            lines.append(f"Sender priors ({total_priors} total) — most-sampled: {pr}.")
        lines.append(f"Few-shot corpus: {fewshot_n} embedded example(s).")
        return "\n".join(lines)

    @tool
    async def smart_organizer_test_rules(sample: str = "") -> str:
        """Dry-run the configured Tier 0 rule set (allow/block/regex) against a
        sample line to preview whether it would be kept or discarded.

        Args:
            sample: A "sender | subject" line to test, e.g.
                "no-reply@promo.example.com | 50% off — unsubscribe".
                If omitted, returns a summary of the loaded rules.
        """
        config = await _get_config(agent_id)
        allow = _parse_lines(config.get("sender_allowlist"))
        block = _parse_lines(config.get("sender_blocklist"))
        raw_regexes = _parse_lines(config.get("regex_rules"))
        compiled = _compile_regex_rules(raw_regexes)
        invalid = [p for p in raw_regexes if p not in {pat for pat, _ in compiled}]

        summary = (
            f"Loaded Tier 0 rules — allowlist: {len(allow)}, blocklist: {len(block)}, "
            f"regex: {len(compiled)} valid"
            + (f" ({len(invalid)} invalid: {invalid})" if invalid else "")
            + "."
        )
        if not sample.strip():
            return summary

        sender, _, subject = sample.partition("|")
        sender, subject = sender.strip(), subject.strip()
        decision, reason = evaluate_rules(sender, subject, config)
        verb = "KEEP → queue for classification" if decision == "keep" else "DISCARD"
        return (
            f"{summary}\n\nSample: sender={sender!r} subject={subject!r}\n"
            f"Result: {verb}  (matched rule: {reason})"
        )

    return [
        smart_organizer_ingest,
        smart_organizer_triage_urgent,
        smart_organizer_run_batch,
        smart_organizer_record_feedback,
        smart_organizer_feedback_summary,
        smart_organizer_test_rules,
    ]


# ─── Connection test ─────────────────────────────────────────────────────────
async def test_connection(creds: dict, config: dict) -> dict:
    """Validate config: referenced LLM Purposes resolve, the SQLite store is
    writable, and the host bridge daemon is reachable and authenticated.
    """
    details: list[str] = []
    ok = True

    # 1. Purpose references
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.llm_purpose import LLMPurpose

    batch_id = (config.get("batch_purpose_id") or "").strip()
    frontier_id = (config.get("frontier_purpose_id") or "").strip()

    if not batch_id:
        ok = False
        details.append("✗ Batch LLM Purpose (Tier 1) is not set — required.")
    else:
        async with async_session_factory() as db:
            purpose = await db.get(LLMPurpose, batch_id)
        if not purpose:
            ok = False
            details.append(f"✗ Batch LLM Purpose '{batch_id}' not found.")
        elif not purpose.get_slots():
            ok = False
            details.append(f"✗ Batch LLM Purpose '{purpose.name}' has no model slots configured.")
        else:
            details.append(f"✓ Batch purpose '{purpose.name}' ({len(purpose.get_slots())} slot(s)).")

    if frontier_id:
        async with async_session_factory() as db:
            fp = await db.get(LLMPurpose, frontier_id)
        if not fp:
            details.append(f"! Frontier LLM Purpose '{frontier_id}' not found — escalation will be skipped.")
        else:
            details.append(f"✓ Frontier purpose '{fp.name}'.")
    else:
        details.append("! No frontier purpose set — Tier 3 escalation disabled.")

    # 2. SQLite store
    try:
        conn = _connect(config)
        conn.execute("SELECT 1")
        conn.close()
        details.append(f"✓ Data store writable at {_resolve_sqlite_path(config)}.")
    except Exception as e:  # noqa: BLE001
        ok = False
        details.append(f"✗ Data store error: {e}")

    # 3. Host bridge daemon
    import httpx

    bridge_url = (config.get("bridge_url") or "").rstrip("/")
    token = creds.get("bridge_token") or ""
    if not bridge_url:
        ok = False
        details.append("✗ Host Bridge URL is not set (e.g. http://host.docker.internal:7477).")
    else:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{bridge_url}/health",
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                )
            if resp.status_code == 401:
                ok = False
                details.append("✗ Host bridge rejected the token (401).")
            elif not resp.is_success:
                ok = False
                details.append(f"✗ Host bridge returned {resp.status_code}.")
            else:
                details.append(f"✓ Host bridge reachable at {bridge_url}.")
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            ok = False
            details.append(
                f"✗ Host bridge unreachable at {bridge_url} ({e}). "
                "Is scripts/smart_organizer_bridge.py running on the host?"
            )

    return {"ok": ok, "detail": "\n".join(details)}
