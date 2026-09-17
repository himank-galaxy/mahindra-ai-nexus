"""Write API tests: recommendation approvals and PoC roadmap CRUD."""

from __future__ import annotations

import uuid

from app.database import seed_data
from httpx import AsyncClient


async def test_approve_recommendation_returns_updated_entity(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/recommendations/r1", json={"status": "Approved"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Approved"
    assert body["title"] == seed_data.RECOMMENDATIONS[0]["title"]

    # Mutation persists across a fresh read.
    listing = (await client.get("/api/v1/overview/recommendations")).json()
    assert next(row for row in listing if row["id"] == "r1")["status"] == "Approved"


async def test_route_recommendation_to_human_review(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/recommendations/r2", json={"status": "Under Review"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "Under Review"


async def test_patch_recommendation_not_found(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/recommendations/r99", json={"status": "Approved"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "recommendation_not_found"


async def test_patch_recommendation_invalid_status_rejected(client: AsyncClient) -> None:
    resp = await client.patch("/api/v1/recommendations/r1", json={"status": "Pending"})
    assert resp.status_code == 422


async def test_poc_crud_flow_with_dedupe(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/poc")).json() == []

    payload = {"name": "AI Simulation Center", "bucket": "Intelligence Platforms"}
    created = await client.post("/api/v1/poc", json=payload)
    assert created.status_code == 201
    item = created.json()
    assert item["name"] == payload["name"]
    assert item["bucket"] == payload["bucket"]
    assert isinstance(item["addedAt"], int)

    # Server-side dedupe: duplicate name is a 409.
    duplicate = await client.post("/api/v1/poc", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate_poc_item"

    listing = (await client.get("/api/v1/poc")).json()
    assert [row["name"] for row in listing] == [payload["name"]]

    removed = await client.delete("/api/v1/poc", params={"name": payload["name"]})
    assert removed.status_code == 204
    assert (await client.get("/api/v1/poc")).json() == []


async def test_poc_delete_missing_returns_404(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/poc", params={"name": "Does Not Exist"})
    assert resp.status_code == 404
    assert resp.json()["code"] == "poc_item_not_found"


async def test_poc_roadmap_plan_matches_dialog(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/poc/roadmap-plan")
    assert resp.status_code == 200
    plan = resp.json()
    assert [phase["p"] for phase in plan["phases"]] == ["Phase 0", "Phase 1", "Phase 2", "Phase 3"]
    assert plan["phases"][0]["t"] == "Discovery"
    assert plan["phases"][3]["w"] == "8-12 weeks"
    assert plan["topPocs"] == [
        "AI Simulation Center",
        "Dealer Revenue Optimizer",
        "Financial Services AI Command Center",
    ]
    assert plan["optional"] == "Optional: Circular Economy Intelligence Platform"


async def test_random_uuid_routes_return_404_envelope(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    resp = await client.post(f"/api/v1/dealer-leads/{missing}/convert")
    assert resp.status_code == 404
    assert resp.json()["code"] == "lead_not_found"
