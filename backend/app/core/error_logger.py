"""Async error logger — persists platform errors to error_logs table.

Never raises. Safe to call from exception handlers and background tasks.
"""

import json
import logging
import traceback as tb
from typing import Any

logger = logging.getLogger(__name__)


async def log_error(
    source: str,
    error: Exception,
    *,
    severity: str = "error",
    request_path: str | None = None,
    agent_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Persist an error to the error_logs table.

    Args:
        source: Where the error originated (e.g. "route", "background_task", "startup").
        error: The caught exception.
        severity: "debug" | "info" | "warning" | "error" | "critical".
        request_path: HTTP request path if applicable.
        agent_id: Associated agent ID if applicable.
        context: Any additional structured context.
    """
    try:
        from app.db.session import async_session_factory
        from app.models.error_log import ErrorLog

        error_type = type(error).__name__
        message = str(error)
        traceback_str = tb.format_exc()
        if traceback_str.strip() == "NoneType: None":
            traceback_str = None

        context_str = json.dumps(context) if context else None

        async with async_session_factory() as db:
            record = ErrorLog(
                source=source,
                error_type=error_type,
                severity=severity,
                message=message,
                traceback=traceback_str,
                request_path=request_path,
                agent_id=agent_id,
                context=context_str,
            )
            db.add(record)
            await db.commit()
    except Exception as inner:
        # If DB write fails, at minimum log to stderr
        logger.error("error_logger: failed to persist error: %s | original: %s", inner, error)
