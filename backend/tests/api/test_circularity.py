"""Read API tests: Circular Economy."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_credits_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/circularity/credits")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.CARBON_CREDITS)

    first, expected = body[0], seed_data.CARBON_CREDITS[0]
    assert first["id"] == expected["code"]
    assert first["type"] == expected["type"]
    assert first["price"] == expected["price"]
    assert first["match"] == expected["buyer_match"]
    assert first["closure"] == expected["closure_prob"]
    assert first["trace"] == expected["traceability"]


async def test_rvsf_metrics_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/circularity/rvsf-metrics")

    assert response.status_code == 200
    body = response.json()
    expected = [s for s in seed_data.WAREHOUSE_SIGNALS if s["panel"] == "rvsf"]
    assert len(body) == len(expected)
    assert body[0]["label"] == expected[0]["label"]
    assert body[0]["value"] == expected[0]["value"]


async def test_dmrv_prompts_match_seed_questions(client: AsyncClient) -> None:
    response = await client.get("/api/v1/circularity/dmrv/prompts")

    assert response.status_code == 200
    assert response.json() == [item["question"] for item in seed_data.DMRV_QA]
