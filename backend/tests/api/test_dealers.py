"""Read API tests: Dealer Revenue Optimizer."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_dealers_match_seed_with_camel_case_aliases(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dealers")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.DEALERS)

    first, expected = body[0], seed_data.DEALERS[0]
    assert first["id"] == expected["code"]
    assert first["name"] == expected["name"]
    assert first["leads"] == expected["leads"]
    assert first["hotLeads"] == expected["hot_leads"]
    assert first["testDrivesPending"] == expected["test_drives_pending"]
    assert first["bookingProb"] == expected["booking_prob"]
    assert first["revenueAtRisk"] == expected["revenue_at_risk"]
    assert first["leakage"] == f"{expected['leakage_pct']}%"
    assert first["bayUtil"] == f"{expected['bay_util_pct']}%"


async def test_dealer_leads_match_seed_with_display_status(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dealers/d1/leads")

    assert response.status_code == 200
    body = response.json()
    d1_leads = [lead for lead in seed_data.DEALER_LEADS if lead["dealer"] == "d1"]
    assert len(body) == len(d1_leads)

    first, expected = body[0], d1_leads[0]
    assert first["name"] == expected["name"]
    assert first["vehicle"] == expected["vehicle"]
    assert first["score"] == expected["score"]
    assert first["prob"] == expected["prob"]
    assert first["action"] == expected["action"]
    assert first["revenue"] == expected["revenue"]
    assert first["status"] == expected["status"].capitalize()
    assert first["id"]  # UUID exposed for Phase 3 write endpoints


async def test_unknown_dealer_returns_structured_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/dealers/d999/leads")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "dealer_not_found"
    assert "request_id" in body
