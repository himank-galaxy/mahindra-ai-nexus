"""Circularity Credit Pricing Simulation Phase 6: real regressions + calibrated closure sweep.

Ask-price and buyer-interest come from two OLS regressions trained on
real historical listing/assessment data (never a formula) — see
app/ai/simulation/credit_pricing.py. Credit type is the exact real
recorded category (MIXED_CIRCULARITY/RECYCLING_AVOIDANCE/REUSE_AVOIDANCE),
so this domain has no UI-to-real translation layer. Trade-closure
probability stays a documented calibrated function because
`listing_status` is OPEN for every real listing — no closed/not-closed
outcome exists to train a classifier against — so `confidence_basis` is
always `calibrated_heuristic` for this domain, the same treatment Dealer
Allocation gives its CSAT/waiting-period layer.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/simulations"
CREDIT_TYPES = ("MIXED_CIRCULARITY", "RECYCLING_AVOIDANCE", "REUSE_AVOIDANCE")


async def _run(client: AsyncClient, **overrides: object) -> dict:
    payload = {"type": "REUSE_AVOIDANCE", "supply": 50, "demand": 60, "trace": 70, "verif": 65, **overrides}
    response = await client.post(f"{BASE}/credit-pricing/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_credit_pricing_run_uses_real_trained_models(client: AsyncClient, credit_pricing_seed: None) -> None:
    body = await _run(client)

    assert uuid.UUID(body["run_id"]).version == 4
    assert body["status"] == "PROPOSED"
    assert body["confidence_basis"] == "calibrated_heuristic"
    assert 0 <= body["conf"] <= 70
    assert body["priceBandLow"] < body["priceBandHigh"]
    assert 0 <= body["closure"] <= 100
    assert 0 <= body["match"] <= 100
    assert body["complianceRisk"] in {"Low", "Medium", "High"}


async def test_credit_pricing_every_real_credit_type_runs(client: AsyncClient, credit_pricing_seed: None) -> None:
    for credit_type in CREDIT_TYPES:
        body = await _run(client, type=credit_type)
        assert body["confidence_basis"] == "calibrated_heuristic", f"{credit_type} did not run"


async def test_credit_pricing_higher_ask_price_lowers_closure_probability(
    client: AsyncClient, credit_pricing_seed: None
) -> None:
    """Regression: the calibrated closure function must genuinely respond
    to demand/supply pressure — otherwise the sliders would be decorative,
    the exact bug already fixed once for Auto Sales' uplift figure and
    Logistics Delay's breach probability."""
    weak_demand = await _run(client, demand=15, supply=95)
    strong_demand = await _run(client, demand=95, supply=15)

    assert strong_demand["closure"] > weak_demand["closure"]


async def test_credit_pricing_never_recommends_the_top_of_the_band_by_default(
    client: AsyncClient, credit_pricing_seed: None
) -> None:
    """Regression: the pricing optimizer must trade off price against
    closure probability (price x closure), never simply pick the highest
    price the band allows — the doc's explicit non-negotiable for this
    domain."""
    body = await _run(client)
    detail = (await client.get(f"{BASE}/{body['run_id']}")).json()

    # priceBandLow/High are rounded for display; allow a 1-rupee tolerance
    # against the unrounded recommended price for edge-of-band cases.
    recommended_price = detail["recommendation_json"]["recommended_price_inr"]
    assert body["priceBandLow"] - 1 <= recommended_price <= body["priceBandHigh"] + 1


async def test_credit_pricing_drivers_show_credit_type_and_closure_for_this_run(
    client: AsyncClient, credit_pricing_seed: None
) -> None:
    body = await _run(client, type="MIXED_CIRCULARITY")

    drivers = (await client.get(f"{BASE}/{body['run_id']}/drivers")).json()

    names = [item["name"] for item in drivers["predictive_drivers"]]
    assert any("Mixed Circularity" in name for name in names)
    assert any("closure" in name.lower() for name in names)
    assert drivers["causal_evidence"] == []
    sources = {item["source"] for item in drivers["predictive_drivers"]}
    assert "trained_model" in sources
    assert "calibrated_heuristic" in sources


async def test_credit_pricing_summary_reflects_the_actual_run(client: AsyncClient, credit_pricing_seed: None) -> None:
    body = await _run(client)

    summary = (await client.post(f"{BASE}/{body['run_id']}/summary")).json()

    assert str(body["closure"]) in summary["predicted_outcome"]
    assert summary["recommendation"] == body["recommendedAction"]
    assert summary["major_drivers"]


async def test_credit_pricing_insufficient_data_returns_clear_error(client: AsyncClient) -> None:
    """No seed fixture applied — the credit_listings table is empty."""
    response = await client.post(f"{BASE}/credit-pricing/run", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_training_data"
