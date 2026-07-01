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

import os
import sqlite3
import sys
from pathlib import Path

from langchain_core.tools import tool

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
    conn.commit()
    return conn


def _envelope_index_path() -> Path | None:
    """Best-effort locate the Mail.app Envelope Index (macOS only)."""
    if sys.platform != "darwin":
        return None
    mail_root = Path(os.path.expanduser("~/Library/Mail"))
    if not mail_root.exists():
        return None
    matches = sorted(mail_root.glob("V*/MailData/Envelope Index"))
    return matches[-1] if matches else None


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

        Args:
            limit: Max number of new messages to pull this pass (default 50).
        """
        config = await _get_config(agent_id)
        conn = _connect(config)
        try:
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM queue WHERE state = 'pending'"
            ).fetchone()["n"]
        finally:
            conn.close()
        return f"{_STUB}\nQueue currently holds {pending} pending item(s)."

    @tool
    async def smart_organizer_triage_urgent(message_ref: str) -> str:
        """Run the free urgency pre-check on a single just-arrived message and,
        if urgent, classify it immediately (bypassing the batch queue).

        Args:
            message_ref: Stable identifier of the message (from the Mail rule handler).
        """
        return _STUB

    @tool
    async def smart_organizer_run_batch() -> str:
        """Tier 1 (+ Tier 3) — classify and extract the entire queued batch in a
        single local-model pass, escalate low-confidence items to the frontier
        model when enabled, and route results to Reminders / the daily Note.
        """
        return _STUB

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
            sample: A "sender | subject" line to test against the rules.
        """
        return _STUB

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
