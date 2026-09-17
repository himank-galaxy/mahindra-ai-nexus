"""Domain-agnostic Simulation Center infra tests.

Formerly held frozen-formula parity tests for the engines that hadn't yet
moved to real models — Auto Sales (Phase 2), Dealer Allocation (Phase 3),
Collections (Phase 4), Logistics Delay (Phase 5), and finally Credit
Pricing (Phase 6) — see tests/api/test_auto_sales_simulation.py,
tests/api/test_dealer_allocation_simulation.py,
tests/api/test_collections_simulation.py,
tests/api/test_logistics_delay_simulation.py, and
tests/api/test_credit_pricing_simulation.py for each domain's real tests.
What remains here is domain-agnostic: input validation and the generic
causal-drivers endpoint.
"""

from __future__ import annotations

from httpx import AsyncClient

BASE = "/api/v1/simulations"


async def test_simulation_inputs_outside_slider_ranges_are_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/auto-sales/run", json={"discount": 25})

    assert response.status_code == 422


async def test_causal_drivers_served_for_known_domain(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/causal-drivers", params={"domain": "logistics-delay"})

    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "logistics-delay"
    assert body["drivers"] == [
        "Historical elasticity (finance approval, exchange bonus)",
        "Regional propensity model output",
        "Dealer capacity + waiting-list dynamics",
        "Competitor promo signal",
        "Weather / calendar events",
    ]


async def test_causal_drivers_unknown_domain_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/causal-drivers", params={"domain": "warp-drive"})

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_simulation_domain"
