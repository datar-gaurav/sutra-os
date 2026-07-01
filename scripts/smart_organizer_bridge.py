#!/usr/bin/env python3
"""Smart Organizer bridge daemon — host-side HTTP server for the smart_organizer extension.

Runs on the HOST machine (macOS, not inside Docker). Listens on 127.0.0.1:PORT.
The backend container reaches it via http://host.docker.internal:PORT.

It performs the macOS-only I/O the container cannot: reading Mail's Envelope
Index, fetching message bodies, and creating Reminders / appending to a daily
Note. All intelligence + state live in the container; this daemon is a thin
macOS proxy.

Usage:
    python3 scripts/smart_organizer_bridge.py

Config is read from ../backend/.env (relative to this script's directory):
    SMART_ORGANIZER_BRIDGE_TOKEN    — shared bearer token (any secret string)
    SMART_ORGANIZER_BRIDGE_PORT     — port to listen on (default 7477)
    SMART_ORGANIZER_ARRIVAL_WEBHOOK — optional URL the Mail rule's /arrival
                                      notifications are forwarded to
    SMART_ORGANIZER_MAIL_ROOT       — optional override for ~/Library/Mail

Endpoints (all require Authorization: Bearer <token> when a token is set):
    GET  /health
    GET  /mail/new?after=<rowid>&limit=<n>
    GET  /mail/body?message_id=<id>
    POST /reminders            {title, due}          -> {ok, id}
    GET  /reminders/status?id=<id>                   -> {status}
    POST /notes/append         {line}                -> {ok}
    POST /arrival              {message_id?}          -> {ok}

No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import datetime
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "1.0.0"


# ── .env loader ───────────────────────────────────────────────────────────────
def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file. Handles comments, blank lines, and single/double quotes."""
    env: dict[str, str] = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key, val = key.strip(), val.strip()
                if val and val[0] in ('"', "'"):
                    quote = val[0]
                    end = val.find(quote, 1)
                    val = val[1:end] if end != -1 else val[1:]
                else:
                    val = val.split(" #")[0].strip()
                env[key] = val
    except FileNotFoundError:
        pass
    return env


# ── Configuration ─────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH = _SCRIPT_DIR.parent / "backend" / ".env"
_env = _load_env_file(_ENV_PATH)

BRIDGE_TOKEN: str = _env.get("SMART_ORGANIZER_BRIDGE_TOKEN") or os.environ.get(
    "SMART_ORGANIZER_BRIDGE_TOKEN", ""
)
BRIDGE_PORT: int = int(
    _env.get("SMART_ORGANIZER_BRIDGE_PORT") or os.environ.get("SMART_ORGANIZER_BRIDGE_PORT", "7477")
)
ARRIVAL_WEBHOOK: str = _env.get("SMART_ORGANIZER_ARRIVAL_WEBHOOK") or os.environ.get(
    "SMART_ORGANIZER_ARRIVAL_WEBHOOK", ""
)
_MAIL_ROOT_OVERRIDE: str = _env.get("SMART_ORGANIZER_MAIL_ROOT") or os.environ.get(
    "SMART_ORGANIZER_MAIL_ROOT", ""
)

_BODY_SNIPPET_CHARS = 1500
# Apple stores Envelope Index dates as CFAbsoluteTime (seconds since 2001-01-01).
_APPLE_EPOCH_OFFSET = 978307200


# ── Mail Envelope Index (read-only) ───────────────────────────────────────────
def _mail_root() -> Path:
    return (
        Path(_MAIL_ROOT_OVERRIDE).expanduser()
        if _MAIL_ROOT_OVERRIDE
        else Path(os.path.expanduser("~/Library/Mail"))
    )


def _mail_status() -> tuple[str, Path | None]:
    """Diagnose Mail readability. Returns (status, envelope_index_path).

    status is one of:
      ok         — Envelope Index found and the directory is readable
      no_mail    — ~/Library/Mail does not exist (Apple Mail not set up)
      needs_fda  — the directory exists but can't be read (Full Disk Access)
      no_index   — directory readable but no Envelope Index inside
    """
    root = _mail_root()
    if not root.exists():
        return "no_mail", None
    try:
        # Enumerating the protected dir raises PermissionError without Full Disk Access.
        next(root.iterdir(), None)
    except PermissionError:
        return "needs_fda", None
    except OSError:
        return "needs_fda", None
    matches = sorted(root.glob("V*/MailData/Envelope Index"))
    if matches:
        return "ok", matches[-1]
    return "no_index", None


_MAIL_STATUS_HINT = {
    "ok": None,
    "no_mail": "Apple Mail is not set up (~/Library/Mail does not exist).",
    "needs_fda": (
        "~/Library/Mail can't be read — grant Full Disk Access to the process running "
        "this bridge (System Settings > Privacy & Security > Full Disk Access), then "
        "restart it."
    ),
    "no_index": "~/Library/Mail is readable but no 'Envelope Index' was found inside.",
}


