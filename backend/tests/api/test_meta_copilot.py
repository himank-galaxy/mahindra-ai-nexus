"""Read API tests: simulation metadata and copilot prompt chips."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_simulation_meta_lists_regions_and_models(client: AsyncClient) -> None:
    response = await client.get("/api/v1/simulations/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["regions"] == seed_data.REGIONS
    assert body["models"] == seed_data.VEHICLE_MODELS


async def test_suggested_prompts_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/copilot/suggested-prompts")

    assert response.status_code == 200
    assert response.json() == seed_data.SUGGESTED_PROMPTS
