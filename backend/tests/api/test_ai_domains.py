"""Parity tests for the domain AI endpoints (mobility, dMRV, ELV, finance, workflow)."""

from __future__ import annotations

from httpx import AsyncClient

MISSING_TWIN = "00000000-0000-0000-0000-000000000000"


async def _first_twin_id(client: AsyncClient) -> str:
    response = await client.get("/api/v1/finance/twins")
    assert response.status_code == 200
    return response.json()[0]["id"]


async def test_mobility_ask_known_question(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/mobility-twin/ask",
        json={"question": "Why did bookings drop in Pune?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "Why did bookings drop in Pune?"
    assert body["answer"] == (
        "Bookings dropped due to follow-up leakage at 2 Pune dealers (47%), competitor promo "
        "(28%), finance TAT (15%). Recommend: exchange bonus + follow-up SLA."
    )


async def test_mobility_ask_is_case_insensitive(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/mobility-twin/ask",
        json={"question": "  which factor has highest impact on cancellation?  "},
    )

    assert response.status_code == 200
    assert response.json()["answer"].startswith("Finance approval TAT (>4 days)")


async def test_mobility_ask_unknown_question_falls_back(client: AsyncClient) -> None:
    response = await client.post("/api/v1/mobility-twin/ask", json={"question": "Tell me a joke"})

    assert response.status_code == 200
    assert response.json()["answer"].startswith("The causal twin currently answers")


async def test_dmrv_prompts_and_ask_roundtrip(client: AsyncClient) -> None:
    prompts = await client.get("/api/v1/circularity/dmrv/prompts")
    assert prompts.status_code == 200
    questions = prompts.json()
    assert "Estimate carbon credits for this batch." in questions

    response = await client.post(
        "/api/v1/circularity/dmrv/ask",
        json={"question": questions[0]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] != ""
    assert body["answer"].startswith("The dMRV copilot") is False


async def test_dmrv_ask_unknown_question_falls_back(client: AsyncClient) -> None:
    response = await client.post("/api/v1/circularity/dmrv/ask", json={"question": "anything else?"})

    assert response.status_code == 200
    assert response.json()["answer"].startswith("The dMRV copilot currently answers")


async def test_elv_estimate_defaults_match_frontend(client: AsyncClient) -> None:
    response = await client.post("/api/v1/circularity/elv/estimate", json={})

    assert response.status_code == 200
    assert response.json() == {"price": 65000, "recoverable": 45500, "risks": ["OK"]}


async def test_elv_estimate_low_docs_raises_risk_flags(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/circularity/elv/estimate",
        json={"vehicleType": "Pickup", "age": 12, "condition": 60, "docs": 40},
    )

    assert response.status_code == 200
    assert response.json() == {
        "price": 60200,
        "recoverable": 42140,
        "risks": ["Incomplete RC", "Missing insurance papers"],
    }


async def test_finance_explain_rm_script_and_offer(client: AsyncClient) -> None:
    twin_id = await _first_twin_id(client)

    explain = await client.post(f"/api/v1/finance/twins/{twin_id}/explain")
    assert explain.status_code == 200
    assert explain.json()["bullets"] == [
        "Repayment track record on tractor loan (36 EMIs paid on-time)",
        "Agri-cycle signal indicates stable cash-flow next 6 months",
        "Peer benchmarking in Sangli shows +18% growth in SME activity",
        "Insurance renewal + FD balance indicate low credit stress",
    ]

    script = await client.post(f"/api/v1/finance/twins/{twin_id}/rm-script")
    assert script.status_code == 200
    assert script.json()["script"].startswith("Namaste Suresh-ji, based on your excellent")
    assert script.json()["script"].endswith("Shall I share the digital application link?")

    offer = await client.post(
        f"/api/v1/finance/twins/{twin_id}/simulate-offer",
        json={"amount": 450000},
    )
    assert offer.status_code == 200
    assert offer.json() == {"amount": 450000, "emi": 15200, "risk": "Low"}


async def test_finance_simulate_offer_small_amount(client: AsyncClient) -> None:
    twin_id = await _first_twin_id(client)

    response = await client.post(
        f"/api/v1/finance/twins/{twin_id}/simulate-offer",
        json={"amount": 100000},
    )

    assert response.status_code == 200
    assert response.json()["emi"] == 3378


async def test_finance_ai_endpoints_require_existing_twin(client: AsyncClient) -> None:
    for path in ("explain", "rm-script"):
        response = await client.post(f"/api/v1/finance/twins/{MISSING_TWIN}/{path}")
        assert response.status_code == 404
        assert response.json()["code"] == "twin_not_found"


async def test_finance_simulate_offer_rejects_out_of_range_amount(client: AsyncClient) -> None:
    twin_id = await _first_twin_id(client)

    response = await client.post(
        f"/api/v1/finance/twins/{twin_id}/simulate-offer",
        json={"amount": 500},
    )

    assert response.status_code == 422


async def test_agent_workflow_returns_staged_flow(client: AsyncClient) -> None:
    response = await client.post("/api/v1/agents/workflow/run")

    assert response.status_code == 200
    body = response.json()
    assert body["intervalMs"] == 700
    assert [stage["stage"] for stage in body["stages"]] == [
        "Data Agent",
        "Prediction Agent",
        "Causal Agent",
        "Simulation Agent",
        "Compliance Agent",
        "Human Review",
        "Action Agent",
        "Learning Agent",
    ]
    assert body["stages"][0]["message"] == "Fetching data"
    assert body["stages"][-1]["message"] == "Feedback captured"
