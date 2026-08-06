"""Shared schema primitives reused across endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error envelope returned by every failure path."""

    detail: str = Field(description="Human-readable error message.")
    code: str = Field(description="Stable machine-readable error code.")
    request_id: str | None = Field(default=None, description="Correlation id for support.")
    errors: list[dict[str, Any]] | None = Field(default=None, description="Field-level validation errors, if any.")
    details: dict[str, Any] | None = Field(default=None, description="Additional domain-specific context.")
