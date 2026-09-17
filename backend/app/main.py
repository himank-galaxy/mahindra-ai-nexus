"""FastAPI application factory.

Wires together configuration, structured logging, middleware, exception
handlers and routers. Run locally with:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.database.session import dispose_engine
from app.middleware.audit_log import AuditLogMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.mobility_causal_cache import refresh_loop as mobility_causal_refresh_loop

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: log startup, run the Auto Mobility Causal
    Twin's in-process refresh loop, and release pooled connections on
    shutdown.

    The mobility causal graph has no replay/scheduler container (unlike
    manufacturing/telematics) — it's recomputed by this one background
    task running inside the API process itself. See
    docs/Implementation_plan_mobility_causal.md §4.
    """
    settings = get_settings()
    logger.info(
        "application_startup",
        environment=settings.environment,
        version=settings.app_version,
    )
    mobility_task = asyncio.create_task(mobility_causal_refresh_loop())
    yield
    mobility_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await mobility_task
    await dispose_engine()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.json_logs)

    # Interactive API docs are a development convenience; disabled in production.
    is_production = settings.environment == "production"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production backend for the Mahindra AI Command Center: unified AI intelligence "
            "across automotive, farm equipment, finance, logistics and circularity value chains."
        ),
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # Middleware (last added runs first): CORS outermost for preflights, then
    # security headers, request context (assigns X-Request-ID), rate limiting
    # and finally the audit trail around the actual route handlers.
    app.add_middleware(AuditLogMiddleware)
    if settings.rate_limit_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            default_limit=settings.rate_limit_requests,
            ai_limit=settings.rate_limit_ai_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Structured error handling for every route.
    register_exception_handlers(app)

    # Routers: health at root, domain endpoints under /api/v1.
    app.include_router(health_router)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
