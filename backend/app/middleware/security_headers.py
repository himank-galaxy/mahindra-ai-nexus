"""Security response headers.

Adds a conservative baseline of defensive headers to every response.
Headers are set with ``setdefault`` so individual routes (e.g. file
downloads) can still override them deliberately.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

BASE_HEADERS: dict[str, str] = {
    # Never sniff a JSON payload into executable content.
    "X-Content-Type-Options": "nosniff",
    # The API is never meant to be embedded in a frame.
    "X-Frame-Options": "DENY",
    # Keep referrer information from leaking to third parties.
    "Referrer-Policy": "no-referrer",
    # No browser features are needed by API consumers.
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=()",
    # API responses must not be cached by shared proxies.
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attaches defensive response headers to every response."""

    def __init__(self, app, *, hsts_enabled: bool = False) -> None:
        super().__init__(app)
        self._hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in BASE_HEADERS.items():
            response.headers.setdefault(name, value)
        if self._hsts_enabled:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
