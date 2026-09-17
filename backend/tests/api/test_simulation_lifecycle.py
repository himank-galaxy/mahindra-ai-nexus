"""Simulation run lifecycle: get, approve, reject, duplicate-decision rejection.

See docs/simulation_centre_implementation.md §2/§7. Auto Sales is the only
engine wired into persistence so far, so it is the vehicle for these
lifecycle tests; the lifecycle endpoints themselves are domain-agnostic.
Uses the shared ``auto_sales_funnel`` seed (tests/conftest.py) since Phase 2
requires real historical data to produce a run at all.
"""

from __future__ import annotations

from httpx import AsyncClient

BASE = "/api/v1/simulations"


async def _create_run(client: AsyncClient) -> str:
    response = await client.post(f"{BASE}/auto-sales/run", json={})
    assert response.status_code == 200
    return response.json()["run_id"]


async def test_get_run_returns_persisted_envelope(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    response = await client.get(f"{BASE}/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["domain"] == "auto-sales"
    assert body["status"] == "PROPOSED"
    assert body["scenario_name"] == "Baseline FY26"
    assert isinstance(body["outputs"]["uplift"], int)
    assert body["confidence_basis"] == "calibrated_heuristic"
    assert body["model_name"] == "auto_sales.logit_conversion_cancellation_v1"


async def test_get_unknown_run_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "simulation_run_not_found"


async def test_approve_run_updates_status(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    response = await client.post(f"{BASE}/{run_id}/approve", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "APPROVED"
    assert body["decision"] == "approved"

    refetched = await client.get(f"{BASE}/{run_id}")
    assert refetched.json()["status"] == "APPROVED"


async def test_duplicate_approval_is_rejected(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)
    first = await client.post(f"{BASE}/{run_id}/approve", json={})
    assert first.status_code == 200

    second = await client.post(f"{BASE}/{run_id}/approve", json={})

    assert second.status_code == 409
    assert second.json()["code"] == "simulation_run_already_decided"


async def test_reject_run_updates_status_with_reason(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    response = await client.post(
        f"{BASE}/{run_id}/reject",
        json={"reason": "Discount too aggressive for the margin target."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["decision"] == "rejected"


async def test_approve_after_reject_is_rejected(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)
    await client.post(f"{BASE}/{run_id}/reject", json={})

    response = await client.post(f"{BASE}/{run_id}/approve", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "simulation_run_already_decided"
