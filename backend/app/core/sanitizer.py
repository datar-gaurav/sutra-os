"""Input sanitization helpers — chat messages, system prompts, and URLs."""

import html
import re
import urllib.parse

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_CHAT_MESSAGE_LENGTH = 32_000
MAX_SYSTEM_PROMPT_LENGTH = 16_000

# Private / non-routable IP ranges (SSRF protection)
_SSRF_BLOCKLIST = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|::1"
    r"|10\."
    r"|172\.(1[6-9]|2[0-9]|3[01])\."
    r"|192\.168\."
    r"|169\.254\."        # link-local
    r"|fc00:|fe80:"       # IPv6 private
    r")",
    re.IGNORECASE,
)

# Heuristic prompt-injection patterns
_INJECTION_PATTERNS = re.compile(
    r"(ignore (all |previous |above )(instructions?|prompts?|rules?)"
    r"|you are now|act as (an? |the )?(ai|assistant|system|admin)"
    r"|system:\s|###\s*(system|instruction))",
    re.IGNORECASE,
)

# Control characters (except common whitespace)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ─── Public helpers ───────────────────────────────────────────────────────────

def sanitize_chat_message(text: str) -> str:
    """Sanitize a user chat message: escape HTML, strip control chars, enforce length."""
    text = _CONTROL_CHARS.sub("", text)
    text = html.escape(text, quote=False)
    if len(text) > MAX_CHAT_MESSAGE_LENGTH:
        raise ValueError(
            f"Message too long ({len(text)} chars). Maximum is {MAX_CHAT_MESSAGE_LENGTH}."
        )
    # Warn-only heuristic: flag but do not block (LLMs handle context)
    # Uncomment the block below to enforce strict rejection:
    # if _INJECTION_PATTERNS.search(text):
    #     raise ValueError("Message contains disallowed patterns.")
    return text.strip()


def sanitize_system_prompt(text: str) -> str:
    """Sanitize a system prompt: strip control chars, enforce length."""
    text = _CONTROL_CHARS.sub("", text)
    if len(text) > MAX_SYSTEM_PROMPT_LENGTH:
        raise ValueError(
            f"System prompt too long ({len(text)} chars). Maximum is {MAX_SYSTEM_PROMPT_LENGTH}."
        )
    return text.strip()


def validate_url(url: str, field_name: str = "URL") -> str:
    """Validate that a URL is well-formed, uses http/https, and is not a private IP (SSRF)."""
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{field_name} must start with http:// or https://")
    host = parsed.hostname or ""
    if _SSRF_BLOCKLIST.match(host):
        raise ValueError(f"{field_name} points to a disallowed private or local address")
    return url
