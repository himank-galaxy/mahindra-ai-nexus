"""Auto Sales Simulation Phase 2: real trained models over a seeded funnel.

Exact numeric outputs depend on a fitted logistic regression's internal
convergence, so assertions check shape, ranges and monotonic-ish sanity
(e.g. confidence never exceeds the calibrated-heuristic ceiling) rather
than brittle hardcoded values — see
docs/simulation_centre_implementation.md §11 (testing plan).

The ``auto_sales_funnel`` fixture (tests/conftest.py) seeds a small, noisy
leads -> bookings -> cancellations funnel shared with the run-lifecycle
tests, so both suites exercise the real engine rather than the old
formula.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/simulations"
REGION = "West"
MODEL = "XUV700"
LEAD_COUNT = 320


async def _run(client: AsyncClient) -> dict:
    response = await client.post(f"{BASE}/auto-sales/run", json={"region": REGION, "model": MODEL})
    assert response.status_code == 200, response.text
    return response.json()


async def test_auto_sales_run_uses_real_trained_model(client: AsyncClient, auto_sales_funnel: None) -> None:
    body = await _run(client)

    assert uuid.UUID(body["run_id"]).version == 4
    assert body["status"] == "PROPOSED"
    assert body["confidence_basis"] == "calibrated_heuristic"
    assert 0 <= body["conf"] <= 70  # calibrated-heuristic ceiling, never a fake 88%
    assert isinstance(body["uplift"], int)
    assert isinstance(body["rev"], int)
    assert REGION in body["recommendedAction"]
    assert MODEL in body["recommendedAction"]


async def test_auto_sales_baseline_reference_uses_real_cohort_stats(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = (await _run(client))["run_id"]

    detail = (await client.get(f"{BASE}/{run_id}")).json()

    baseline = detail["baseline_reference"]
    assert baseline["cohort_lead_count"] == LEAD_COUNT
    assert baseline["avg_booking_value_inr"] > 0
    assert 0 <= baseline["baseline_conversion_probability"] <= 1
    assert 0 <= baseline["baseline_cancellation_probability"] <= 1


async def test_auto_sales_drivers_separate_predictive_from_causal(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = (await _run(client))["run_id"]

    drivers = (await client.get(f"{BASE}/{run_id}/drivers")).json()

    assert drivers["domain"] == "auto-sales"
    assert len(drivers["predictive_drivers"]) >= 4
    sources = {item["source"] for item in drivers["predictive_drivers"]}
    assert sources <= {"trained_model", "calibrated_heuristic"}
    assert "trained_model" in sources
    assert "calibrated_heuristic" in sources
    # Causal evidence is a genuinely separate list, never mislabelled feature importance.
    assert isinstance(drivers["causal_evidence"], list)
    assert drivers["causal_evidence_note"]


async def test_auto_sales_summary_reflects_the_actual_run(client: AsyncClient, auto_sales_funnel: None) -> None:
    body = await _run(client)

    summary = (await client.post(f"{BASE}/{body['run_id']}/summary")).json()

    assert REGION in summary["scenario"]
    assert MODEL in summary["scenario"]
    assert str(body["uplift"]) in summary["predicted_outcome"]
    assert summary["recommendation"] == body["recommendedAction"]
    assert summary["major_drivers"]


async def test_auto_sales_insufficient_data_returns_clear_error(client: AsyncClient) -> None:
    """No funnel fixture applied — the leads/bookings tables are empty."""
    response = await client.post(f"{BASE}/auto-sales/run", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_training_data"
