"""Logistics AI Control Tower: real database-backed route/shipment intelligence.

Exercises the real backend (services/operational_logistics.py) against the
``logistics_delay_seed`` fixture (two real West -> North routes, 150
real-shaped shipments each, route B deliberately safer) plus one canonical
(Synthetic Data Factory-style) trust decision linked to a real seeded
shipment, so both governance tracks (canonical vs live) are covered.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

BASE = "/api/v1/logistics"

CANONICAL_LINKED_SHIPMENT_ID = "seed-shipment-0"
CANONICAL_LINKED_DECISION_ID = "DEC_SEED_LOGISTICS_SHIPMENT_0"

_RULE_CODES = [
    ("BUSINESS_POLICY_ALIGNMENT", "Business policy alignment"),
    ("LINEAGE_INTEGRITY", "Data lineage integrity"),
    ("EVIDENCE_SUFFICIENCY", "Evidence and explainability sufficiency"),
    ("FAIRNESS_INPUT_SCOPE", "Fairness input-scope check"),
    ("HUMAN_CONTROL_GATE", "Human-control risk gate"),
]


@pytest_asyncio.fixture
async def logistics_canonical_link_seed(db_session: AsyncSession, logistics_delay_seed: None) -> None:
    """Link one real seeded shipment to a canonical (immutable)
    trust_decisions row, mirroring the real production shape where a
    subset of shipments already carry Synthetic Data Factory governance
    history."""
    recommendation_id = "REC_SEED_LOGISTICS_SHIPMENT_0"
    recommendation = {
        "recommendation_id": recommendation_id,
        "domain": "LOGISTICS",
        "use_case": "LOGISTICS_DELAY_MITIGATION",
        "target_entity_type": "SHIPMENT",
        "target_entity_id": CANONICAL_LINKED_SHIPMENT_ID,
        "recommendation_type": "RECOMMEND_REROUTE",
        "generated_at": datetime(2026, 1, 5, tzinfo=UTC),
        "evidence_json": json.dumps({"route_id": "seed-route-a"}),
        "expected_impact": json.dumps({"metric": "sla_breach_probability", "direction": "IMPROVE", "value": 0.1}),
        "confidence": 0.85,
        "risk_level": "MEDIUM",
        "status": "ACCEPTED",
        "data_origin": "TEST_SEED",
        "generator_version": "test",
    }
    decision = {
        "decision_id": CANONICAL_LINKED_DECISION_ID,
        "recommendation_id": recommendation_id,
        "domain": "LOGISTICS",
        "use_case": "LOGISTICS_DELAY_MITIGATION",
        "target_entity_type": "SHIPMENT",
        "target_entity_id": CANONICAL_LINKED_SHIPMENT_ID,
        "recommendation_type": "RECOMMEND_REROUTE",
        "recommendation_confidence": 0.85,
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
            "compliance_check_id": f"CHK_SEED_LOGISTICS_SHIPMENT_0_{code}",
            "decision_id": CANONICAL_LINKED_DECISION_ID,
            "recommendation_id": recommendation_id,
            "domain": "LOGISTICS",
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


def _find_route(routes: list[dict], route_id: str) -> dict:
    return next(r for r in routes if r["route_id"] == route_id)


def _find_shipment(shipments: list[dict], shipment_id: str) -> dict:
    return next(s for s in shipments if s["shipment_id"] == shipment_id)


async def _list_routes(client: AsyncClient) -> list[dict]:
    response = await client.get(f"{BASE}/routes")
    assert response.status_code == 200
    return response.json()


async def _list_shipments(client: AsyncClient, route_uuid: str) -> list[dict]:
    response = await client.get(f"{BASE}/routes/{route_uuid}/shipments")
    assert response.status_code == 200
    return response.json()


# --- Route cards ---------------------------------------------------------------


async def test_routes_are_real_aggregates_over_seeded_shipments(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    routes = await _list_routes(client)
    assert len(routes) == 2
    for route in routes:
        assert route["active_shipments"] == 150
        assert 0 <= route["slaRisk"] <= 100
        assert 0 <= route["delayProb"] <= 100
        assert route["priority"] in {"Critical", "High", "Medium", "Low"}
        assert route["status"] in {"Pending", "Approved", "Escalated"}


async def test_route_b_is_a_genuinely_safer_corridor(client: AsyncClient, logistics_delay_seed: None) -> None:
    """Confirms the trained model actually differentiates the two seeded
    routes — not a fixed/hardcoded number for every route."""
    routes = await _list_routes(client)
    route_a = _find_route(routes, "seed-route-a")
    route_b = _find_route(routes, "seed-route-b")
    # Rounded route-level averages can occasionally tie at these sample
    # sizes, so require route B to be no worse on both and strictly
    # better on at least one — never simply equal on everything.
    assert route_b["slaRisk"] <= route_a["slaRisk"]
    assert route_b["delayProb"] <= route_a["delayProb"]
    assert route_b["slaRisk"] < route_a["slaRisk"] or route_b["delayProb"] < route_a["delayProb"]


async def test_warehouse_signals_are_real_aggregates(client: AsyncClient, logistics_delay_seed: None) -> None:
    response = await client.get(f"{BASE}/warehouse-signals")
    assert response.status_code == 200
    body = response.json()
    # 3 real warehouses (Mumbai/Pune/Delhi) x 3 signal tiles each.
    assert len(body) == 9
    for tile in body:
        assert tile["tone"] in {"success", "warning", "danger"}
        assert tile["affected_routes"]


async def test_predict_delay_matches_the_route_card(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    route = routes[0]
    response = await client.post(f"{BASE}/routes/{route['id']}/predict-delay")
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == route["route_id"]
    assert body["slaRisk"] == route["slaRisk"]
    assert body["delayProb"] == route["delayProb"]


async def test_reroute_preview_does_not_persist_anything(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    route = routes[0]
    response = await client.post(f"{BASE}/routes/{route['id']}/reroute")
    assert response.status_code == 200
    # A pure preview must not change the route's own status/persisted state.
    reloaded = _find_route(await _list_routes(client), route["route_id"])
    assert reloaded["status"] == route["status"]


async def test_route_actions_missing_route_return_404(client: AsyncClient, logistics_delay_seed: None) -> None:
    missing = uuid.uuid4()
    for path in ("predict-delay", "reroute", "auto-heal"):
        response = await client.post(f"{BASE}/routes/{missing}/{path}")
        assert response.status_code == 404
        assert response.json()["code"] == "route_not_found"
    response = await client.get(f"{BASE}/routes/{missing}/shipments")
    assert response.status_code == 404
    response = await client.get(f"{BASE}/routes/{missing}/sla-report")
    assert response.status_code == 404


# --- Shipment drill-down ---------------------------------------------------------


async def test_shipments_drill_down_lists_every_route_shipment(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    route = _find_route(routes, "seed-route-a")
    shipments = await _list_shipments(client, route["id"])
    assert len(shipments) == 150
    assert {s["shipment_id"] for s in shipments} == {f"seed-shipment-{i}" for i in range(150)}
    # Sorted by breach probability, descending.
    breach_probs = [s["breach_probability"] for s in shipments]
    assert breach_probs == sorted(breach_probs, reverse=True)


async def test_delay_and_breach_probability_are_never_conflated(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    route = routes[0]
    shipments = await _list_shipments(client, route["id"])
    assert any(s["delay_probability"] != s["breach_probability"] for s in shipments)
    for shipment in shipments:
        assert 0 <= shipment["delay_probability"] <= 100
        assert 0 <= shipment["breach_probability"] <= 100


async def test_shipments_are_all_live_governance_track_without_canonical_seed(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    routes = await _list_routes(client)
    shipments = await _list_shipments(client, routes[0]["id"])
    assert all(s["governance_track"] == "live" for s in shipments)
    assert all(s["decision_status"] == "Pending" for s in shipments)
    assert all(s["decision_code"] is None for s in shipments)


# --- Approve / Modify / Review persistence (live track) -------------------------


async def test_approve_shipment_persists_and_updates_status(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    shipments = await _list_shipments(client, routes[0]["id"])
    shipment = shipments[0]

    response = await client.post(f"{BASE}/shipments/{shipment['shipment_id']}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["decision_status"] == "Approved"
    assert body["governance_track"] == "live"
    assert body["decision_code"] == shipment["shipment_id"]

    reloaded = _find_shipment(await _list_shipments(client, routes[0]["id"]), shipment["shipment_id"])
    assert reloaded["decision_status"] == "Approved"


async def test_approve_twice_conflicts(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    shipment = (await _list_shipments(client, routes[0]["id"]))[0]
    first = await client.post(f"{BASE}/shipments/{shipment['shipment_id']}/approve")
    assert first.status_code == 200
    second = await client.post(f"{BASE}/shipments/{shipment['shipment_id']}/approve")
    assert second.status_code == 409
    assert second.json()["code"] == "shipment_already_decided"


async def test_modify_preserves_original_ai_recommendation(client: AsyncClient, logistics_delay_seed: None) -> None:
    """Preserve the original AI recommendation when a human modifies it —
    both must be independently retrievable afterward via the ledger."""
    routes = await _list_routes(client)
    shipments = await _list_shipments(client, routes[0]["id"])
    shipment = next(s for s in shipments if s["recommended_action"] == "Reroute")
    original_recommended_route_label = shipment["recommended_route_label"]

    response = await client.post(
        f"{BASE}/shipments/{shipment['shipment_id']}/modify",
        json={"action": "MAINTAIN", "reason": "Ops override: transporter already committed."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_status"] == "Approved"
    assert body["recommended_action"] == "Maintain"
    assert body["recommended_route_label"] is None

    ledger = (await client.get(f"{BASE}/shipments/{shipment['shipment_id']}/ledger")).json()
    assert ledger["track"] == "live"
    assert ledger["recommended_action"] == "Reroute"
    assert original_recommended_route_label is not None
    assert ledger["modified_action"] == "Maintain"
    assert ledger["modification_reason"] == "Ops override: transporter already committed."


async def test_modify_reroute_requires_a_real_route_id(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    shipment = (await _list_shipments(client, routes[0]["id"]))[0]
    response = await client.post(
        f"{BASE}/shipments/{shipment['shipment_id']}/modify",
        json={"action": "REROUTE", "reason": ""},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "missing_route_id"


async def test_modify_rejects_an_action_not_in_the_real_category_list(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    routes = await _list_routes(client)
    shipment = (await _list_shipments(client, routes[0]["id"]))[0]
    response = await client.post(
        f"{BASE}/shipments/{shipment['shipment_id']}/modify",
        json={"action": "TELEPORT", "reason": ""},
    )
    assert response.status_code == 422


async def test_review_sends_shipment_to_human_review(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    shipment = (await _list_shipments(client, routes[0]["id"]))[0]
    response = await client.post(
        f"{BASE}/shipments/{shipment['shipment_id']}/review",
        json={"reviewer_role": "Risk Reviewer", "reason": "High breach probability, needs a second look."},
    )
    assert response.status_code == 200
    assert response.json()["decision_status"] == "Escalated"

    reloaded = _find_shipment(await _list_shipments(client, routes[0]["id"]), shipment["shipment_id"])
    assert reloaded["decision_status"] == "Escalated"

    # An escalated (not yet approved) shipment can still be approved afterward.
    approve = await client.post(f"{BASE}/shipments/{shipment['shipment_id']}/approve")
    assert approve.status_code == 200
    assert approve.json()["decision_status"] == "Approved"


async def test_shipment_actions_missing_shipment_return_404(client: AsyncClient, logistics_delay_seed: None) -> None:
    response = await client.post(f"{BASE}/shipments/does-not-exist/approve")
    assert response.status_code == 404
    assert response.json()["code"] == "shipment_not_found"


# --- Auto-heal (bulk persisting action) ------------------------------------------


async def test_auto_heal_approves_only_at_risk_undecided_shipments(
    client: AsyncClient, logistics_delay_seed: None
) -> None:
    routes = await _list_routes(client)
    route = routes[0]
    shipments_before = await _list_shipments(client, route["id"])
    at_risk_ids = {s["shipment_id"] for s in shipments_before if s["breach_probability"] >= 25}

    response = await client.post(f"{BASE}/routes/{route['id']}/auto-heal")
    assert response.status_code == 200
    body = response.json()
    assert body["approved_shipments"] == len(at_risk_ids)
    assert body["already_decided_shipments"] == 0
    assert body["route"]["status"] == ("Approved" if at_risk_ids else "Pending")

    shipments_after = await _list_shipments(client, route["id"])
    for shipment in shipments_after:
        if shipment["shipment_id"] in at_risk_ids:
            assert shipment["decision_status"] == "Approved"
        else:
            assert shipment["decision_status"] == "Pending"

    # Running it again finds nothing new to approve — everything at-risk
    # is already decided.
    second = await client.post(f"{BASE}/routes/{route['id']}/auto-heal")
    assert second.status_code == 200
    assert second.json()["approved_shipments"] == 0
    assert second.json()["already_decided_shipments"] == len(at_risk_ids)


# --- SLA report -------------------------------------------------------------------


async def test_sla_report_is_a_real_aggregate(client: AsyncClient, logistics_delay_seed: None) -> None:
    routes = await _list_routes(client)
    route = routes[0]
    response = await client.get(f"{BASE}/routes/{route['id']}/sla-report")
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == route["route_id"]
    assert body["active_shipments"] == 150
    assert 0 <= body["on_time_shipments"] <= 150
    assert body["at_risk_shipments"] == route["at_risk_shipments"]
    assert body["drivers"]
    assert body["cost_exposure_inr"] >= 0


# --- Trust Ledger linkage (canonical track) ---------------------------------------


async def test_canonical_shipment_shows_real_canonical_governance(
    client: AsyncClient, logistics_canonical_link_seed: None
) -> None:
    routes = await _list_routes(client)
    route = _find_route(routes, "seed-route-a")
    shipments = await _list_shipments(client, route["id"])
    shipment = _find_shipment(shipments, CANONICAL_LINKED_SHIPMENT_ID)
    assert shipment["governance_track"] == "canonical"
    assert shipment["decision_code"] == CANONICAL_LINKED_DECISION_ID
    assert shipment["decision_status"] == "Approved"

    ledger = (await client.get(f"{BASE}/shipments/{CANONICAL_LINKED_SHIPMENT_ID}/ledger")).json()
    assert ledger["track"] == "canonical"
    assert ledger["decision_code"] == CANONICAL_LINKED_DECISION_ID
    assert len(ledger["compliance"]) == 5
    assert all(check["result"] == "PASS" for check in ledger["compliance"])
    assert ledger["outcome"]["outcome_status"] == "PENDING"
    assert ledger["outcome"]["expected_impact"]["value"] == 0.1


async def test_canonical_shipment_actions_are_immutable(
    client: AsyncClient, logistics_canonical_link_seed: None
) -> None:
    for endpoint, payload in (
        ("approve", None),
        ("modify", {"action": "MAINTAIN", "reason": ""}),
        ("review", {"reviewer_role": "Risk Reviewer", "reason": ""}),
    ):
        response = await client.post(f"{BASE}/shipments/{CANONICAL_LINKED_SHIPMENT_ID}/{endpoint}", json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == "immutable_trust_decision"

    routes = await _list_routes(client)
    route = _find_route(routes, "seed-route-a")
    reloaded = _find_shipment(await _list_shipments(client, route["id"]), CANONICAL_LINKED_SHIPMENT_ID)
    assert reloaded["decision_status"] == "Approved"
    assert reloaded["governance_track"] == "canonical"


async def test_auto_heal_skips_canonical_shipments(client: AsyncClient, logistics_canonical_link_seed: None) -> None:
    routes = await _list_routes(client)
    route = _find_route(routes, "seed-route-a")
    response = await client.post(f"{BASE}/routes/{route['id']}/auto-heal")
    assert response.status_code == 200
    assert response.json()["already_decided_shipments"] >= 1
