"""Read API tests: Logistics Control Tower."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_routes_match_seed_with_camel_case_aliases(client: AsyncClient) -> None:
    response = await client.get("/api/v1/logistics/routes")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.LOGISTICS_ROUTES)

    first, expected = body[0], seed_data.LOGISTICS_ROUTES[0]
    assert first["name"] == expected["name"]
    assert first["slaRisk"] == expected["sla_risk"]
    assert first["delayProb"] == expected["delay_prob"]
    assert first["cost"] == expected["cost"]
    assert first["action"] == expected["recommended_action"]
    assert first["rerouted"] is False


async def test_warehouse_signals_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/logistics/warehouse-signals")

    assert response.status_code == 200
    body = response.json()
    expected = [s for s in seed_data.WAREHOUSE_SIGNALS if s["panel"] == "warehouse"]
    assert len(body) == len(expected)
    assert body[0] == {"label": expected[0]["label"], "value": expected[0]["value"], "tone": expected[0]["tone"]}
