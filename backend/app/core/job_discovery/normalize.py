"""Normalization helpers shared across adapters and the H-1B matcher.

Keeping this in one place because *both* the H1B matcher and the dedup
soft-match key off `normalize_company`, and we don't want them to drift.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# ─── Company name normalization ──────────────────────────────────────────────

_LEGAL_SUFFIXES = re.compile(
    r"\b("
    r"inc|incorporated|corp|corporation|llc|ltd|limited|company|co|holdings|"
    r"group|llp|lp|plc|gmbh|sa|ag|nv|bv|pvt|private|technology|technologies|"
    r"tech|labs|services|systems|solutions|software|usa|us|na|"
    r"north\s+america"
    r")\b\.?",
    re.IGNORECASE,
)
_PUNCT_TO_SPACE = re.compile(r"[.,&/\-_()]")
_WHITESPACE = re.compile(r"\s+")


def normalize_company(name: str | None) -> str:
    """Lowercase, strip legal suffixes/punctuation, collapse whitespace."""
    if not name:
        return ""
    s = name.lower().strip()
    s = _LEGAL_SUFFIXES.sub("", s)
    s = _PUNCT_TO_SPACE.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


# ─── URL canonicalization ────────────────────────────────────────────────────

# Tracking params we always strip from apply URLs before hashing.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid", "src", "source", "lever-source", "lever_source",
    "ref", "referrer", "trk", "trkCampaign",
}


def canonicalize_url(url: str | None) -> str:
    """Strip tracking params, lowercase host, drop fragment.

    Empty input returns "" — the caller should fall back to a composite hash.
    """
    if not url:
        return ""
    try:
        u = urlparse(url.strip())
    except Exception:
        return url.strip()

    if not u.scheme or not u.netloc:
        return url.strip()

    host = u.netloc.lower()
    # Drop default ports
    if host.endswith(":80") or host.endswith(":443"):
        host = host.rsplit(":", 1)[0]

    # Filter tracking params, preserve everything else.
    qs = parse_qs(u.query, keep_blank_values=True)
    qs = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
    new_query = urlencode(qs, doseq=True)

    # Drop trailing slash on the path so /jobs/123 == /jobs/123/
    path = u.path.rstrip("/") or "/"
    return urlunparse((u.scheme.lower(), host, path, u.params, new_query, ""))


def dedup_hash(canonical_url: str, *, fallback: tuple[str, str, str] | None = None) -> str:
    """Hash a canonical URL. Falls back to (company, title, location) if URL is empty."""
    if canonical_url:
        material = f"url:{canonical_url}"
    elif fallback:
        co, title, loc = fallback
        material = f"composite:{normalize_company(co)}|{(title or '').lower().strip()}|{(loc or '').lower().strip()}"
    else:
        # Last-resort entropy — should never happen in practice, but better
        # than colliding on empty string.
        material = "empty:" + canonical_url
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ─── Title matching ──────────────────────────────────────────────────────────

_TITLE_TOKENIZE = re.compile(r"[a-z0-9]+")


def title_matches(
    title: str,
    title_query: str,
    keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Return (matched, hit_terms).

    Match strategy:
      - whole-word match of every token in `title_query` (case-insensitive)
      - OR whole-word match of any of `keywords`
      - AND no whole-word match of any of `exclude_keywords`
    """
    if not title:
        return False, []
    title_l = title.lower()
    title_tokens = set(_TITLE_TOKENIZE.findall(title_l))

    # Exclusions kill the match outright.
    for ex in exclude_keywords or []:
        ex_l = ex.lower().strip()
        if not ex_l:
            continue
        ex_tokens = _TITLE_TOKENIZE.findall(ex_l)
        if ex_tokens and all(t in title_tokens for t in ex_tokens):
            return False, []

    hits: list[str] = []

    query_tokens = _TITLE_TOKENIZE.findall(title_query.lower())
    if query_tokens and all(t in title_tokens for t in query_tokens):
        hits.append(title_query)

    for kw in keywords or []:
        kw_l = kw.lower().strip()
        if not kw_l:
            continue
        kw_tokens = _TITLE_TOKENIZE.findall(kw_l)
        if kw_tokens and all(t in title_tokens for t in kw_tokens):
            hits.append(kw)

    return bool(hits), hits


# ─── No-sponsorship phrase detection ─────────────────────────────────────────

# Match a negation word ("no", "not", "unable to", "does not", "don't",
# "without", "cannot") followed within ~4 words by a sponsorship keyword
# ("sponsor", "sponsorship", "visa", "h-1b"). Handles "does not offer visa
# sponsorship", "unable to sponsor", "we don't sponsor", etc.
_NO_SPONSOR = re.compile(
    r"(?:no|not|cannot|unable\s+to|do(?:es)?\s+not|don[’'`]?t|without)"
    r"\s+(?:[\w-]+\s+){0,4}"
    r"(?:sponsor(?:ship)?|visas?|h-?1b)",
    re.IGNORECASE,
)


def has_no_sponsorship_phrase(text: str | None) -> bool:
    """Return True if the JD snippet contains a 'no sponsorship' phrase."""
    if not text:
        return False
    return bool(_NO_SPONSOR.search(text))
