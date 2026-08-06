"""End-to-end tests for the health endpoint."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_200_with_envelope(client: AsyncClient) -> None:
    """Health responds 200 with the documented fields regardless of DB state."""
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["service"] == "Mahindra AI Command Center API"
    assert body["database"] in {"up", "down"}
    assert body["environment"]
    assert body["timestamp"]


async def test_health_reports_database_state_consistently(client: AsyncClient) -> None:
    """``status`` must agree with the ``database`` field."""
    body = (await client.get("/health")).json()
    expected_status = "ok" if body["database"] == "up" else "degraded"
    assert body["status"] == expected_status


async def test_responses_carry_request_id_header(client: AsyncClient) -> None:
    """The request-context middleware echoes a correlation id on every response."""
    response = await client.get("/health")
    assert response.headers.get("X-Request-ID")


async def test_unknown_route_returns_structured_error(client: AsyncClient) -> None:
    """Unknown paths return the standard error envelope, not FastAPI defaults."""
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "http_error"
    assert "detail" in body
    assert "request_id" in body
