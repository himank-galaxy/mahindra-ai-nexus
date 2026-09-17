"""Fixed-window rate limiting.

Protects the API from runaway clients with a lightweight in-memory
fixed-window limiter keyed by client IP. Expensive AI endpoints (copilot
chat, simulations, valuations) get a stricter budget than regular reads.

The counter store is a ``TTLCache`` so idle windows are evicted
automatically. Disable via ``RATE_LIMIT_ENABLED=false`` for load tests.
"""

from __future__ import annotations

from cachetools import TTLCache
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger

logger = get_logger(__name__)

# Path fragments identifying compute-heavy AI endpoints (POST only).
AI_PATH_MARKERS = (
    "/copilot/chat",
    "/executive-summary",
    "/simulations/",
    "/mobility-twin/ask",
    "/elv/estimate",
    "/dmrv/ask",
    "/workflow/run",
    "/explain",
    "/rm-script",
    "/simulate-offer",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter returning the standard error envelope on 429."""

    def __init__(
        self,
        app,
        *,
        default_limit: int,
        ai_limit: int,
        window_seconds: int,
    ) -> None:
        super().__init__(app)
        self._default_limit = default_limit
        self._ai_limit = ai_limit
        self._window_seconds = window_seconds
        # Entries expire after one window; maxsize bounds memory under attack.
        self._hits: TTLCache[tuple[str, str], int] = TTLCache(maxsize=100_000, ttl=window_seconds)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        is_ai = request.method == "POST" and any(marker in path for marker in AI_PATH_MARKERS)
        limit = self._ai_limit if is_ai else self._default_limit

        client_ip = request.client.host if request.client else "unknown"
        bucket = "ai" if is_ai else "default"
        key = (client_ip, bucket)
        current = self._hits.get(key, 0) + 1
        self._hits[key] = current

        if current > limit:
            logger.warning(
                "rate_limited",
                client_ip=client_ip,
                bucket=bucket,
                path=path,
                count=current,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and retry shortly.",
                    "code": "rate_limited",
                    "request_id": getattr(request.state, "request_id", None),
                },
                headers={"Retry-After": str(self._window_seconds)},
            )

        response = await call_next(request)
        response.headers.setdefault("X-RateLimit-Limit", str(limit))
        response.headers.setdefault("X-RateLimit-Remaining", str(max(limit - current, 0)))
        return response