def _envelope_index_path() -> Path | None:
    """Locate the most recent Mail.app Envelope Index (None if unreadable/absent)."""
    status, path = _mail_status()
    return path if status == "ok" else None


def _apple_time_to_iso(value) -> str | None:
    """Convert an Envelope Index timestamp to ISO-8601 UTC, tolerantly."""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts < _APPLE_EPOCH_OFFSET:
        ts += _APPLE_EPOCH_OFFSET
    try:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _read_envelope_messages(after_rowid: int, limit: int) -> list[dict]:
    """Return new messages (ROWID > after_rowid) from the Mail Envelope Index."""
    env_path = _envelope_index_path()
    if env_path is None:
        return []
    try:
        conn = sqlite3.connect(f"file:{env_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{env_path}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        if not {"sender", "subject", "date_received"} <= cols:
            print(f"[bridge] unexpected Envelope Index schema: {sorted(cols)}", flush=True)
            return []
        msg_id_expr = "m.message_id" if "message_id" in cols else "NULL"
        read_expr = "m.read" if "read" in cols else "NULL"
        query = f"""
            SELECT m.ROWID         AS rowid,
                   {msg_id_expr}   AS message_id,
                   a.address       AS sender,
                   s.subject       AS subject,
                   m.date_received AS date_received,
                   {read_expr}     AS read_flag
            FROM messages m
            LEFT JOIN addresses a ON a.ROWID = m.sender
            LEFT JOIN subjects  s ON s.ROWID = m.subject
            WHERE m.ROWID > ?
            ORDER BY m.ROWID ASC
            LIMIT ?
        """
        rows = conn.execute(query, (after_rowid, max(1, limit))).fetchall()
    except sqlite3.Error as e:
        print(f"[bridge] Envelope Index read failed: {e}", flush=True)
        return []
    finally:
        conn.close()

    return [
        {
            "rowid": r["rowid"],
            "message_id": r["message_id"] or f"rowid:{r['rowid']}",
            "sender": r["sender"] or "",
            "subject": r["subject"] or "",
            "received_at": _apple_time_to_iso(r["date_received"]),
            "read": bool(r["read_flag"]) if r["read_flag"] is not None else None,
        }
        for r in rows
    ]


# ── osascript helpers (macOS app scripting) ───────────────────────────────────
_REMINDER_JXA = """
function run(argv) {
  var title = argv[0]; var due = argv[1] || "";
  var app = Application("Reminders");
  var r = app.Reminder({name: title});
  app.defaultList().reminders.push(r);
  if (due) { var d = new Date(due); if (!isNaN(d.getTime())) { r.dueDate = d; } }
  return r.id();
}
"""

_REMINDER_STATUS_JXA = """
function run(argv) {
  var id = argv[0];
  var app = Application("Reminders");
  try {
    var r = app.reminders.byId(id);
    return r.completed() ? "completed" : "open";
  } catch (e) { return "missing"; }
}
"""

_NOTE_JXA = """
function run(argv) {
  var noteName = argv[0]; var line = argv[1];
  var app = Application("Notes");
  var esc = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  var notes = app.notes;
  for (var i = 0; i < notes.length; i++) {
    if (notes[i].name() === noteName) {
      notes[i].body = notes[i].body() + "<div>" + esc + "</div>";
      return "appended";
    }
  }
  var n = app.Note({name: noteName, body: "<div><b>" + noteName + "</b></div><div>" + esc + "</div>"});
  app.defaultAccount().notes.push(n);
  return "created";
}
"""


def _osascript(lang: str, script: str, args: list[str], timeout: float = 10.0) -> tuple[bool, str]:
    """Run an AppleScript ('AppleScript') or JXA ('JavaScript') snippet with argv."""
    cmd = ["osascript"]
    if lang == "JavaScript":
        cmd += ["-l", "JavaScript"]
    cmd += ["-e", script, *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()
    return True, (proc.stdout or "").strip()


def _fetch_body(message_id: str) -> str:
    if not message_id or message_id.startswith("rowid:"):
        return ""
    mid = message_id.strip().lstrip("<").rstrip(">")
    script = (
        'tell application "Mail"\n'
        f'  set matches to (every message of inbox whose message id is "{mid}")\n'
        '  if matches is {} then return ""\n'
        "  return content of item 1 of matches\n"
        "end tell"
    )
    ok, out = _osascript("AppleScript", script, [])
    return out[:_BODY_SNIPPET_CHARS] if ok else ""


def _daily_note_name() -> str:
    return f"Sutra Daily Digest — {datetime.datetime.now().date().isoformat()}"


def _create_reminder(title: str, due: str) -> tuple[bool, str]:
    ok, out = _osascript("JavaScript", _REMINDER_JXA, [title or "(no subject)", due or ""])
    return (ok and bool(out)), (out if ok else "")


def _reminder_status(reminder_id: str) -> str:
    if not reminder_id:
        return "unknown"
    ok, out = _osascript("JavaScript", _REMINDER_STATUS_JXA, [reminder_id])
    return out if ok and out in ("completed", "open", "missing") else "unknown"


def _append_note(line: str) -> bool:
    ok, _ = _osascript("JavaScript", _NOTE_JXA, [_daily_note_name(), line])
    return ok


# ── HTTP handler ──────────────────────────────────────────────────────────────
class BridgeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[bridge] {self.address_string()} — {fmt % args}", flush=True)

    def _auth(self) -> bool:
        if not BRIDGE_TOKEN:
            return True  # no token configured → open (local dev only)
        return self.headers.get("Authorization", "") == f"Bearer {BRIDGE_TOKEN}"

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

    def _query(self) -> dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    # ── Route dispatch ────────────────────────────────────────────────────────
    def do_GET(self):  # noqa: N802
        if not self._auth():
            self._send_json({"detail": "Unauthorized"}, 401)
            return
        route = urllib.parse.urlparse(self.path).path
        if route == "/health":
            self._handle_health()
        elif route == "/mail/new":
            self._handle_mail_new()
        elif route == "/mail/body":
            self._handle_mail_body()
        elif route == "/reminders/status":
            self._handle_reminder_status()
        else:
            self._send_json({"detail": "Not found"}, 404)

    def do_POST(self):  # noqa: N802
        if not self._auth():
            self._send_json({"detail": "Unauthorized"}, 401)
            return
        route = urllib.parse.urlparse(self.path).path
        if route == "/reminders":
            self._handle_create_reminder()
        elif route == "/notes/append":
            self._handle_append_note()
        elif route == "/arrival":
            self._handle_arrival()
        else:
            self._send_json({"detail": "Not found"}, 404)

    # ── Handlers ──────────────────────────────────────────────────────────────
    def _handle_health(self) -> None:
        status, env_path = _mail_status()
        self._send_json({
            "ok": status == "ok",
            "mail_status": status,
            "envelope_index": str(env_path) if env_path else None,
            "hint": _MAIL_STATUS_HINT.get(status),
            "version": VERSION,
        })

    def _handle_mail_new(self) -> None:
        q = self._query()
        try:
            after = int(q.get("after", "0"))
            limit = int(q.get("limit", "50"))
        except ValueError:
            self._send_json({"detail": "after/limit must be integers"}, 400)
            return
        status, _ = _mail_status()
        if status != "ok":
            self._send_json(
                {"detail": _MAIL_STATUS_HINT.get(status, "Mail unavailable"), "mail_status": status},
                503,
            )
            return
        self._send_json({"messages": _read_envelope_messages(after, limit)})

    def _handle_mail_body(self) -> None:
        message_id = self._query().get("message_id", "")
        if not message_id:
            self._send_json({"detail": "message_id is required"}, 400)
            return
        self._send_json({"body": _fetch_body(message_id)})

    def _handle_create_reminder(self) -> None:
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"detail": f"Invalid JSON: {e}"}, 400)
            return
        ok, rid = _create_reminder((body.get("title") or "").strip(), (body.get("due") or "").strip())
        self._send_json({"ok": ok, "id": rid})

    def _handle_reminder_status(self) -> None:
        rid = self._query().get("id", "")
        self._send_json({"status": _reminder_status(rid)})

    def _handle_append_note(self) -> None:
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"detail": f"Invalid JSON: {e}"}, 400)
            return
        line = (body.get("line") or "").strip()
        if not line:
            self._send_json({"detail": "line is required"}, 400)
            return
        self._send_json({"ok": _append_note(line)})

    def _handle_arrival(self) -> None:
        """Mail-rule webhook: forward to the container if configured, else spool."""
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError):
            body = {}
        if ARRIVAL_WEBHOOK:
            try:
                req = urllib.request.Request(
                    ARRIVAL_WEBHOOK,
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)  # noqa: S310
            except Exception as e:  # noqa: BLE001
                print(f"[bridge] arrival forward failed: {e}", flush=True)
        else:
            spool = _SCRIPT_DIR.parent / "backend" / ".local" / "smart_organizer_arrivals.log"
            spool.parent.mkdir(parents=True, exist_ok=True)
            with open(spool, "a") as fh:
                fh.write(json.dumps({"at": datetime.datetime.now().isoformat(), **body}) + "\n")
        self._send_json({"ok": True})


# ── Startup ───────────────────────────────────────────────────────────────────
def main() -> None:
    if not BRIDGE_TOKEN:
        print(
            "[bridge] WARNING: SMART_ORGANIZER_BRIDGE_TOKEN is not set — all requests accepted.\n"
            '         Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"',
            file=sys.stderr,
        )
    status, env_path = _mail_status()
    if status == "ok":
        print(f"[bridge] Envelope Index: {env_path}", flush=True)
    else:
        print(f"[bridge] WARNING: mail_status={status} — {_MAIL_STATUS_HINT.get(status)}", file=sys.stderr)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
    print(f"[bridge] Listening on http://127.0.0.1:{BRIDGE_PORT}  (version {VERSION})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bridge] Stopped.", flush=True)


if __name__ == "__main__":
    main()
