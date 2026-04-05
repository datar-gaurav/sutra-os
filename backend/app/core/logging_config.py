"""Structured logging configuration with correlation ID injection."""

import logging
import re

from app.middleware.correlation import get_request_id

# Patterns that look like secrets — matched case-insensitively against log messages.
_SECRET_PATTERNS = [
    re.compile(r"(sk-sutra_)[a-zA-Z0-9]{8,}", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[a-zA-Z0-9\-_.]+", re.IGNORECASE),
    re.compile(r"((?:api[_-]?key|secret[_-]?key|token|password|encryption[_-]?key)\s*[=:]\s*)\S+", re.IGNORECASE),
]


def _redact(message: str) -> str:
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(lambda m: m.group(1) + "***REDACTED***", message)
    return message


class CorrelationFilter(logging.Filter):
    """Injects the current request ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


class SecretRedactionFilter(logging.Filter):
    """Redacts common secret patterns from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging(debug: bool = False) -> None:
    """
    Replace basicConfig with structured logging that includes request IDs.
    Call this once at application startup.
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | rid=%(request_id)s | %(message)s"
    level = logging.DEBUG if debug else logging.INFO

    # Apply filter + formatter to the root handler
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicate output
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(CorrelationFilter())
    handler.addFilter(SecretRedactionFilter())
    root.addHandler(handler)
