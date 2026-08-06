"""Parity tests for the five simulation engines.

Expected values are hand-computed from the ``simulation.tsx`` formulas with
JS ``Math.round`` semantics so the Python ports are provably identical.
"""

from __future__ import annotations

from httpx import AsyncClient

BASE = "/api/v1/simulations"


async def test_auto_sales_default_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/auto-sales/run", json={})

    assert response.status_code == 200
    assert response.json() == {
        "uplift": 16,
        "margin": -4,
        "cancel": 4,
        "rev": 44,
        "conf": 88,
        "recommendedAction": ("Deploy exchange bonus ₹25,000 in West for XUV700 with medium follow-up."),
    }


async def test_auto_sales_variant_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/auto-sales/run",
        json={
            "region": "North",
            "model": "Scorpio N",
            "discount": 3.5,
            "bonus": 50000,
            "campaign": 2.0,
            "intensity": "High",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uplift"] == 26
    assert body["margin"] == -4
    assert body["cancel"] == 3
    assert body["rev"] == 76
    assert body["conf"] == 88
    assert body["recommendedAction"] == ("Deploy exchange bonus ₹50,000 in North for Scorpio N with high follow-up.")


async def test_dealer_allocation_default_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/dealer-allocation/run", json={})

    assert response.status_code == 200
    assert response.json() == {
        "delay": 6,
        "rev": 1512,
        "csat": 86,
        "suggestedSplit": "West 45% · North 30% · South 25%",
    }


async def test_dealer_allocation_delay_floor_is_one_day(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/dealer-allocation/run",
        json={"units": 400, "demand": 20, "capacity": 100, "wait": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delay"] == 1
    assert body["rev"] == 1440
    assert body["csat"] == 90


async def test_collections_default_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/collections/run", json={})

    assert response.status_code == 200
    assert response.json() == {"prob": 68, "cost": 90, "friction": 12, "net": 2856}


async def test_collections_field_settlement_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/collections/run",
        json={"risk": "High", "channel": "Field", "offer": "Settlement", "field": 40},
    )

    assert response.status_code == 200
    assert response.json() == {"prob": 42, "cost": 1520, "friction": 62, "net": 1235}


async def test_logistics_delay_default_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/logistics-delay/run", json={})

    assert response.status_code == 200
    assert response.json() == {
        "delay": 32,
        "breach": 49,
        "reroute": "Via Panvel bypass",
        "cost": 28800,
    }


async def test_logistics_delay_medium_sla_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/logistics-delay/run",
        json={"warehouse": 100, "vehicle": 20, "weather": 60, "sla": "Medium"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["delay"] == 70
    assert body["breach"] == 33
    assert body["cost"] == 60800


async def test_credit_pricing_default_matches_frontend(client: AsyncClient) -> None:
    response = await client.post(f"{BASE}/credit-pricing/run", json={})

    assert response.status_code == 200
    assert response.json() == {
        "priceBandLow": 1810,
        "priceBandHigh": 1930,
        "closure": 68,
        "match": 83,
        "complianceRisk": "Medium",
    }


async def test_credit_pricing_compliance_risk_thresholds(client: AsyncClient) -> None:
    high = await client.post(f"{BASE}/credit-pricing/run", json={"verif": 30})
    low = await client.post(f"{BASE}/credit-pricing/run", json={"verif": 80})

    assert high.json()["complianceRisk"] == "High"
    assert low.json()["complianceRisk"] == "Low"


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
