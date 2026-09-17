"""Request-context middleware.

For every request it:
1. assigns (or propagates) an ``X-Request-ID`` correlation id,
2. binds request-scoped fields to structlog contextvars so every log line
   emitted while handling the request is automatically correlated,
3. logs completion with status code and duration.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlates each request with a unique id and emits an access log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.error(
                "request_failed",
                status_code=500,
                duration_ms=round(duration_ms, 2),
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
