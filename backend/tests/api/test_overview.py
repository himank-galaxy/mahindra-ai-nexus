"""Read API tests: Executive Overview."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_kpis_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/overview/kpis")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.KPIS)

    first, expected = body[0], seed_data.KPIS[0]
    assert first["id"] == expected["code"]
    assert first["label"] == expected["label"]
    assert first["value"] == expected["value"]
    assert first["trend"] == expected["trend"]
    assert first["up"] == expected["up"]
    assert first["confidence"] == expected["confidence"]
    assert first["drivers"] == expected["drivers"]


async def test_recommendations_match_seed_with_display_labels(client: AsyncClient) -> None:
    response = await client.get("/api/v1/overview/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.RECOMMENDATIONS)

    first, expected = body[0], seed_data.RECOMMENDATIONS[0]
    assert first["id"] == expected["code"]
    assert first["title"] == expected["title"]
    assert first["impact"] == expected["impact"]
    assert first["confidence"] == expected["confidence"]
    assert first["risk"] == expected["risk"].capitalize()
    assert first["status"] == "Pending"
