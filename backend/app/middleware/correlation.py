"""Correlation ID middleware — injects a unique request ID into every request."""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ContextVar so the request ID is accessible anywhere in the async call chain
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_var.get()


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Reads X-Request-ID from incoming headers (or generates a UUID4 if absent).
    Sets the value in a ContextVar so all loggers in the request chain can use it.
    Echoes the ID back on the response as X-Request-ID.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = req_id
        return response
