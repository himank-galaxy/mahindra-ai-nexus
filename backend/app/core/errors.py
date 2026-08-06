"""Domain exceptions and structured FastAPI exception handlers.

All errors returned by the API share a single envelope:

    { "detail": "<human readable message>", "code": "<machine code>", "request_id": "<uuid>" }

Raise the specific ``AppError`` subclass from services/repositories and let
the registered handlers translate it into an HTTP response.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all domain errors with a stable machine-readable code."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    """Raised when a requested resource does not exist (or is soft-deleted)."""

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"


class ConflictError(AppError):
    """Raised on uniqueness violations or illegal state transitions."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class BadRequestError(AppError):
    """Raised for semantically invalid requests that pass schema validation."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"


class DomainValidationError(AppError):
    """Raised for cross-field business-rule validation failures."""

    status_code = 422  # Unprocessable Content (constant renamed across Starlette versions)
    default_code = "validation_error"


class ExternalServiceError(AppError):
    """Raised when a downstream provider (e.g. LLM) fails."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "external_service_error"


def _request_id(request: Request) -> str | None:
    """Extract the request id assigned by the request-context middleware."""
    return getattr(request.state, "request_id", None)


def _envelope(detail: str, code: str, request: Request, **extra: Any) -> dict[str, Any]:
    """Build the standard error payload envelope."""
    body: dict[str, Any] = {"detail": detail, "code": code, "request_id": _request_id(request)}
    body.update(extra)
    return body


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate domain errors into structured JSON responses."""
    payload = _envelope(exc.message, exc.code, request)
    if exc.details:
        payload["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return Pydantic request-validation failures in the standard envelope."""
    errors = [
        {
            "loc": ".".join(str(part) for part in err.get("loc", [])),
            "msg": err.get("msg", "invalid value"),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    payload = _envelope("Request validation failed.", "validation_error", request, errors=errors)
    return JSONResponse(status_code=422, content=payload)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Normalize plain HTTP exceptions (404 routes, 405 methods, ...) into the envelope."""
    payload = _envelope(str(exc.detail), "http_error", request)
    return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: log with traceback, return an opaque 500."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=exc,
    )
    payload = _envelope("An unexpected error occurred.", "internal_error", request)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all structured exception handlers to the application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


def json_dumps(value: Any) -> str:
    """Compact JSON serialization helper used for JSONB payloads."""
    return json.dumps(value, ensure_ascii=False, default=str)
