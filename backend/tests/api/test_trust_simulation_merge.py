"""Trust Ledger surfaces Simulation Center runs — pending or decided.

Canonical ``trust_decisions`` rows are empty in the SQLite test seam (no
seed data), so these tests exercise the simulation-merge path
specifically. Unlike the canonical (immutable) track, a still-open
simulation run is a genuine second governance entry point: Approve/
Reject/Escalate from the Trust Ledger call straight into
``SimulationService`` — the same code path the Simulation Center screen
itself uses — so the decision is recorded exactly once, on the same
``SimulationRun``/``SimulationApproval`` record, never duplicated.
"""

from __future__ import annotations

from httpx import AsyncClient

SIM_BASE = "/api/v1/simulations"
TRUST_BASE = "/api/v1/trust"


async def _create_run(client: AsyncClient) -> str:
    run = (await client.post(f"{SIM_BASE}/auto-sales/run", json={})).json()
    return run["run_id"]


async def _create_and_approve_run(client: AsyncClient) -> str:
    run_id = await _create_run(client)
    await client.post(f"{SIM_BASE}/{run_id}/approve", json={})
    return run_id


def _code(run_id: str) -> str:
    return f"SIM_{run_id.replace('-', '')}"


async def test_pending_simulation_run_appears_in_trust_ledger(client: AsyncClient, auto_sales_funnel: None) -> None:
    """A run with no decision yet must be visible — it's a live governance
    entry, not just a historical mirror of already-decided runs."""
    run_id = await _create_run(client)

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()

    matching = [d for d in decisions if run_id.replace("-", "") in d["id"]]
    assert len(matching) == 1
    assert matching[0]["approval"] == "Pending"


