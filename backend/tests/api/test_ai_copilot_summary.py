"""Parity tests for the copilot rule engine and executive summary template.

Expected payloads reproduce ``copilot.ts`` exactly (answers, SQL, Python,
charts, tables, confidences).
"""

from __future__ import annotations

from httpx import AsyncClient

CHAT = "/api/v1/copilot/chat"


async def test_chat_bookings_pune_intent(client: AsyncClient) -> None:
    response = await client.post(CHAT, json={"message": "Why did bookings drop in Pune?"})

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 89
    assert body["answer"].startswith("Bookings in Pune dropped 12.4% week-on-week")
    assert "WHERE region = 'West' AND city = 'Pune'" in body["sql"]
    assert "\n" in body["sql"]
    assert body["chart"] == [
        {"label": "Follow-up", "value": 47},
        {"label": "Competitor", "value": 28},
        {"label": "Finance TAT", "value": 15},
        {"label": "Walk-ins", "value": 10},
    ]
    assert "table" not in body  # optional fields omitted, mirroring TS `chart?`
    assert body["action"].startswith("Launch exchange-bonus campaign")


async def test_chat_dealer_leakage_intent_returns_table(client: AsyncClient) -> None:
    response = await client.post(CHAT, json={"message": "Which dealers leak the most revenue?"})

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 92
    assert "chart" not in body
    assert body["table"]["headers"] == ["Dealer", "Leakage", "Revenue at Risk"]
    assert body["table"]["rows"][0] == ["Lucknow Motors", "21%", "₹0.7 Cr"]


async def test_chat_intent_precedence_matches_ts_if_chain(client: AsyncClient) -> None:
    # Contains both booking+pune and dealer keywords; TS checks bookings first.
    response = await client.post(CHAT, json={"message": "dealer follow-up and bookings in pune"})

    assert response.status_code == 200
    assert response.json()["confidence"] == 89


async def test_chat_remaining_intents_route_correctly(client: AsyncClient) -> None:
    cases = {
        "what is the roll forward risk": 87,
        "which routes breach SLA": 85,
        "how do we price carbon credits": 81,
        "explain the warranty spike": 90,
        "summarise ROI for the board": 93,
    }
    for message, confidence in cases.items():
        response = await client.post(CHAT, json={"message": message})
        assert response.status_code == 200, message
        assert response.json()["confidence"] == confidence, message


async def test_chat_unknown_prompt_falls_back(client: AsyncClient) -> None:
    response = await client.post(CHAT, json={"message": "hello there"})

    assert response.status_code == 200
    body = response.json()
    assert body["confidence"] == 70
    assert body["sql"] == "-- Ask a specific question to generate a query"
    assert "chart" not in body and "table" not in body


async def test_chat_requires_message(client: AsyncClient) -> None:
    response = await client.post(CHAT, json={"message": ""})

    assert response.status_code == 422


async def test_executive_summary_matches_template(client: AsyncClient) -> None:
    response = await client.post("/api/v1/executive-summary", json={"useCase": "Auto Sales Simulation"})

    assert response.status_code == 200
    assert response.json() == {
        "problem": (
            "Auto Sales Simulation today relies on fragmented data, reactive workflows and "
            "limited causal understanding."
        ),
        "solution": (
            "Deploy the Auto Sales Simulation AI module of the Mahindra AI Command Center — "
            "predict, explain, simulate, act and learn in a closed loop."
        ),
        "diff": (
            "Causal AI + multi-agent orchestration + human-in-the-loop guardrails + trust ledger for every decision."
        ),
        "impact": (
            "Estimated 6-month impact: 7-12% revenue uplift or cost reduction in the target "
            "function, with audit-ready governance."
        ),
        "data": (
            "Operational transactions, customer signals, telemetry, compliance events, and dealer / partner feeds."
        ),
        "scope": ("3 use-cases, 1 business unit, 2 regions, closed-loop with human approval on high-risk actions."),
        "timeline": "Discovery 2 weeks → Prototype 4 weeks → PoC 8 weeks → Pilot 12 weeks.",
        "risks": "Data readiness, change management, integration cadence with source systems.",
        "next": "Approve PoC roadmap and align a joint sponsor + squad from Mahindra + partner team.",
    }
