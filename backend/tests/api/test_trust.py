"""Read API tests: Compliance Trust Ledger."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient

APPROVAL_DISPLAY = {
    "approved": "Approved",
    "human_review": "Human Review",
    "pending": "Pending",
    "rejected": "Rejected",
    "escalated": "Escalated",
}


async def test_decisions_match_seed_with_display_labels(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trust/decisions")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.TRUST_DECISIONS)

    first, expected = body[0], seed_data.TRUST_DECISIONS[0]
    assert first["id"] == expected["code"]
    assert first["use"] == expected["use_case"]
    assert first["rec"] == expected["recommendation"]
    assert first["data"] == expected["data_sources"]
    assert first["conf"] == expected["confidence"]
    assert first["approval"] == APPROVAL_DISPLAY[expected["approval"]]
    assert first["risk"] == expected["risk"].capitalize()
    expected_audit = "Complete" if expected["audit"] == "complete" else "Pending"
    assert first["audit"] == expected_audit


async def test_compliance_rules_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trust/compliance-rules")

    assert response.status_code == 200
    assert response.json() == seed_data.COMPLIANCE_RULES


async def test_lineage_has_six_steps(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trust/decisions/AUTO-1042/lineage")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    assert [step["step"] for step in body] == [1, 2, 3, 4, 5, 6]
    assert all(step["title"] for step in body)
    assert body[0]["detail"]


async def test_unknown_decision_lineage_returns_structured_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/trust/decisions/NOPE-0000/lineage")

    assert response.status_code == 404
    assert response.json()["code"] == "decision_not_found"
