"""Structured logging configuration with correlation ID injection."""

import logging

from app.middleware.correlation import get_request_id


class CorrelationFilter(logging.Filter):
    """Injects the current request ID into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
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
    root.addHandler(handler)
