"""Audit trail for state-changing requests.

Every successful mutating request against the API (POST / PATCH / PUT /
DELETE) is written as a structured ``audit_event`` log entry carrying the
actor, endpoint, target and request id. Combined with the Trust Ledger
this gives compliance a replayable record of every approval, action and
status change made through the platform.

Implemented as middleware so new mutation endpoints are audited
automatically without per-route boilerplate.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger
from app.core.security import DEMO_USER_ID

logger = get_logger(__name__)

MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Emits an ``audit_event`` for every successful mutating request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        path = request.url.path
        if request.method in MUTATING_METHODS and path.startswith("/api/") and 200 <= response.status_code < 300:
            # Last non-empty path segment is typically the target resource id.
            segments = [segment for segment in path.split("/") if segment]
            logger.info(
                "audit_event",
                channel="audit",
                actor=f"demo:{DEMO_USER_ID}",
                method=request.method,
                path=path,
                target=segments[-1] if segments else None,
                status_code=response.status_code,
                request_id=getattr(request.state, "request_id", None),
            )
        return response
