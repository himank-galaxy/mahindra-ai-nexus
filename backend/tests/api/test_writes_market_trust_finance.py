"""Write API tests: circularity credits, trust decisions and finance approvals."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient

CREDIT_CODE = seed_data.CARBON_CREDITS[0]["code"]
DECISION_CODE = seed_data.TRUST_DECISIONS[0]["code"]


async def test_reprice_credit_returns_updated_row(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/circularity/credits/{CREDIT_CODE}/reprice")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == CREDIT_CODE
    assert body["price"] == seed_data.CARBON_CREDITS[0]["price"]


async def test_match_buyer_sets_full_match(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/circularity/credits/{CREDIT_CODE}/match-buyer")
    assert resp.status_code == 200
    assert resp.json()["match"] == 100


async def test_credit_actions_missing_credit_return_404(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/circularity/credits/CR-0000/reprice")
    assert resp.status_code == 404
    assert resp.json()["code"] == "credit_not_found"


async def test_trust_approve_updates_approval_label(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/trust/decisions/{DECISION_CODE}/approve")
    assert resp.status_code == 200
    assert resp.json()["approval"] == "Approved"

    # Persisted across reload.
    rows = (await client.get("/api/v1/trust/decisions")).json()
    assert next(row for row in rows if row["id"] == DECISION_CODE)["approval"] == "Approved"


async def test_trust_reject_records_reason(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/trust/decisions/{DECISION_CODE}/reject",
        json={"reason": "Insufficient causal evidence"},
    )
    assert resp.status_code == 200
    assert resp.json()["approval"] == "Rejected"


async def test_trust_escalate_marks_escalated(client: AsyncClient) -> None:
    resp = await client.post(f"/api/v1/trust/decisions/{DECISION_CODE}/escalate")
    assert resp.status_code == 200
    assert resp.json()["approval"] == "Escalated"


async def test_trust_actions_missing_decision_return_404(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/trust/decisions/AUTO-0000/approve")
    assert resp.status_code == 404
    assert resp.json()["code"] == "decision_not_found"


async def test_submit_twin_approval_transitions_to_under_review(client: AsyncClient) -> None:
    twins = (await client.get("/api/v1/finance/twins")).json()
    assert twins, "seed must provide customer twins"
    twin_id = twins[0]["id"]

    resp = await client.post(f"/api/v1/finance/twins/{twin_id}/submit-approval")
    assert resp.status_code == 200
    assert resp.json()["approval_status"] == "Under Review"

    # Second submission is a conflict.
    again = await client.post(f"/api/v1/finance/twins/{twin_id}/submit-approval")
    assert again.status_code == 409
    assert again.json()["code"] == "approval_already_submitted"
