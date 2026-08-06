"""Health endpoint (mounted at application root, outside /api/v1)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import get_settings
from app.database.session import check_database
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness/readiness probe",
    description="Reports service state and PostgreSQL connectivity. Returns 200 even when "
    "degraded so orchestrators can distinguish app-level from dependency-level failures.",
)
async def health() -> HealthResponse:
    """Return service health including a live database connectivity check."""
    settings = get_settings()
    db_up = await check_database()
    return HealthResponse(
        status="ok" if db_up else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database="up" if db_up else "down",
        timestamp=datetime.now(UTC),
    )
