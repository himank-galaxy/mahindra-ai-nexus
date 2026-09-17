"""Write API tests: collections case actions and logistics corrective actions."""

from __future__ import annotations

import uuid

from app.services.collections import CASE_LEDGER_STEPS
from app.services.logistics import AUTO_HEAL_STEPS
from httpx import AsyncClient


async def _first_case(client: AsyncClient) -> dict:
    cases = (await client.get("/api/v1/collections/cases")).json()
    assert cases, "seed must provide collections cases"
    return cases[0]


async def _first_route(client: AsyncClient) -> dict:
    routes = (await client.get("/api/v1/logistics/routes")).json()
    assert routes, "seed must provide logistics routes"
    return routes[0]


async def test_approve_case_returns_updated_entity(client: AsyncClient) -> None:
    case = await _first_case(client)
    resp = await client.post(f"/api/v1/collections/cases/{case['id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Approved"

    # Persisted across reload.
    cases = (await client.get("/api/v1/collections/cases")).json()
    assert next(row for row in cases if row["id"] == case["id"])["status"] == "Approved"


async def test_modify_case_records_new_action(client: AsyncClient) -> None:
    case = await _first_case(client)
    resp = await client.post(
        f"/api/v1/collections/cases/{case['id']}/modify",
        json={"action": "Field visit + settlement"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Modified"


async def test_review_case_routes_to_human_review(client: AsyncClient) -> None:
    case = await _first_case(client)
    resp = await client.post(f"/api/v1/collections/cases/{case['id']}/review")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Human Review"


async def test_case_ledger_returns_trust_trail(client: AsyncClient) -> None:
    case = await _first_case(client)
    resp = await client.get(f"/api/v1/collections/cases/{case['id']}/ledger")
    assert resp.status_code == 200
    assert resp.json() == CASE_LEDGER_STEPS


async def test_case_actions_missing_case_return_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    resp = await client.post(f"/api/v1/collections/cases/{missing}/approve")
    assert resp.status_code == 404
    assert resp.json()["code"] == "case_not_found"


async def test_predict_delay_echoes_current_probability(client: AsyncClient) -> None:
    route = await _first_route(client)
    resp = await client.post(f"/api/v1/logistics/routes/{route['id']}/predict-delay")
    assert resp.status_code == 200
    assert resp.json()["delayProb"] == route["delayProb"]


async def test_reroute_sets_flag_and_persists(client: AsyncClient) -> None:
    route = await _first_route(client)
    resp = await client.post(f"/api/v1/logistics/routes/{route['id']}/reroute")
    assert resp.status_code == 200
    assert resp.json()["rerouted"] is True

    routes = (await client.get("/api/v1/logistics/routes")).json()
    assert next(row for row in routes if row["id"] == route["id"])["rerouted"] is True


async def test_auto_heal_returns_five_step_workflow(client: AsyncClient) -> None:
    route = await _first_route(client)
    resp = await client.post(f"/api/v1/logistics/routes/{route['id']}/auto-heal")
    assert resp.status_code == 200
    body = resp.json()
    assert body["steps"] == AUTO_HEAL_STEPS
    assert body["route"]["name"] == route["name"]


async def test_route_actions_missing_route_return_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    resp = await client.post(f"/api/v1/logistics/routes/{missing}/auto-heal")
    assert resp.status_code == 404
    assert resp.json()["code"] == "route_not_found"
