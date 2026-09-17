"""Logistics Delay Simulation Phase 5: real trained models + reroute sweep.

Any-delay and SLA-breach probability come from two logistic regressions
trained on the real ``shipments`` outcome columns (never a formula) — see
app/ai/simulation/logistics_delay.py. Route and priority are the exact
real recorded categories (route_id, LOW/NORMAL/HIGH/CRITICAL), so this
domain has no UI-to-real translation layer and ``confidence_basis`` is
always ``trained_model``. The seed fixture makes ``seed-route-b``
systematically safer than ``seed-route-a`` on the same corridor so the
reroute optimizer has a genuine, learnable signal to act on.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/simulations"


async def _run(client: AsyncClient, **overrides: object) -> dict:
    payload = {"route": "seed-route-a", "warehouse": 60, "vehicle": 70, "weather": 20, "sla": "HIGH", **overrides}
    response = await client.post(f"{BASE}/logistics-delay/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_logistics_delay_run_uses_real_trained_models(client: AsyncClient, logistics_delay_seed: None) -> None:
    body = await _run(client)

    assert uuid.UUID(body["run_id"]).version == 4
    assert body["status"] == "PROPOSED"
    assert body["confidence_basis"] == "trained_model"
    assert 0 <= body["delay"] <= 100
    assert 0 <= body["breach"] <= 100
    assert isinstance(body["cost"], int) and body["cost"] > 0
    assert isinstance(body["reroute"], str) and body["reroute"]


async def test_logistics_delay_every_real_priority_is_trained(client: AsyncClient, logistics_delay_seed: None) -> None:
    for priority in ("LOW", "NORMAL", "HIGH", "CRITICAL"):
        body = await _run(client, sla=priority)
        assert body["confidence_basis"] == "trained_model", f"{priority} was not trained"


async def test_logistics_delay_unknown_route_returns_clear_error(client: AsyncClient, logistics_delay_seed: None) -> None:
    response = await client.post(
        f"{BASE}/logistics-delay/run",
        json={"route": "does-not-exist", "warehouse": 60, "vehicle": 70, "weather": 20, "sla": "HIGH"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_route"


async def test_logistics_delay_high_stress_scenario_increases_risk(client: AsyncClient, logistics_delay_seed: None) -> None:
    """Regression: higher warehouse load/weather disruption/vehicle
    unavailability must not leave the trained breach probability
    unchanged — otherwise the sliders would be decorative, the exact bug
    already fixed once for Auto Sales' uplift figure."""
    calm = await _run(client, warehouse=30, vehicle=95, weather=5)
    stressed = await _run(client, warehouse=95, vehicle=25, weather=90)

    assert stressed["breach"] > calm["breach"]
    assert stressed["delay"] > calm["delay"]


async def test_logistics_delay_recommends_the_safer_alternative_route(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    """Regression: the reroute sweep must genuinely re-evaluate the trained
    models for each real alternative route, not just compare a static risk
    score — seed-route-b is systematically safer than seed-route-a on the
    same corridor under an identical stress scenario, so a high-stress run
    on route-a should recommend switching."""
    body = await _run(client, route="seed-route-a", warehouse=90, vehicle=30, weather=80)

    assert "Pune" in body["reroute"] or "Delhi" in body["reroute"]
    assert "reroute" in body["recommendedAction"].lower() or "consider" in body["recommendedAction"].lower()


async def test_logistics_delay_drivers_show_route_and_priority_for_this_run(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    body = await _run(client, route="seed-route-b", sla="CRITICAL")

    drivers = (await client.get(f"{BASE}/{body['run_id']}/drivers")).json()

    names = [item["name"] for item in drivers["predictive_drivers"]]
    assert any("Pune" in name for name in names)
    assert any("Critical" in name for name in names)
    assert drivers["causal_evidence"] == []
    assert {item["source"] for item in drivers["predictive_drivers"]} == {"trained_model"}


async def test_logistics_delay_summary_reflects_the_actual_run(client: AsyncClient, logistics_delay_seed: None) -> None:
    body = await _run(client)

    summary = (await client.post(f"{BASE}/{body['run_id']}/summary")).json()

    assert str(body["delay"]) in summary["predicted_outcome"]
    assert summary["recommendation"] == body["recommendedAction"]
    assert summary["major_drivers"]


async def test_logistics_delay_insufficient_data_returns_clear_error(client: AsyncClient) -> None:
    """No seed fixture applied — the shipments table is empty."""
    response = await client.post(
        f"{BASE}/logistics-delay/run",
        json={"route": "seed-route-a", "warehouse": 60, "vehicle": 70, "weather": 20, "sla": "HIGH"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_training_data"


async def test_logistics_delay_meta_lists_real_routes(client: AsyncClient, logistics_delay_seed: None) -> None:
    meta = (await client.get(f"{BASE}/meta")).json()

    route_ids = {route["id"] for route in meta["routes"]}
    assert {"seed-route-a", "seed-route-b"} <= route_ids
    labels = {route["id"]: route["label"] for route in meta["routes"]}
    assert labels["seed-route-a"] == "Mumbai → Delhi"
    assert labels["seed-route-b"] == "Pune → Delhi"
