"""Hardening tests: security headers, rate limiting and the audit trail."""

from __future__ import annotations

import logging

from app.middleware.rate_limit import RateLimitMiddleware
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route


async def _ok(request: Request) -> Response:
    return PlainTextResponse("ok")


def _limited_app(default_limit: int, ai_limit: int) -> Starlette:
    """Minimal ASGI app guarded by the rate-limit middleware."""
    app = Starlette(
        routes=[
            Route("/api/v1/reads", _ok),
            Route("/api/v1/copilot/chat", _ok, methods=["POST"]),
        ]
    )
    app.add_middleware(
        RateLimitMiddleware,
        default_limit=default_limit,
        ai_limit=ai_limit,
        window_seconds=60,
    )
    return app


# --- Security headers --------------------------------------------------------


async def test_responses_carry_security_headers(client: AsyncClient) -> None:
    """Every response is hardened with the defensive baseline headers."""
    response = await client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


async def test_error_responses_also_carry_security_headers(client: AsyncClient) -> None:
    """Hardening headers apply to failures too, not just happy paths."""
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"


# --- Rate limiting -----------------------------------------------------------


async def test_rate_limiter_allows_traffic_under_limit() -> None:
    app = _limited_app(default_limit=3, ai_limit=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(3):
            assert (await ac.get("/api/v1/reads")).status_code == 200


async def test_rate_limiter_rejects_over_limit_with_envelope() -> None:
    """Exceeding the window budget yields a structured 429 with Retry-After."""
    app = _limited_app(default_limit=2, ai_limit=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/api/v1/reads")).status_code == 200
        assert (await ac.get("/api/v1/reads")).status_code == 200
        blocked = await ac.get("/api/v1/reads")

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert blocked.headers["Retry-After"] == "60"


async def test_rate_limiter_tracks_ai_bucket_separately() -> None:
    """AI POSTs have their own stricter budget independent of read traffic."""
    app = _limited_app(default_limit=10, ai_limit=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.post("/api/v1/copilot/chat", json={})).status_code == 200
        blocked = await ac.post("/api/v1/copilot/chat", json={})
        # General reads remain unaffected by the exhausted AI budget.
        assert (await ac.get("/api/v1/reads")).status_code == 200

    assert blocked.status_code == 429


async def test_rate_limited_response_exposes_limit_headers() -> None:
    """Successful responses advertise the budget via X-RateLimit-* headers."""
    app = _limited_app(default_limit=5, ai_limit=1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/reads")

    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


# --- Audit trail ---------------------------------------------------------------


async def test_mutations_emit_audit_event(client: AsyncClient, caplog) -> None:
    """Successful mutations leave a structured audit_event in the logs."""
    path = "/api/v1/trust/decisions/AUTO-1042/approve"
    with caplog.at_level(logging.INFO):
        response = await client.post(path)

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    audit_records = [message for message in messages if "audit_event" in message]
    assert audit_records, "expected an audit_event log entry for the mutation"
    assert any(path in message for message in audit_records)
    assert any("actor" in message for message in audit_records)


async def test_reads_do_not_emit_audit_event(client: AsyncClient, caplog) -> None:
    """GET traffic is not an auditable state change and must stay out of the trail."""
    with caplog.at_level(logging.INFO):
        assert (await client.get("/api/v1/trust/decisions")).status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert not any("audit_event" in message for message in messages)