async def test_approved_simulation_run_appears_in_trust_ledger(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_and_approve_run(client)

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()

    matching = [d for d in decisions if run_id.replace("-", "") in d["id"]]
    assert len(matching) == 1
    row = matching[0]
    assert row["id"].startswith("SIM_")
    assert row["approval"] == "Approved"
    assert "auto sales" in row["use"].lower()


async def test_simulation_lineage_reflects_real_evidence(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_and_approve_run(client)

    lineage = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/lineage")).json()

    titles = [step["title"] for step in lineage]
    assert any(title.startswith("Model:") for title in titles)
    assert any(title.startswith("Human decision: Approved") for title in titles)


async def test_pending_simulation_lineage_shows_no_decision_yet(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    lineage = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/lineage")).json()

    titles = [step["title"] for step in lineage]
    assert any(title == "Human decision: Pending" for title in titles)


async def test_approve_from_trust_ledger_updates_the_same_simulation_record(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    """Regression: approving from the Trust Ledger must not create a
    second/independent decision — it has to be the exact same
    SimulationRun/SimulationApproval the Simulation Center screen reads."""
    run_id = await _create_run(client)

    response = await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/approve")
    assert response.status_code == 200
    assert response.json()["approval"] == "Approved"

    detail = (await client.get(f"{SIM_BASE}/{run_id}")).json()
    assert detail["status"] == "APPROVED"


async def test_reject_from_trust_ledger_updates_the_same_simulation_record(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    run_id = await _create_run(client)

    response = await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/reject", json={"reason": "Too risky"})
    assert response.status_code == 200
    assert response.json()["approval"] == "Rejected"

    detail = (await client.get(f"{SIM_BASE}/{run_id}")).json()
    assert detail["status"] == "REJECTED"


async def test_escalate_from_trust_ledger_marks_human_review_pending(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    run_id = await _create_run(client)

    response = await client.post(
        f"{TRUST_BASE}/decisions/{_code(run_id)}/escalate",
        json={"reviewer_role": "Risk Reviewer", "reason": "Confidence too low for autonomous action"},
    )
    assert response.status_code == 200
    assert response.json()["approval"] == "Escalated"

    detail = (await client.get(f"{SIM_BASE}/{run_id}")).json()
    assert detail["status"] == "HUMAN_REVIEW_PENDING"


async def test_escalated_run_can_still_be_approved_afterward(client: AsyncClient, auto_sales_funnel: None) -> None:
    """Escalation is a request, not a decision — the run must still be
    decidable once a reviewer looks at it."""
    run_id = await _create_run(client)
    await client.post(
        f"{TRUST_BASE}/decisions/{_code(run_id)}/escalate",
        json={"reviewer_role": "Risk Reviewer", "reason": "Needs a second look"},
    )

    response = await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/approve")

    assert response.status_code == 200
    assert response.json()["approval"] == "Approved"


async def test_simulation_decision_cannot_be_redecided_from_trust_ledger(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    """Once decided (by either the Simulation Center screen or the Trust
    Ledger itself), a second decision attempt must be refused with a
    genuine conflict, not silently accepted."""
    run_id = await _create_and_approve_run(client)

    response = await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/approve")

    assert response.status_code == 409
    assert response.json()["code"] == "simulation_run_already_decided"


async def test_decided_run_cannot_be_escalated(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_and_approve_run(client)

    response = await client.post(
        f"{TRUST_BASE}/decisions/{_code(run_id)}/escalate",
        json={"reviewer_role": "Compliance Reviewer", "reason": "Late request"},
    )

    assert response.status_code == 409


async def test_unknown_simulation_code_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{TRUST_BASE}/decisions/SIM_00000000000000000000000000000000/lineage")

    assert response.status_code == 404


async def test_simulation_compliance_is_real_and_per_decision(client: AsyncClient, auto_sales_funnel: None) -> None:
    """Regression: the compliance panel must never be a global aggregate
    (the exact bug this audit found) — each decision gets its own real
    rule evaluation, covering the same five-rule taxonomy already used
    for canonical decisions."""
    run_id = await _create_run(client)

    checks = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/compliance")).json()

    rule_codes = {c["rule_code"] for c in checks}
    assert rule_codes == {
        "BUSINESS_POLICY_ALIGNMENT",
        "LINEAGE_INTEGRITY",
        "EVIDENCE_SUFFICIENCY",
        "FAIRNESS_INPUT_SCOPE",
        "HUMAN_CONTROL_GATE",
    }
    fairness = next(c for c in checks if c["rule_code"] == "FAIRNESS_INPUT_SCOPE")
    assert fairness["result"] == "NOT_APPLICABLE"
    for check in checks:
        assert check["reason"], f"{check['rule_code']} has no explanation"


async def test_simulation_compliance_is_cached_not_recomputed_differently(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    run_id = await _create_run(client)

    first = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/compliance")).json()
    second = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/compliance")).json()

    assert first == second


async def test_low_confidence_simulation_run_requires_human_review(client: AsyncClient, auto_sales_funnel: None) -> None:
    """Regression: the human-control gate must genuinely react to real
    confidence/risk, not always return the same hardcoded proxy value."""
    run_id = await _create_run(client)

    detail = (await client.get(f"{SIM_BASE}/{run_id}")).json()
    checks = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/compliance")).json()
    gate = next(c for c in checks if c["rule_code"] == "HUMAN_CONTROL_GATE")

    if detail["confidence"] < 60:
        assert gate["result"] == "REVIEW_REQUIRED"
        decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
        row = next(d for d in decisions if d["id"] == _code(run_id))
        assert row["audit"] == "Review Required"


async def test_simulation_explanation_reuses_real_persisted_drivers(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    """Regression: explanation must reuse the run's own stored
    driver_json — never fabricate driver names/contributions."""
    run_id = await _create_run(client)
    detail = (await client.get(f"{SIM_BASE}/{run_id}")).json()

    explanation = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/explanation")).json()

    assert explanation["confidence"] == detail["confidence"]
    assert explanation["confidence_basis"] == detail["confidence_basis"]
    assert explanation["recommendation"] == detail["outputs"]["recommendedAction"]
    stored_drivers = detail["driver_json"]["predictive_drivers"]
    assert len(explanation["drivers"]) == len(stored_drivers)
    assert {d["name"] for d in explanation["drivers"]} == {d["name"] for d in stored_drivers}
    assert explanation["supporting_evidence"], "baseline_reference should surface as supporting evidence"


async def test_pending_simulation_explanation_does_not_require_a_decision(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    run_id = await _create_run(client)

    response = await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/explanation")

    assert response.status_code == 200


async def test_pending_simulation_run_is_not_execution_eligible(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
    row = next(d for d in decisions if d["id"] == _code(run_id))

    assert row["execution_eligible"] is False
    assert row["execution_eligible_reason"], "a Blocked pill must never appear with no explanation"
    assert "blocked" in row["execution_eligible_reason"].lower()


async def test_rejected_simulation_run_is_not_execution_eligible(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)
    await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/reject", json={"reason": "no"})

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
    row = next(d for d in decisions if d["id"] == _code(run_id))

    assert row["execution_eligible"] is False


async def test_approved_simulation_run_with_no_failed_checks_is_execution_eligible(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    """Regression: approval alone is not enough per se — this asserts the
    common real-world case (no compliance rule ever FAILs in this data)
    ends up eligible once approved, while the earlier tests confirm
    approval status is still a hard requirement."""
    run_id = await _create_and_approve_run(client)

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
    row = next(d for d in decisions if d["id"] == _code(run_id))

    checks = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/compliance")).json()
    any_failed = any(c["result"] == "FAIL" for c in checks)
    assert row["execution_eligible"] == (not any_failed)
    assert row["execution_eligible_reason"]
    if not any_failed:
        assert "approved" in row["execution_eligible_reason"].lower()


async def test_simulation_events_are_chronological_and_real(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)
    await client.post(
        f"{TRUST_BASE}/decisions/{_code(run_id)}/escalate",
        json={"reviewer_role": "Risk Reviewer", "reason": "double-checking"},
    )
    await client.post(f"{TRUST_BASE}/decisions/{_code(run_id)}/approve")

    events = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/events")).json()

    event_types = [e["event_type"] for e in events]
    assert event_types == ["DECISION_CREATED", "HUMAN_ESCALATED", "HUMAN_APPROVED"]
    timestamps = [e["event_at"] for e in events]
    assert timestamps == sorted(timestamps)


async def test_pending_simulation_run_has_only_the_creation_event(client: AsyncClient, auto_sales_funnel: None) -> None:
    run_id = await _create_run(client)

    events = (await client.get(f"{TRUST_BASE}/decisions/{_code(run_id)}/events")).json()

    assert [e["event_type"] for e in events] == ["DECISION_CREATED"]


async def test_ledger_data_column_is_meaningful_for_every_domain(
    client: AsyncClient,
    dealer_allocation_seed: None,
    collections_seed: None,
    logistics_delay_seed: None,
    credit_pricing_seed: None,
) -> None:
    """Regression: the `data` column must never fall back to the
    Auto-Sales-shaped "region/model" placeholder ("? / ?") for domains
    whose real inputs are shaped differently."""
    dealer_run = (await client.post(f"{SIM_BASE}/dealer-allocation/run", json={})).json()
    collections_run = (await client.post(f"{SIM_BASE}/collections/run", json={})).json()
    logistics_run = (
        await client.post(
            f"{SIM_BASE}/logistics-delay/run",
            json={"route": "seed-route-a", "warehouse": 60, "vehicle": 70, "weather": 20, "sla": "HIGH"},
        )
    ).json()
    credit_run = (await client.post(f"{SIM_BASE}/credit-pricing/run", json={})).json()

    decisions = (await client.get(f"{TRUST_BASE}/decisions")).json()
    by_id = {d["id"]: d for d in decisions}

    dealer_data = by_id[_code(dealer_run["run_id"])]["data"]
    collections_data = by_id[_code(collections_run["run_id"])]["data"]
    logistics_data = by_id[_code(logistics_run["run_id"])]["data"]
    credit_data = by_id[_code(credit_run["run_id"])]["data"]

    assert dealer_data != "? / ?" and "units" in dealer_data
    assert collections_data != "? / ?" and "risk" in collections_data
    assert logistics_data == "Route seed-route-a"
    assert credit_data != "?" and credit_data in {"MIXED_CIRCULARITY", "RECYCLING_AVOIDANCE", "REUSE_AVOIDANCE"}
