"""Read-only API for the Smart Organizer dashboard.

Serves the plugin's local SQLite store (queue, classifications, sender priors,
feedback, decision log) for the /smart-organizer dashboard, plus a CSV export
of the queue (FR-16) and a cross-plugin sender-importance lookup (PR-4).

Runs on the backend where the store lives (bind-mounted .local path).
"""

from __future__ import annotations

import csv
import io
import sqlite3

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import nullslast, select

from app.db.session import async_session_factory
from app.models.integration import Integration
from app.tools.extensions.smart_organizer import EXTENSION_ID, _connect

router = APIRouter(prefix="/smart-organizer", tags=["smart-organizer"])


async def _resolve_config() -> dict:
    """Return the Smart Organizer integration's config (system-wide preferred)."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Integration)
            .where(Integration.type == EXTENSION_ID, Integration.is_active == True)  # noqa: E712
            .order_by(nullslast(Integration.agent_id.desc()))
        )
        rows = result.scalars().all()
    row = next((r for r in rows if r.agent_id is None), None) or (rows[0] if rows else None)
    if not row:
        raise HTTPException(404, "No active Smart Organizer integration is configured.")
    return dict(row.extra_config or {})


async def _store() -> sqlite3.Connection:
    return _connect(await _resolve_config())


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


@router.get("/overview")
async def overview() -> dict:
    """Top-line counts for the dashboard header."""
    conn = await _store()
    try:
        return {
            "queue": {
                r["state"]: r["n"]
                for r in _rows(conn, "SELECT state, COUNT(*) AS n FROM queue GROUP BY state")
            },
            "labels": {
                r["label"]: r["n"]
                for r in _rows(
                    conn,
                    "SELECT label, COUNT(*) AS n FROM classifications "
                    "WHERE label IS NOT NULL GROUP BY label",
                )
            },
            "needs_review": _scalar(
                conn, "SELECT COUNT(*) FROM classifications WHERE needs_review=1"
            ),
            "sender_priors": _scalar(conn, "SELECT COUNT(*) FROM sender_priors"),
            "corrections": _scalar(conn, "SELECT COUNT(*) FROM feedback"),
            "fewshot_examples": _scalar(conn, "SELECT COUNT(*) FROM feedback_embeddings"),
        }
    finally:
        conn.close()


@router.get("/queue")
async def queue(
    state: str | None = Query(None, description="Filter by state (pending/classified/routed)"),
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict]:
    """Queue rows joined with their classification (if any)."""
    conn = await _store()
    try:
        sql = (
            "SELECT q.id, q.message_ref, q.sender, q.subject, q.received_at, q.urgency, "
            "       q.state, c.label, c.summary, c.due_date, c.confidence, c.escalated, "
            "       c.needs_review "
            "FROM queue q LEFT JOIN classifications c ON c.message_ref = q.message_ref "
        )
        params: tuple = ()
        if state:
            sql += "WHERE q.state = ? "
            params = (state,)
        sql += "ORDER BY q.id DESC LIMIT ?"
        return _rows(conn, sql, (*params, limit))
    finally:
        conn.close()


@router.get("/digest")
async def digest(on: str | None = Query(None, description="Date YYYY-MM-DD; default today")) -> dict:
    """Items routed on a given day, split into tasks (Actionable) and FYIs."""
    conn = await _store()
    try:
        day = on or "now"
        date_expr = "date(?)" if on else "date('now')"
        rows = _rows(
            conn,
            "SELECT c.label, c.summary, c.due_date, q.sender, q.subject "
            "FROM classifications c JOIN queue q ON q.message_ref = c.message_ref "
            f"WHERE q.state='routed' AND date(c.created_at) = {date_expr} "
            "ORDER BY c.created_at DESC",
            (day,) if on else (),
        )
        return {
            "date": on or "today",
            "actionable": [r for r in rows if r["label"] == "Actionable"],
            "fyi": [r for r in rows if r["label"] == "Important-FYI"],
        }
    finally:
        conn.close()


@router.get("/needs-review")
async def needs_review(limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    """Items flagged for manual review (frontier off/unavailable)."""
    conn = await _store()
    try:
        return _rows(
            conn,
            "SELECT c.message_ref, c.label, c.summary, c.confidence, q.sender, q.subject "
            "FROM classifications c JOIN queue q ON q.message_ref = c.message_ref "
            "WHERE c.needs_review = 1 ORDER BY c.created_at DESC LIMIT ?",
            (limit,),
        )
    finally:
        conn.close()


@router.get("/priors")
async def priors(limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    """Per-sender importance priors, most-sampled first."""
    conn = await _store()
    try:
        return _rows(
            conn,
            "SELECT sender, score, sample_count, updated_at FROM sender_priors "
            "ORDER BY sample_count DESC, ABS(score) DESC LIMIT ?",
            (limit,),
        )
    finally:
        conn.close()


@router.get("/feedback")
async def feedback(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    """Recent corrections."""
    conn = await _store()
    try:
        return _rows(
            conn,
            "SELECT id, sender, subject, model_label, user_label, timestamp "
            "FROM feedback ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    finally:
        conn.close()


@router.get("/audit")
async def audit(
    tier: str | None = Query(None, description="Filter by tier (tier0/tier1/tier3/route/urgency/feedback)"),
    limit: int = Query(200, ge=1, le=2000),
) -> list[dict]:
    """The decision trail across every tier."""
    conn = await _store()
    try:
        sql = "SELECT id, message_ref, tier, decision, confidence, timestamp FROM decision_log "
        params: tuple = ()
        if tier:
            sql += "WHERE tier = ? "
            params = (tier,)
        sql += "ORDER BY id DESC LIMIT ?"
        return _rows(conn, sql, (*params, limit))
    finally:
        conn.close()


@router.get("/queue.csv")
async def queue_csv() -> StreamingResponse:
    """Export the full queue (with classifications) as CSV (FR-16)."""
    conn = await _store()
    try:
        rows = _rows(
            conn,
            "SELECT q.id, q.message_ref, q.sender, q.subject, q.received_at, q.urgency, "
            "       q.state, c.label, c.summary, c.due_date, c.confidence, c.escalated, "
            "       c.needs_review "
            "FROM queue q LEFT JOIN classifications c ON c.message_ref = q.message_ref "
            "ORDER BY q.id ASC",
        )
    finally:
        conn.close()

    fieldnames = [
        "id", "message_ref", "sender", "subject", "received_at", "urgency", "state",
        "label", "summary", "due_date", "confidence", "escalated", "needs_review",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=smart_organizer_queue.csv"},
    )


@router.get("/sender-importance")
async def sender_importance(sender: str = Query(..., description="Exact sender address")) -> dict:
    """Cross-plugin read API (PR-4): a sender's learned importance prior."""
    conn = await _store()
    try:
        row = conn.execute(
            "SELECT sender, score, sample_count, updated_at FROM sender_priors WHERE sender = ?",
            (sender,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"sender": sender, "score": 0.0, "sample_count": 0, "known": False}
    return {**dict(row), "known": True}
