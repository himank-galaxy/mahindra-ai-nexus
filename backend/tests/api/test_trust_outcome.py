"""Compliance Trust Ledger: outcome tracking for canonical decisions.

`GET /trust/decisions/{code}/outcome` surfaces the real
``action_outcomes``/``recommendations.expected_impact`` data already
sitting unused in the runtime schema — never a fabricated value. No
expected-vs-observed variance is computed (that field doesn't exist in
the schema yet); this is intentionally out of scope for this phase.

Simulation Center runs have no execution/outcome mechanism at all, so
they are always honestly ``PENDING`` with no expected impact — covered
by a single smoke test here (the canonical-track states are the real
subject of this file).
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import (
    CANONICAL_OUTCOME_EMPTY_DECISION_ID,
    CANONICAL_OUTCOME_OBSERVED_2_DECISION_ID,
    CANONICAL_OUTCOME_OBSERVED_DECISION_ID,
    CANONICAL_OUTCOME_PENDING_DECISION_ID,
)

TRUST_BASE = "/api/v1/trust"
SIM_BASE = "/api/v1/simulations"


async def test_canonical_decision_with_observed_outcome(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """1. Canonical decision with an existing outcome."""
    response = await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/outcome")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome_status"] == "OBSERVED"
    assert body["observed_outcome_value"] == "EXECUTED"
    assert body["business_outcome_observed"] is True
    assert body["business_outcome_note"] == "Customer honored the revised payment plan."
    assert body["observed_at"] is not None
    assert body["expected_impact"] == {"metric": "recovery_probability", "direction": "IMPROVE", "value": 0.15}


async def test_canonical_decision_with_expected_impact_but_no_observed_outcome(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """2. Canonical decision with expected impact but no observed outcome."""
    response = await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_PENDING_DECISION_ID}/outcome")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome_status"] == "PENDING"
    assert body["expected_impact"] == {"metric": "recovery_probability", "direction": "IMPROVE", "value": 0.09}
    assert body["observed_outcome_type"] is None
    assert body["observed_outcome_value"] is None
    assert body["observed_at"] is None
    assert body["business_outcome_observed"] is None
    assert body["business_outcome_note"] is None


async def test_canonical_decision_with_no_outcome_data_at_all(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """3. Canonical decision with no outcome data (recommendation itself
    unresolvable — a defensive edge case) must degrade to a clean,
    entirely empty pending state, never a fabricated expected_impact."""
    response = await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_EMPTY_DECISION_ID}/outcome")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome_status"] == "PENDING"
    assert body["expected_impact"] is None
    assert body["observed_outcome_type"] is None
    assert body["observed_outcome_value"] is None
    assert body["observed_at"] is None
    assert body["business_outcome_observed"] is None
    assert body["business_outcome_note"] is None


async def test_outcome_is_linked_to_the_correct_decision(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """4. Correct decision-to-outcome linkage: two decisions each with
    their own observed outcome must never cross-contaminate."""
    first = (await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/outcome")).json()
    second = (await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_2_DECISION_ID}/outcome")).json()

    assert first["observed_outcome_value"] == "EXECUTED"
    assert first["business_outcome_observed"] is True
    assert first["expected_impact"]["value"] == 0.15

    assert second["observed_outcome_value"] == "FAILED"
    assert second["business_outcome_observed"] is False
    assert second["expected_impact"]["value"] == 0.22


async def test_no_fabricated_fallback_values_for_pending_outcome(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """5. No fabricated fallback values: a PENDING outcome must never
    invent placeholder text like "N/A" or a made-up observed_at."""
    body = (await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_PENDING_DECISION_ID}/outcome")).json()

    assert body["observed_outcome_type"] is None
    assert body["observed_outcome_value"] is None
    assert body["observed_at"] is None
    for value in body.values():
        assert value not in ("N/A", "TBD", "Unknown", "n/a")


async def test_canonical_decision_remains_immutable_with_outcome_endpoint_present(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """6. Canonical decisions remain immutable: adding the outcome
    endpoint must not open any new mutation path — approve/reject/
    escalate on a real seeded canonical decision still refuse."""
    approve = await client.post(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/approve")
    reject = await client.post(
        f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/reject", json={"reason": "test"}
    )
    escalate = await client.post(
        f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/escalate",
        json={"reviewer_role": "Risk Reviewer", "reason": "test"},
    )

    for response in (approve, reject, escalate):
        assert response.status_code == 422
        assert response.json()["code"] == "immutable_trust_decision"

    # And the outcome data itself is unchanged by the refused attempts.
    outcome = (await client.get(f"{TRUST_BASE}/decisions/{CANONICAL_OUTCOME_OBSERVED_DECISION_ID}/outcome")).json()
    assert outcome["outcome_status"] == "OBSERVED"
    assert outcome["observed_outcome_value"] == "EXECUTED"


async def test_simulation_run_outcome_is_honestly_pending(client: AsyncClient, auto_sales_funnel: None) -> None:
    """Simulation Center runs have no execution/outcome mechanism yet —
    always a genuine PENDING, never a fabricated observed outcome."""
    run = (await client.post(f"{SIM_BASE}/auto-sales/run", json={})).json()
    code = f"SIM_{run['run_id'].replace('-', '')}"

    body = (await client.get(f"{TRUST_BASE}/decisions/{code}/outcome")).json()

    assert body["outcome_status"] == "PENDING"
    assert body["expected_impact"] is None
    assert body["observed_outcome_value"] is None


async def test_unknown_canonical_decision_outcome_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{TRUST_BASE}/decisions/DEC_DOES_NOT_EXIST/outcome")

    assert response.status_code == 404


async def test_execution_eligible_card_always_carries_a_real_reason(
    client: AsyncClient, canonical_trust_outcome_seed: None
) -> None:
    """The 'Execution eligible' card must never be a bare Yes/Blocked
    pill — an approved decision explains why it's eligible, and a
    rejected one explains why it's blocked."""
    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
    by_id = {d["id"]: d for d in decisions}

    approved = by_id[CANONICAL_OUTCOME_OBSERVED_DECISION_ID]
    rejected = by_id[CANONICAL_OUTCOME_EMPTY_DECISION_ID]

    assert approved["execution_eligible"] is True
    assert approved["execution_eligible_reason"]
    assert "approved" in approved["execution_eligible_reason"].lower()

    assert rejected["execution_eligible"] is False
    assert rejected["execution_eligible_reason"]
    assert "rejected" in rejected["execution_eligible_reason"].lower()
