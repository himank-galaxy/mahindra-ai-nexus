"""Health-check schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Service liveness/readiness report."""

    status: Literal["ok", "degraded"] = Field(description="'ok' when all dependencies are reachable.")
    service: str = Field(description="Service display name.")
    version: str = Field(description="API version.")
    environment: str = Field(description="Deployment environment.")
    database: Literal["up", "down"] = Field(description="PostgreSQL connectivity state.")
    timestamp: datetime = Field(description="Server time (UTC) of the check.")
