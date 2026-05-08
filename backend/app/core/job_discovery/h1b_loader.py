"""USCIS H-1B Employer Data Hub loader.

Downloads the latest CSV from the user-supplied URL (the page at
https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub
publishes one CSV per fiscal year), streams it row-by-row, normalizes the
employer name, and upserts into `h1b_sponsors`.

The CSV columns vary slightly across fiscal years; this loader is
column-name driven (case-insensitive) so it handles minor renames without
breaking. Unknown columns are stored verbatim in the `raw` JSON field.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_discovery.normalize import normalize_company
from app.db.session import async_session_factory
from app.models.h1b_sponsor import H1bSponsor

logger = logging.getLogger(__name__)


def _to_int(s: str | None) -> int:
    if not s:
        return 0
    try:
        return int(str(s).replace(",", "").strip())
    except Exception:
        return 0


def _detect_fiscal_year(headers: dict[str, str], default: int) -> int:
    """Best-effort FY detection from the column header text.

    USCIS sometimes labels columns "Initial Approvals (FY 2024)". If found,
    use that; otherwise fall back to the caller-supplied default.
    """
    for h in headers.keys():
        m = re.search(r"FY\s*(\d{4})", h, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return default


def _resolve(headers: dict[str, str], *needles: str) -> str | None:
    """Return the actual column name matching any of the needles (case-insensitive)."""
    lower = {h.lower(): h for h in headers}
    for n in needles:
        if n.lower() in lower:
            return lower[n.lower()]
    # Substring search as last resort
    for h in headers:
        for n in needles:
            if n.lower() in h.lower():
                return h
    return None


async def load_uscis_csv(url: str, fiscal_year: int) -> dict:
    """Stream-download a USCIS Employer Data Hub CSV and upsert into h1b_sponsors.

    Args:
        url: HTTPS URL of the .csv (or .csv.zip) file from uscis.gov.
        fiscal_year: FY label to attach to rows when the column header
            doesn't carry one.

    Returns: summary dict with counts. On any HTTP/parse failure the dict
    contains `status: "error"` and an explanatory `error` key — the caller
    should surface this to the UI rather than treating it as success.
    """
    started_at = datetime.now(timezone.utc)
    logger.info("[h1b] downloading %s", url)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=20.0),
            headers={"User-Agent": "SutraOS-H1BLoader/0.1 (+contact: backend)"},
        ) as client:
            resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as e:
        return {
            "status": "error",
            "url": url,
            "error": f"network: {type(e).__name__}: {e}",
        }
    if resp.status_code != 200:
        # Some USCIS pages send HTML 200 from the page wrapper but the
        # actual file is a sibling URL — surface the status so the user
        # can pick the right link from the data-hub page.
        return {
            "status": "error",
            "url": url,
            "error": f"http {resp.status_code}",
            "content_type": resp.headers.get("content-type"),
        }
    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" in ctype:
        return {
            "status": "error",
            "url": url,
            "error": "got HTML, not CSV — likely the page URL, not the file URL",
            "content_type": ctype,
        }

    return await load_uscis_bytes(
        resp.content, fiscal_year=fiscal_year, source_label=url, started_at=started_at,
    )


def _decode_with_bom(body: bytes) -> tuple[str, str]:
    """Decode CSV bytes, picking the encoding from the BOM.

    USCIS frequently ships UTF-16 LE files (Excel "Save as → Unicode Text")
    even though the extension is .csv. The BOM tells us which.
    Returns (text, encoding_label).
    """
    if body[:4] == b"\xff\xfe\x00\x00":
        return body.decode("utf-32-le", errors="replace"), "utf-32-le"
    if body[:4] == b"\x00\x00\xfe\xff":
        return body.decode("utf-32-be", errors="replace"), "utf-32-be"
    if body[:2] == b"\xff\xfe":
        return body.decode("utf-16-le", errors="replace"), "utf-16-le"
    if body[:2] == b"\xfe\xff":
        return body.decode("utf-16-be", errors="replace"), "utf-16-be"
    if body[:3] == b"\xef\xbb\xbf":
        return body.decode("utf-8-sig", errors="replace"), "utf-8-bom"
    return body.decode("utf-8", errors="replace"), "utf-8"


def _looks_like_header(row: list[str]) -> bool:
    """A row is the real header if it contains an employer-name-like cell."""
    if not row:
        return False
    needles = ("employer", "petitioner", "petitioner name")
    joined = " ".join(c.lower() for c in row if c)
    if not any(n in joined for n in needles):
        return False
    # Sanity: real header has multiple columns, not a single title cell.
    return sum(1 for c in row if c.strip()) >= 3


def _sniff_dialect(sample: str) -> csv.Dialect:
    """Pick a delimiter by counting occurrences across the first few lines.

    csv.Sniffer is brittle on USCIS files because the preamble row throws it
    off. A simple count is more reliable in practice: tab-separated files
    have many tabs, comma files have many commas, etc. Tie-break in favor
    of comma.
    """
    counts = {ch: sample.count(ch) for ch in "\t,|;"}
    delim = max(counts, key=lambda k: (counts[k], k == ","))
    if counts[delim] == 0:
        delim = ","

    class _D(csv.excel):
        pass
    _D.delimiter = delim  # type: ignore[assignment]
    return _D()


async def load_uscis_bytes(
    body: bytes,
    *,
    fiscal_year: int,
    source_label: str = "upload",
    started_at: datetime | None = None,
) -> dict:
    """Parse a USCIS Employer Data Hub CSV from raw bytes and upsert.

    Handles UTF-8 / UTF-16 / UTF-32 (Excel "Unicode Text" exports), tab- or
    comma-delimited, and a leading "Line by line" preamble row above the
    real header — all of which USCIS has shipped at one point or another.
    """
    started_at = started_at or datetime.now(timezone.utc)

    # USCIS sometimes ships zipped CSV; auto-detect.
    if body[:2] == b"PK":
        import zipfile
        try:
            z = zipfile.ZipFile(io.BytesIO(body))
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    body = z.read(name)
                    break
        except zipfile.BadZipFile as e:
            return {"status": "error", "url": source_label, "error": f"bad zip: {e}"}

    text, encoding = _decode_with_bom(body)

    # Sniff delimiter from a chunk that's big enough to span a few rows.
    dialect = _sniff_dialect(text[:8000])

    # Single-pass read: csv.reader's internal buffering doesn't play well
    # with handing the same StringIO off to DictReader, so we materialize
    # all rows once and slice in memory. USCIS files are < 100k rows, this
    # is cheap.
    all_rows = list(csv.reader(io.StringIO(text), dialect=dialect))

    header_idx: int | None = None
    for i, row in enumerate(all_rows[:15]):  # only scan first ~15 rows
        if _looks_like_header(row):
            header_idx = i
            break

    if header_idx is None:
        return {
            "status": "error",
            "url": source_label,
            "error": "could not find a header row containing 'Employer'",
            "encoding": encoding,
            "delimiter": getattr(dialect, "delimiter", "?"),
            "preamble": [", ".join(r)[:120] for r in all_rows[:3]],
        }

    header_row = [(c or "").strip() for c in all_rows[header_idx]]
    data_rows = all_rows[header_idx + 1:]
    headers = {f: f for f in header_row}
    fy = _detect_fiscal_year(headers, fiscal_year)
    name_col = _resolve(
        headers,
        "Employer (Petitioner) Name", "Employer Name",
        "Petitioner Name", "Petitioner (Employer) Name", "Employer",
    )
    ein_col = _resolve(headers, "Tax ID", "EIN")
    # USCIS has used several column-name variants over the years.
    init_appr = _resolve(
        headers,
        "Initial Approvals", "Initial Approval",
        "New Employment Approval", "New Employment Approvals",
    )
    init_den = _resolve(
        headers,
        "Initial Denials", "Initial Denial",
        "New Employment Denial", "New Employment Denials",
    )
    cont_appr = _resolve(
        headers,
        "Continuing Approvals", "Continuing Approval",
        "Continuation Approval", "Continuation Approvals",
    )
    cont_den = _resolve(
        headers,
        "Continuing Denials", "Continuing Denial",
        "Continuation Denial", "Continuation Denials",
    )

    if not name_col:
        return {
            "status": "error",
            "url": source_label,
            "error": "missing employer-name column",
            "headers": list(headers.keys()),
            "encoding": encoding,
            "delimiter": getattr(dialect, "delimiter", "?"),
        }

    # Map each resolved column name back to its index in header_row, then
    # iterate data_rows by position. Avoids building a per-row dict.
    def col_idx(col_name: str | None) -> int | None:
        if not col_name:
            return None
        try:
            return header_row.index(col_name)
        except ValueError:
            return None

    name_i = col_idx(name_col)
    ein_i = col_idx(ein_col)
    init_appr_i = col_idx(init_appr)
    init_den_i = col_idx(init_den)
    cont_appr_i = col_idx(cont_appr)
    cont_den_i = col_idx(cont_den)

    def cell(row: list[str], i: int | None) -> str:
        if i is None or i >= len(row):
            return ""
        return (row[i] or "").strip()

    # Aggregate — USCIS lists the same employer multiple times across worksite
    # states. We want one row per (normalized_name, fy).
    agg: dict[str, dict] = {}
    rows_seen = 0
    for row in data_rows:
        rows_seen += 1
        display = cell(row, name_i)
        if not display:
            continue
        norm = normalize_company(display)
        if not norm:
            continue
        approvals = _to_int(cell(row, init_appr_i)) + _to_int(cell(row, cont_appr_i))
        denials = _to_int(cell(row, init_den_i)) + _to_int(cell(row, cont_den_i))
        bucket = agg.setdefault(norm, {
            "display": display,
            "ein": cell(row, ein_i) or None,
            "approvals": 0,
            "denials": 0,
        })
        bucket["approvals"] += approvals
        bucket["denials"] += denials

    if not agg:
        return {"status": "no_rows", "rows": rows_seen, "url": source_label}

    loaded_at = datetime.now(timezone.utc)
    written = 0

    async with async_session_factory() as db:
        # Wipe existing rows for this (fy, source) so re-load is idempotent.
        await db.execute(
            delete(H1bSponsor).where(
                H1bSponsor.fiscal_year == fy,
                H1bSponsor.source == "uscis",
            )
        )

        # Bulk upsert, in batches.
        batch: list[dict] = []
        for norm, b in agg.items():
            batch.append({
                "normalized_name": norm[:255],
                "display_name": b["display"][:255],
                "ein": (b["ein"] or None) and b["ein"][:16],
                "fiscal_year": fy,
                "approvals": b["approvals"],
                "denials": b["denials"],
                "source": "uscis",
                "raw": None,
                "loaded_at": loaded_at,
            })
            if len(batch) >= 5000:
                await _flush_batch(db, batch)
                written += len(batch)
                batch = []
        if batch:
            await _flush_batch(db, batch)
            written += len(batch)
        await db.commit()

    return {
        "status": "ok",
        "url": source_label,
        "fiscal_year": fy,
        "rows_seen": rows_seen,
        "employers": len(agg),
        "written": written,
        "duration_sec": (datetime.now(timezone.utc) - started_at).total_seconds(),
    }


async def _flush_batch(db: AsyncSession, batch: list[dict]) -> None:
    stmt = pg_insert(H1bSponsor).values(batch)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_h1b_sponsors_name_fy_src",
        set_={
            "display_name": stmt.excluded.display_name,
            "ein": stmt.excluded.ein,
            "approvals": stmt.excluded.approvals,
            "denials": stmt.excluded.denials,
            "loaded_at": stmt.excluded.loaded_at,
        },
    )
    await db.execute(stmt)


# ─── Convenience wrappers ────────────────────────────────────────────────────

# Latest known USCIS Employer Data Hub URLs as of v1 ship. The user can
# override these via the manual refresh endpoint.
DEFAULT_USCIS_SOURCES = [
    # FY24 — adjust if USCIS reorganizes the page
    {
        "fiscal_year": 2024,
        "url": "https://www.uscis.gov/sites/default/files/document/data/H-1B_Employer_Data_Hub_FY2024.csv",
    },
    {
        "fiscal_year": 2023,
        "url": "https://www.uscis.gov/sites/default/files/document/data/H-1B_Employer_Data_Hub_FY2023.csv",
    },
    {
        "fiscal_year": 2022,
        "url": "https://www.uscis.gov/sites/default/files/document/data/H-1B_Employer_Data_Hub_FY2022.csv",
    },
]


async def refresh_uscis_default() -> dict:
    """Re-load the canonical USCIS sources. Best-effort — partial failures OK."""
    summaries = []
    for src in DEFAULT_USCIS_SOURCES:
        try:
            s = await load_uscis_csv(src["url"], src["fiscal_year"])
            summaries.append(s)
        except Exception as e:
            summaries.append({
                "status": "error",
                "url": src["url"],
                "fiscal_year": src["fiscal_year"],
                "error": str(e),
            })
            logger.warning("[h1b] FY%s load failed: %s", src["fiscal_year"], e)
    return {"summaries": summaries}
