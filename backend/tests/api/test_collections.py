"""Collections & Recovery AI Swarm: real database-backed case intelligence.

Exercises the real backend (services/collections.py) against the
``collections_seed`` fixture (real-shaped cases/interactions/loans with
genuine noise for the recovery/roll-forward models) plus one canonical
(Synthetic Data Factory-style) trust decision linked to a real seeded
case, so both governance tracks (canonical vs live) are covered.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.simulation.models import collections_model
from app.database.runtime_schema import runtime_tables
from app.repositories.collections_simulation import CHANNEL_DISPLAY_NAMES, OFFER_DISPLAY_NAMES

BASE = "/api/v1/collections"

# Deterministic (fixed rng seed in `collections_seed`) — always OPEN,
# current_dpd=91, current_arrears_inr=13650.0, secured/DSR/principal vary
# but are fixed per this seed.
CANONICAL_LINKED_CASE_ID = "seed-case-0"
CANONICAL_LINKED_DECISION_ID = "DEC_SEED_COLLECTIONS_CASE_0"

_RULE_CODES = [
    ("BUSINESS_POLICY_ALIGNMENT", "Business policy alignment"),
    ("LINEAGE_INTEGRITY", "Data lineage integrity"),
    ("EVIDENCE_SUFFICIENCY", "Evidence and explainability sufficiency"),
    ("FAIRNESS_INPUT_SCOPE", "Fairness input-scope check"),
    ("HUMAN_CONTROL_GATE", "Human-control risk gate"),
]


@pytest_asyncio.fixture
async def collections_canonical_link_seed(db_session: AsyncSession, collections_seed: None) -> None:
    """Link one real seeded OPEN case to a canonical (immutable)
    trust_decisions row, mirroring the real production shape where a
    subset of collection_cases already carry Synthetic Data Factory
    governance history."""
    recommendation_id = "REC_SEED_COLLECTIONS_CASE_0"
    recommendation = {
        "recommendation_id": recommendation_id,
        "domain": "COLLECTIONS",
        "use_case": "COLLECTIONS_RECOVERY",
        "target_entity_type": "COLLECTION_CASE",
        "target_entity_id": CANONICAL_LINKED_CASE_ID,
        "recommendation_type": "RECOMMEND_PAYMENT_PLAN",
        "generated_at": datetime(2026, 1, 5, tzinfo=UTC),
        "evidence_json": json.dumps({"dpd": 91, "outstanding_inr": 13650.0}),
        "expected_impact": json.dumps({"metric": "recovery_probability", "direction": "IMPROVE", "value": 0.12}),
        "confidence": 0.8,
        "risk_level": "MEDIUM",
        "status": "ACCEPTED",
        "data_origin": "TEST_SEED",
        "generator_version": "test",
    }
    decision = {
        "decision_id": CANONICAL_LINKED_DECISION_ID,
        "recommendation_id": recommendation_id,
        "domain": "COLLECTIONS",
        "use_case": "COLLECTIONS_RECOVERY",
        "target_entity_type": "COLLECTION_CASE",
        "target_entity_id": CANONICAL_LINKED_CASE_ID,
        "recommendation_type": "RECOMMEND_PAYMENT_PLAN",
        "recommendation_confidence": 0.8,
        "recommendation_risk_level": "MEDIUM",
        "decision_mode": "AUTOMATED_POLICY",
        "decision": "APPROVED",
        "decided_at": datetime(2026, 1, 5, 1, 0, tzinfo=UTC),
        "compliance_checks_count": 5,
        "compliance_pass_count": 5,
        "compliance_warn_count": 0,
        "compliance_fail_count": 0,
        "compliance_review_required_count": 0,
        "human_review_required": False,
        "human_review_id": None,
        "review_priority_score": 0.1,
        "decision_reason_code": "AUTO_APPROVED",
        "data_origin": "TEST_SEED",
        "generator_version": "test",
    }
    checks = [
        {
            "compliance_check_id": f"CHK_SEED_COLLECTIONS_CASE_0_{code}",
            "decision_id": CANONICAL_LINKED_DECISION_ID,
            "recommendation_id": recommendation_id,
            "domain": "COLLECTIONS",
            "rule_code": code,
            "rule_name": name,
            "checked_at": datetime(2026, 1, 5, 0, 30, tzinfo=UTC),
            "result": "PASS",
            "severity": "INFO",
            "reason": "Seeded canonical pass.",
            "evidence_json": json.dumps({}),
            "data_origin": "TEST_SEED",
            "generator_version": "test",
        }
        for code, name in _RULE_CODES
    ]
    await db_session.execute(runtime_tables["recommendations"].insert(), [recommendation])
    await db_session.execute(runtime_tables["trust_decisions"].insert(), [decision])
    await db_session.execute(runtime_tables["compliance_checks"].insert(), checks)
    await db_session.commit()


def _find(cases: list[dict], case_id: str) -> dict:
    return next(c for c in cases if c["case_id"] == case_id)


async def _list_cases(client: AsyncClient) -> list[dict]:
    response = await client.get(f"{BASE}/cases")
    assert response.status_code == 200
    return response.json()


# --- KPIs --------------------------------------------------------------------


async def test_metric_tiles_are_real_aggregates(client: AsyncClient, collections_seed: None) -> None:
    response = await client.get(f"{BASE}/metrics")
    assert response.status_code == 200
    body = response.json()
    labels = [tile["label"] for tile in body]
    assert labels == [
        "Open collection cases",
        "Current arrears",
        "90+ DPD cases",
        "Payment after contact",
        "Promise kept",
        "Scheduled payment realization",
        "Resolved cases",
    ]
    open_tile = next(t for t in body if t["label"] == "Open collection cases")
    resolved_tile = next(t for t in body if t["label"] == "Resolved cases")
    # 120 seeded cases split OPEN/RESOLVED — both real counts, never zero,
    # and they must add up to the seed's total.
    assert int(open_tile["value"]) + int(resolved_tile["value"]) == 120
    assert int(open_tile["value"]) > 0
    assert int(resolved_tile["value"]) > 0


async def test_agents_are_real_channel_tallies(client: AsyncClient, collections_seed: None) -> None:
    response = await client.get(f"{BASE}/agents")
    assert response.status_code == 200
    body = response.json()
    # 120 cases x 3 interactions = 360, spread over 5 real channels.
    total = sum(int(a["status"].split()[0]) for a in body)
    assert total == 360
    assert {a["name"] for a in body} == {
        "Sms workflow",
        "Whatsapp workflow",
        "Email workflow",
        "Call workflow",
        "Field Visit workflow",
    }


# --- Case-level model predictions ---------------------------------------------


async def test_roll_forward_risk_matches_the_real_trained_model(
    client: AsyncClient, collections_seed: None, db_session: AsyncSession
) -> None:
    """Roll-forward risk must come from the exact same trained model
    Collections Simulation uses — not a DPD-ratio heuristic."""
    from app.repositories.collections_simulation import CollectionsSimulationRepository

    models = await collections_model.get_or_train_models(CollectionsSimulationRepository(db_session))
    cases = await _list_cases(client)
    case = _find(cases, "seed-case-0")

    case_frame = models.case_frame
    row = case_frame[case_frame["collection_case_id"] == "seed-case-0"].iloc[0]
    expected_prob_resolve = models.roll_forward.predict_proba(
        {
            "principal_inr": float(row["principal_inr"]),
            "interest_rate_pct": float(row["interest_rate_pct"]),
            "debt_service_ratio_at_origination": float(row["debt_service_ratio_at_origination"]),
            "secured": 1.0 if row["secured"] else 0.0,
        }
    )
    expected_roll = round((1 - expected_prob_resolve) * 100)
    assert case["roll"] == expected_roll
    assert 0 <= case["roll"] <= 100


async def test_recovery_probability_and_best_channel_match_the_sweep(
    client: AsyncClient, collections_seed: None, db_session: AsyncSession
) -> None:
    """Recovery probability/best channel/action must come from a real
    argmax sweep over the trained recovery model — not the case's own
    empirical historical contact-success frequency."""
    from sqlalchemy import select

    from app.ai.simulation.collections_sim import sweep_best_channel_offer
    from app.database.runtime_schema import runtime_tables
    from app.repositories.collections_simulation import CollectionsSimulationRepository

    models = await collections_model.get_or_train_models(CollectionsSimulationRepository(db_session))
    cases = await _list_cases(client)
    case = _find(cases, "seed-case-0")

    interactions = runtime_tables["collection_interactions"]
    latest_outstanding = (
        await db_session.execute(
            select(interactions.c.outstanding_principal_at_interaction_inr)
            .where(interactions.c.collection_case_id == "seed-case-0")
            .order_by(interactions.c.interaction_sequence.desc())
            .limit(1)
        )
    ).scalar_one()

    best_channel, best_offer, best_prob, _net = sweep_best_channel_offer(
        models,
        {
            "dpd_at_interaction": float(case["dpd"]),
            "arrears_at_interaction_inr": 13650.0,
            "outstanding_principal_at_interaction_inr": float(latest_outstanding),
        },
        float(latest_outstanding),
    )
    assert case["channel"] == CHANNEL_DISPLAY_NAMES[best_channel]
    assert case["action"] == OFFER_DISPLAY_NAMES[best_offer]
    assert case["prob"] == round(best_prob * 100)


async def test_roll_forward_and_recovery_probability_are_never_conflated(
    client: AsyncClient, collections_seed: None
) -> None:
    """The two concepts must remain independently computed fields — never
    the same value, never derived from each other."""
    cases = await _list_cases(client)
    # At least one case where the two genuinely differ (near-certain with
    # 120 real cases from two unrelated logistic regressions).
    assert any(c["roll"] != c["prob"] for c in cases)
    for case in cases:
        assert 0 <= case["roll"] <= 100
        assert 0 <= case["prob"] <= 100


# --- Prioritization / real priority ranking / categorization ------------------


async def test_cases_are_ordered_by_real_priority_points_desc(client: AsyncClient, collections_seed: None) -> None:
    """Sort order is the computed priority score, not raw DPD."""
    cases = await _list_cases(client)
    points_by_priority = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}
    ranks = [points_by_priority[c["priority"]] for c in cases]
    assert ranks == sorted(ranks, reverse=True)
    # Confirms this is a real re-ranking, not the old DPD-desc order in
    # disguise — DPD is only a tiebreaker for cases with identical raw
    # priority points (a coarser signal than the 4 display levels above).
    assert [c["dpd"] for c in cases] != sorted((c["dpd"] for c in cases), reverse=True)


async def test_priority_is_backend_derived_and_explainable(client: AsyncClient, collections_seed: None) -> None:
    cases = await _list_cases(client)
    assert cases
    for case in cases:
        assert case["priority"] in {"Critical", "High", "Medium", "Low"}


async def test_all_cases_returned_including_resolved(client: AsyncClient, collections_seed: None) -> None:
    """Resolved cases are no longer excluded — they're tagged with the
    "resolved" filter category instead, so the frontend's Resolved tab has
    something real to show."""
    cases = await _list_cases(client)
    assert len(cases) == 120
    resolved = [c for c in cases if c["category"] == "resolved"]
    non_resolved = [c for c in cases if c["category"] != "resolved"]
    assert resolved
    assert non_resolved
    for case in resolved:
        assert case["status"] == "Resolved"
        assert case["dpd"] == 0  # a RESOLVED case's current_dpd is reset to 0 in the seed
    for case in non_resolved:
        assert case["status"] != "Resolved"


async def test_categories_are_mutually_exclusive_and_cover_every_case(
    client: AsyncClient, collections_seed: None
) -> None:
    cases = await _list_cases(client)
    categories = {c["category"] for c in cases}
    assert categories <= {"actionable", "review_required", "approved", "resolved"}
    # Every undecided, compliance-clean, still-open case must be
    # actionable — confirms the bucket isn't accidentally empty.
    assert any(c["category"] == "actionable" for c in cases)


# --- Compliance status is real, never a fabricated value ----------------------


async def test_compliance_flag_is_only_a_real_audit_status(client: AsyncClient, collections_seed: None) -> None:
    cases = await _list_cases(client)
    assert cases
    for case in cases:
        assert case["flag"] in {"Passed", "Review Required", "Failed"}
        assert case["governance_track"] == "live"
        assert case["status"] in {"Pending", "Approved", "Escalated", "Resolved"}
        if case["category"] == "actionable":
            assert case["decision_code"] is None


# --- Approve / Modify / Review persistence (live track) -----------------------


async def test_approve_case_persists_and_updates_status(client: AsyncClient, collections_seed: None) -> None:
    cases = await _list_cases(client)
    case = cases[0]
    response = await client.post(f"{BASE}/cases/{case['id']}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Approved"
    assert body["governance_track"] == "live"
    assert body["decision_code"] == case["case_id"]

    reloaded = _find(await _list_cases(client), case["case_id"])
    assert reloaded["status"] == "Approved"


async def test_approve_twice_conflicts(client: AsyncClient, collections_seed: None) -> None:
    case = (await _list_cases(client))[0]
    first = await client.post(f"{BASE}/cases/{case['id']}/approve")
    assert first.status_code == 200
    second = await client.post(f"{BASE}/cases/{case['id']}/approve")
    assert second.status_code == 409
    assert second.json()["code"] == "collections_case_already_decided"


async def test_modify_preserves_original_ai_recommendation(client: AsyncClient, collections_seed: None) -> None:
    """Preserve the original AI recommendation when a human modifies it —
    both must be independently retrievable afterward."""
    case = (await _list_cases(client))[0]
    original_channel_label = case["channel"]
    original_action_label = case["action"]

    # Pick a channel/offer combination guaranteed different from the AI's
    # own recommendation so the override is unambiguous.
    override_channel = "FIELD_VISIT" if original_channel_label != "Field Visit" else "SMS"
    override_offer = "REPAYMENT_PLAN_DISCUSSION" if original_action_label != "Repayment Plan Discussion" else "NONE"

    response = await client.post(
        f"{BASE}/cases/{case['id']}/modify",
        json={"channel": override_channel, "offer": override_offer, "reason": "Field team requested a visit."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Approved"
    assert body["channel"] == CHANNEL_DISPLAY_NAMES[override_channel]
    assert body["action"] == OFFER_DISPLAY_NAMES[override_offer]

    ledger = (await client.get(f"{BASE}/cases/{case['id']}/ledger")).json()
    assert ledger["track"] == "live"
    assert ledger["recommended_channel"] == original_channel_label
    assert ledger["recommended_offer"] == original_action_label
    assert ledger["modified_channel"] == CHANNEL_DISPLAY_NAMES[override_channel]
    assert ledger["modified_offer"] == OFFER_DISPLAY_NAMES[override_offer]
    assert ledger["modification_reason"] == "Field team requested a visit."


async def test_modify_rejects_a_channel_not_in_the_real_category_list(
    client: AsyncClient, collections_seed: None
) -> None:
    case = (await _list_cases(client))[0]
    response = await client.post(
        f"{BASE}/cases/{case['id']}/modify",
        json={"channel": "CARRIER_PIGEON", "offer": "NONE", "reason": ""},
    )
    assert response.status_code == 422


async def test_review_sends_case_to_human_review(client: AsyncClient, collections_seed: None) -> None:
    case = (await _list_cases(client))[0]
    response = await client.post(
        f"{BASE}/cases/{case['id']}/review",
        json={"reviewer_role": "Risk Reviewer", "reason": "High exposure, needs a second look."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Escalated"

    reloaded = _find(await _list_cases(client), case["case_id"])
    assert reloaded["status"] == "Escalated"

    # An escalated (not yet decided) case can still be approved afterward.
    approve = await client.post(f"{BASE}/cases/{case['id']}/approve")
    assert approve.status_code == 200
    assert approve.json()["status"] == "Approved"


async def test_case_actions_missing_case_return_404(client: AsyncClient, collections_seed: None) -> None:
    missing = uuid.uuid4()
    response = await client.post(f"{BASE}/cases/{missing}/approve")
    assert response.status_code == 404
    assert response.json()["code"] == "case_not_found"


# --- Trust Ledger linkage (canonical track) ------------------------------------


async def test_canonical_case_shows_real_canonical_governance(
    client: AsyncClient, collections_canonical_link_seed: None
) -> None:
    cases = await _list_cases(client)
    case = _find(cases, CANONICAL_LINKED_CASE_ID)
    assert case["governance_track"] == "canonical"
    assert case["decision_code"] == CANONICAL_LINKED_DECISION_ID
    assert case["status"] == "Approved"
    assert case["flag"] == "Passed"

    ledger = (await client.get(f"{BASE}/cases/{case['id']}/ledger")).json()
    assert ledger["track"] == "canonical"
    assert ledger["decision_code"] == CANONICAL_LINKED_DECISION_ID
    assert len(ledger["compliance"]) == 5
    assert all(check["result"] == "PASS" for check in ledger["compliance"])
    # No action_outcomes row was seeded for this decision — genuinely
    # pending, never a fabricated observed outcome.
    assert ledger["outcome"]["outcome_status"] == "PENDING"
    assert ledger["outcome"]["expected_impact"]["value"] == 0.12


async def test_canonical_case_actions_are_immutable(
    client: AsyncClient, collections_canonical_link_seed: None
) -> None:
    cases = await _list_cases(client)
    case = _find(cases, CANONICAL_LINKED_CASE_ID)

    for endpoint, payload in (
        ("approve", None),
        ("modify", {"channel": "SMS", "offer": "NONE", "reason": ""}),
        ("review", {"reviewer_role": "Risk Reviewer", "reason": ""}),
    ):
        response = await client.post(f"{BASE}/cases/{case['id']}/{endpoint}", json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == "immutable_trust_decision"

    # And the canonical state itself is untouched by the refused attempts.
    reloaded = _find(await _list_cases(client), CANONICAL_LINKED_CASE_ID)
    assert reloaded["status"] == "Approved"
    assert reloaded["governance_track"] == "canonical"
