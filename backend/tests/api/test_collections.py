"""Read API tests: Collections & Recovery AI Swarm."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient

FLAG_DISPLAY = {"ok": "OK", "review": "Review", "escalate": "Escalate"}


async def test_metric_tiles_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/collections/metrics")

    assert response.status_code == 200
    body = response.json()
    expected = [s for s in seed_data.WAREHOUSE_SIGNALS if s["panel"] == "collections_metrics"]
    assert len(body) == len(expected)
    assert body[0]["label"] == expected[0]["label"]
    assert body[0]["value"] == expected[0]["value"]
    assert body[0]["tone"] == expected[0]["tone"]


async def test_agents_match_seed_with_display_status(client: AsyncClient) -> None:
    response = await client.get("/api/v1/collections/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.COLLECTIONS_AGENTS)
    assert body[0]["name"] == seed_data.COLLECTIONS_AGENTS[0]["name"]
    assert body[0]["status"] == seed_data.COLLECTIONS_AGENTS[0]["status"].capitalize()


async def test_cases_match_seed_with_display_labels(client: AsyncClient) -> None:
    response = await client.get("/api/v1/collections/cases")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.COLLECTIONS_CASES)

    first, expected = body[0], seed_data.COLLECTIONS_CASES[0]
    assert first["customer"] == expected["customer"]
    assert first["dpd"] == expected["dpd"]
    assert first["out"] == expected["outstanding"]
    assert first["roll"] == expected["roll_forward_risk"]
    assert first["channel"] == expected["channel"]
    assert first["action"] == expected["action"]
    assert first["prob"] == expected["prob"]
    assert first["flag"] == FLAG_DISPLAY[expected["compliance_flag"]]
    assert first["status"] == "Pending"
