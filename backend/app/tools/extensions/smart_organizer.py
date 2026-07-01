"""Smart Email/Notification Organizer extension for Sutra OS.

Ingests Apple Mail, classifies it locally, extracts actionable tasks to Apple
Reminders, logs important-but-non-actionable items to a daily Apple Note, and
learns per-user importance over time — while keeping ~90%+ of processing on
local models and reserving frontier calls for low-confidence/high-stakes items.

This file is PR #1 (the scaffold): manifest, config plumbing, the plugin-local
SQLite store bootstrap, and stub tools with their final signatures. The tier
logic (ingest, classify, escalate, route, feedback) lands in later PRs.

LLM configuration
-----------------
Unlike a plugin-scoped model dropdown, every model call routes through Sutra's
existing purpose-based LLM settings and keys. Configure two LLM Purposes and
reference them here:
  - batch_purpose_id    → Tier 1 local classify/extract (point slots at Ollama)
  - frontier_purpose_id → Tier 3 escalation (system-wide default frontier)
The extension therefore holds no provider API keys of its own; rate limits,
fallback chains, and circuit breaking come for free via the smart router.

Apple Mail real-time trigger (set up once, macOS)
-------------------------------------------------
Mail ▸ Settings ▸ Rules ▸ add a rule matching "Every Message" whose action runs
an AppleScript that calls the arrival handler (wired in a later PR). Non-urgent
mail is drained on the batch cadence; urgent mail is triaged immediately.

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
import subprocess
import sys
from datetime import datetime, timezone
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
    # No secrets: local Ollama + AppleScript need none; frontier keys come from
    # the referenced LLM Purpose, not from this extension.
    "credential_fields": [],
    "config_fields": [
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
            "label": "Plugin data store path",
            "secret": False,
            "placeholder": "~/.sutra/smart_organizer.db",
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
DEFAULT_SQLITE_PATH = "~/.sutra/smart_organizer.db"
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
    message_ref   TEXT PRIMARY KEY,
    label         TEXT,
    type          TEXT,
    summary       TEXT,
    due_date      TEXT,
    priority      TEXT,
    confidence    REAL,
    source        TEXT,
    escalated     INTEGER NOT NULL DEFAULT 0,
    needs_review  INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
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
    if "needs_review" not in cols:
        conn.execute(
            "ALTER TABLE classifications ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0"
        )


def _envelope_index_path() -> Path | None:
    """Best-effort locate the Mail.app Envelope Index (macOS only)."""
    if sys.platform != "darwin":
        return None
    mail_root = Path(os.path.expanduser("~/Library/Mail"))
    if not mail_root.exists():
        return None
    matches = sorted(mail_root.glob("V*/MailData/Envelope Index"))
    return matches[-1] if matches else None


# ─── Tier 0: rule engine (pure, unit-testable) ───────────────────────────────
# Apple stores dates as CFAbsoluteTime (seconds since 2001-01-01 UTC).
_APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01


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


# ─── Tier 0: Apple Mail Envelope Index reader (read-only, macOS) ──────────────
def _apple_time_to_iso(value) -> str | None:
    """Convert an Envelope Index timestamp to an ISO-8601 UTC string, tolerantly.

    Values are typically CFAbsoluteTime (seconds since 2001). Some rows/versions
    already store Unix epoch; distinguish by magnitude.
    """
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    # A post-2001 CFAbsoluteTime is smaller than the equivalent Unix epoch by
    # the offset; anything already larger than a 2001 Unix epoch is Unix.
    if ts < _APPLE_EPOCH_OFFSET:
        ts += _APPLE_EPOCH_OFFSET
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _open_envelope_ro(path: Path) -> sqlite3.Connection:
    """Open the Envelope Index read-only, tolerating Mail's live locks."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        # Fall back to immutable if the live DB is locked (may miss WAL tail).
        conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _read_envelope_messages(after_rowid: int, limit: int) -> list[dict]:
    """Return new messages (ROWID > after_rowid) from the Mail Envelope Index.

    Adapts to schema variation by inspecting available columns. Returns [] if
    Mail is unavailable or the schema can't be read (caller degrades gracefully).
    """
    env_path = _envelope_index_path()
    if env_path is None:
        return []

    conn = _open_envelope_ro(env_path)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if not {"sender", "subject", "date_received"} <= cols:
            logger.warning("smart_organizer: unexpected Envelope Index schema: %s", sorted(cols))
            return []
        msg_id_expr = "m.message_id" if "message_id" in cols else "NULL"
        read_expr = "m.read" if "read" in cols else "NULL"
        query = f"""
            SELECT m.ROWID           AS rowid,
                   {msg_id_expr}     AS message_id,
                   a.address         AS sender,
                   s.subject         AS subject,
                   m.date_received   AS date_received,
                   {read_expr}       AS read_flag
            FROM messages m
            LEFT JOIN addresses a ON a.ROWID = m.sender
            LEFT JOIN subjects  s ON s.ROWID = m.subject
            WHERE m.ROWID > ?
            ORDER BY m.ROWID ASC
            LIMIT ?
        """
        rows = conn.execute(query, (after_rowid, max(1, limit))).fetchall()
    except sqlite3.Error as e:
        logger.warning("smart_organizer: Envelope Index read failed: %s", e)
        return []
    finally:
        conn.close()

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "rowid": r["rowid"],
                "message_id": r["message_id"] or f"rowid:{r['rowid']}",
                "sender": r["sender"] or "",
                "subject": r["subject"] or "",
                "received_at": _apple_time_to_iso(r["date_received"]),
                "read": bool(r["read_flag"]) if r["read_flag"] is not None else None,
            }
        )
    return out


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


