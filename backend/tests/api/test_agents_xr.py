"""Read API tests: AI Factory agents and XR experiences."""

from __future__ import annotations

import uuid

from app.database import seed_data
from httpx import AsyncClient

AGENT_STATUS_DISPLAY = {"active": "Active", "reviewing": "Reviewing", "recommended": "Recommended"}


async def test_agents_match_seed_with_display_status(client: AsyncClient) -> None:
    response = await client.get("/api/v1/agents")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.AI_AGENTS)

    first, expected = body[0], seed_data.AI_AGENTS[0]
    assert first["name"] == expected["name"]
    assert first["role"] == expected["role"]
    assert first["status"] == AGENT_STATUS_DISPLAY[expected["status"]]
    assert first["last"] == expected["last_activity"]
    assert first["uses"] == expected["use_areas"]


async def test_agent_detail_by_id(client: AsyncClient) -> None:
    listing = (await client.get("/api/v1/agents")).json()
    agent_id = listing[0]["id"]

    response = await client.get(f"/api/v1/agents/{agent_id}")

    assert response.status_code == 200
    assert response.json() == listing[0]


async def test_unknown_agent_returns_structured_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    response = await client.get(f"/api/v1/agents/{missing}")

    assert response.status_code == 404
    assert response.json()["code"] == "agent_not_found"


async def test_xr_experiences_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/xr/experiences")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.XR_EXPERIENCES)

    first, expected = body[0], seed_data.XR_EXPERIENCES[0]
    assert first["id"] == expected["code"]
    assert first["title"] == expected["title"]
    assert first["use"] == expected["use_case"]
    assert first["feat"] == expected["feature"]
    assert first["impact"] == expected["impact"]
