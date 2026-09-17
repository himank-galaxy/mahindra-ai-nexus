"""Write API tests: dealer coach, pitch and lead actions."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _first_lead(client: AsyncClient, dealer_code: str = "d1") -> dict:
    leads = (await client.get(f"/api/v1/dealers/{dealer_code}/leads")).json()
    assert leads, "seed must provide dealer leads"
    return leads[0]


async def test_message_lead_marks_whatsapp_sent(client: AsyncClient) -> None:
    lead = await _first_lead(client)
    resp = await client.post(f"/api/v1/dealer-leads/{lead['id']}/message")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Message Sent"

    # Persisted on reload.
    leads = (await client.get("/api/v1/dealers/d1/leads")).json()
    assert next(row for row in leads if row["id"] == lead["id"])["status"] == "Message Sent"


async def test_schedule_test_drive_books_slot(client: AsyncClient) -> None:
    lead = await _first_lead(client)
    resp = await client.post(f"/api/v1/dealer-leads/{lead['id']}/test-drive", json={"slot": "Sat 11:00"})
    assert resp.status_code == 200
    assert resp.json()["name"] == lead["name"]


async def test_convert_lead_marks_converted(client: AsyncClient) -> None:
    lead = await _first_lead(client)
    resp = await client.post(f"/api/v1/dealer-leads/{lead['id']}/convert")
    assert resp.status_code == 200
    assert resp.json()["status"] == "Converted"


async def test_generate_pitch_uses_lead_name(client: AsyncClient) -> None:
    lead = await _first_lead(client)
    resp = await client.post(f"/api/v1/dealers/d1/leads/{lead['id']}/pitch")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == lead["name"]
    assert body["text"].startswith(f"Hi {lead['name']}, based on your interest and profile")
    assert "₹25,000 exchange bonus" in body["text"]


async def test_pitch_for_wrong_dealer_returns_404(client: AsyncClient) -> None:
    lead = await _first_lead(client, "d1")
    resp = await client.post(f"/api/v1/dealers/d2/leads/{lead['id']}/pitch")
    assert resp.status_code == 404
    assert resp.json()["code"] == "lead_not_found"


async def test_dealer_coach_panel_content(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/dealers/d1/coach")
    assert resp.status_code == 200
    body = resp.json()
    assert body["topAction"].startswith("Call Rakesh Patil")
    assert body["expected"] == "+₹19.8L expected · 74% probability"
    assert body["bestOffer"] == "XUV700 exchange bonus + finance pre-approval"
    assert body["bestTime"] == "Weekdays 6–8 PM, Sat 11 AM–1 PM"
    assert body["risk"].startswith("Potential ₹42L revenue leakage")


async def test_coach_missing_dealer_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/dealers/d999/coach")
    assert resp.status_code == 404
    assert resp.json()["code"] == "dealer_not_found"


async def test_lead_actions_missing_lead_return_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    for path in ("message", "convert"):
        resp = await client.post(f"/api/v1/dealer-leads/{missing}/{path}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "lead_not_found"