# ─── Tier 1: classification & extraction ─────────────────────────────────────
LABELS = ("Actionable", "Important-FYI", "Junk")
_BODY_SNIPPET_CHARS = 1500


def _fetch_body_applescript(message_id: str, timeout: float = 6.0) -> str:
    """Fetch a message body via Mail.app scripting (macOS). Best-effort → "".

    Matches on the RFC message id stored in the Envelope Index. Returns a
    stripped, truncated snippet; empty string on any failure so callers can
    fall back to the subject.
    """
    if sys.platform != "darwin" or message_id.startswith("rowid:"):
        return ""
    mid = message_id.strip().lstrip("<").rstrip(">")
    script = (
        'tell application "Mail"\n'
        f'  set matches to (every message of inbox whose message id is "{mid}")\n'
        "  if matches is {} then return \"\"\n"
        "  return content of item 1 of matches\n"
        "end tell"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug("smart_organizer: body fetch failed for %s: %s", message_id, e)
        return ""
    body = (proc.stdout or "").strip()
    return body[:_BODY_SNIPPET_CHARS]


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


def _load_fewshot(conn: sqlite3.Connection, limit: int = 3) -> list[dict]:
    """Return the most recent human corrections as few-shot examples."""
    rows = conn.execute(
        "SELECT sender, subject, body_snippet, user_label "
        "FROM feedback ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


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

        Reads message metadata (sender, subject, date) from Mail's local
        Envelope Index without invoking any LLM, applies the configured
        allow/block/regex rules, discards junk (logged for audit), and queues
        the rest for Tier 1 classification. Only messages newer than the last
        ingest are considered.

        Args:
            limit: Max number of new messages to pull this pass (default 50).
        """
        config = await _get_config(agent_id)

        if sys.platform != "darwin":
            return "Apple Mail ingestion is only available on macOS; nothing ingested."
        if _envelope_index_path() is None:
            return "Mail Envelope Index not found under ~/Library/Mail; nothing ingested."

        conn = _connect(config)
        try:
            after = int(_meta_get(conn, "last_rowid", "0") or 0)
            messages = _read_envelope_messages(after, limit)
            if not messages:
                return f"No new mail since last ingest (high-water ROWID {after})."

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
            rows = conn.execute(
                "SELECT id, message_ref, sender, subject, body_snippet "
                "FROM queue WHERE state = 'pending' ORDER BY id ASC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
            if not rows:
                return "Queue is empty — nothing to classify."
            items = []
            for r in rows:
                body = _fetch_body_applescript(r["message_ref"]) or (
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
            priors = _load_sender_priors(conn, [it["sender"] for it in items])
            fewshot = _load_fewshot(conn)
        finally:
            conn.close()  # don't hold the store open across the model call

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

        breakdown = ", ".join(f"{k}: {v}" for k, v in counts.items())
        return (
            f"Classified {classified}/{len(items)} queued item(s) via {provider}/{model}. "
            f"{breakdown}. {len(candidates)} hard case(s) gated for Tier 3.{tier3_note}"
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

        Args:
            sender: The message sender's address.
            user_label: The correct label — one of Actionable, Important-FYI, Junk.
            subject: Message subject (optional context).
            body_snippet: Short stripped snippet (optional context).
            model_label: What the model originally predicted (optional).
        """
        return _STUB

    @tool
    async def smart_organizer_feedback_summary() -> str:
        """Return a pull-based summary of corrections since it was last viewed:
        reclassifications tallied, sender priors updated, and new patterns.
        """
        config = await _get_config(agent_id)
        conn = _connect(config)
        try:
            fb = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
            priors = conn.execute("SELECT COUNT(*) AS n FROM sender_priors").fetchone()["n"]
        finally:
            conn.close()
        return (
            f"{_STUB}\nFeedback log: {fb} correction(s) across {priors} sender prior(s)."
        )

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
    """Validate the scaffold: referenced LLM Purposes resolve, the SQLite store
    is writable, and (on macOS) the Mail Envelope Index is reachable.
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

    # 3. Apple Mail (informational — not required for the extension to load)
    if sys.platform != "darwin":
        details.append("! Not running on macOS — Apple Mail ingestion unavailable here.")
    else:
        env_path = _envelope_index_path()
        if env_path:
            details.append(f"✓ Mail Envelope Index found: {env_path}.")
        else:
            details.append("! Mail Envelope Index not found under ~/Library/Mail.")

    return {"ok": ok, "detail": "\n".join(details)}
