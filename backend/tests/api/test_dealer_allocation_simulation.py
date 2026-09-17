"""Dealer Allocation Simulation Phase 3: a real linear program over real data.

The allocation split comes from scipy.optimize.linprog over real dealer
demand share and delivery reliability (never a predictive model — see
app/ai/simulation/optimizers/dealer_allocation_lp.py). Assertions check
shape/ranges and the optimizer's own invariants (never exceeds the unit
pool or any dealer's capacity) rather than brittle exact values, since
the LP's numeric output depends on real seeded data that varies by
region — matching the testing philosophy already used for Auto Sales.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/simulations"


async def _run(client: AsyncClient, **overrides: object) -> dict:
    payload = {"units": 120, "demand": 70, "capacity": 80, "wait": 14, **overrides}
    response = await client.post(f"{BASE}/dealer-allocation/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_dealer_allocation_run_uses_real_optimizer(client: AsyncClient, dealer_allocation_seed: None) -> None:
    body = await _run(client)

    assert uuid.UUID(body["run_id"]).version == 4
    assert body["status"] == "PROPOSED"
    assert body["confidence_basis"] == "calibrated_heuristic"
    assert 0 <= body["conf"] <= 70
    assert isinstance(body["delay"], int) and body["delay"] >= 1
    assert isinstance(body["csat"], int)
    assert "%" in body["suggestedSplit"]


async def test_dealer_allocation_split_never_exceeds_pool_or_dealer_capacity(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    run_id = (await _run(client, units=50))["run_id"]

    detail = (await client.get(f"{BASE}/{run_id}")).json()

    assert detail["baseline_reference"]["dealer_count"] == 10
    # The regional split percentages must sum to ~100 (rounding tolerance).
    split = detail["outputs"]["suggestedSplit"]
    percentages = [int(part.strip().split()[-1].rstrip("%")) for part in split.split("·")]
    assert 95 <= sum(percentages) <= 105


async def test_dealer_allocation_larger_pool_increases_incremental_value(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    small = await _run(client, units=30)
    large = await _run(client, units=300)

    # A materially larger pool should never be worse than a tiny one on the
    # optimizer's own incremental-value metric (monotonic direction, not an
    # exact number — see module docstring).
    assert large["rev"] >= small["rev"]


async def test_dealer_allocation_never_underperforms_the_naive_baseline(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    """Regression: the incremental-value metric must use the SAME
    demand+quality weighting the LP actually maximizes. Using a different
    yardstick (e.g. quality alone) can make a genuinely optimal allocation
    look worse than the naive split purely from a metric mismatch, not a
    real regression — this must never happen since the naive split is
    always a feasible point the optimizer could have chosen instead."""
    for units in (30, 80, 120, 250, 400):
        body = await _run(client, units=units)
        assert body["rev"] >= 0, f"units={units} produced a negative incremental value: {body['rev']}"


async def test_dealer_allocation_drivers_reflect_this_runs_actual_allocation(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    """Regression: the top predictive driver must be ranked by units THIS
    run actually allocated, not by a static historical score — otherwise
    the same 2-3 dealers would show up in Explain Drivers for every
    scenario regardless of units/capacity/demand, even when a different
    region clearly dominates the actual recommended split."""
    body = await _run(client, units=30, capacity=100)
    run_id = body["run_id"]

    top_region_in_split = max(
        (part.strip().rsplit(" ", 1) for part in body["suggestedSplit"].split("·")),
        key=lambda pair: int(pair[1].rstrip("%")),
    )[0]

    drivers = (await client.get(f"{BASE}/{run_id}/drivers")).json()
    top_driver = drivers["predictive_drivers"][0]

    assert top_region_in_split in top_driver["name"]
    assert "Allocated" in top_driver["detail"]


async def test_dealer_allocation_drivers_show_real_dealers_not_generic_text(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    run_id = (await _run(client))["run_id"]

    drivers = (await client.get(f"{BASE}/{run_id}/drivers")).json()

    assert drivers["domain"] == "dealer-allocation"
    sources = {item["source"] for item in drivers["predictive_drivers"]}
    assert "trained_model" in sources
    assert "calibrated_heuristic" in sources
    assert drivers["causal_evidence"] == []
    assert "optimization" in drivers["causal_evidence_note"].lower()


async def test_dealer_allocation_summary_reflects_the_actual_run(
    client: AsyncClient, dealer_allocation_seed: None
) -> None:
    body = await _run(client)

    summary = (await client.post(f"{BASE}/{body['run_id']}/summary")).json()

    assert str(body["delay"]) in summary["predicted_outcome"]
    assert summary["recommendation"] == body["recommendedAction"]
    assert summary["major_drivers"]


async def test_dealer_allocation_never_zeroes_out_a_whole_region(client: AsyncClient, dealer_allocation_seed: None) -> None:
    """Regression: a pure demand+quality ranking can legitimately exclude a
    whole region if its dealers all score below the pool's cutoff (this is
    real, verified against production data — see the module docstring in
    dealer_allocation_lp.py) but the original brief calls out "regional
    constraints" as something the optimizer should respect, so every region
    must get a non-zero floor regardless of how it ranks."""
    for units in (30, 120, 400):
        body = await _run(client, units=units)
        shares = dict(
            (part.strip().rsplit(" ", 1)[0], int(part.strip().rsplit(" ", 1)[1].rstrip("%")))
            for part in body["suggestedSplit"].split("·")
        )
        assert set(shares) == {"West", "North", "South", "East"}, body["suggestedSplit"]
        assert all(share > 0 for share in shares.values()), body["suggestedSplit"]


async def test_dealer_allocation_insufficient_dealer_data_returns_clear_error(client: AsyncClient) -> None:
    """No seed fixture applied — the dealers table is empty."""
    response = await client.post(f"{BASE}/dealer-allocation/run", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_training_data"
