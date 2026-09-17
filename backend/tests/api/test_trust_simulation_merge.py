"""Trust Ledger surfaces already-decided Simulation Center runs.

Canonical ``trust_decisions`` rows are empty in the SQLite test seam (no
seed data), so these tests exercise the simulation-merge path specifically:
a decided Auto Sales run should appear as a read-only ``SIM_``-prefixed
row, with real lineage from its own persisted evidence, and further
approve/reject/escalate attempts from the Trust Ledger refused (the
decision already happened in the Simulation Center).
"""

from __future__ import annotations

from httpx import AsyncClient

SIM_BASE = "/api/v1/simulations"
TRUST_BASE = "/api/v1/trust"


async def _create_and_approve_run(client: AsyncClient) -> str:
    run = (await client.post(f"{SIM_BASE}/auto-sales/run", json={})).json()
    await client.post(f"{SIM_BASE}/{run['run_id']}/approve", json={})
    return run["run_id"]


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
    code = f"SIM_{run_id.replace('-', '')}"

    lineage = (await client.get(f"{TRUST_BASE}/decisions/{code}/lineage")).json()

    titles = [step["title"] for step in lineage]
    assert any(title.startswith("Model:") for title in titles)
    assert any(title.startswith("Human decision: Approved") for title in titles)


async def test_simulation_decision_cannot_be_reapproved_from_trust_ledger(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    run_id = await _create_and_approve_run(client)
    code = f"SIM_{run_id.replace('-', '')}"

    response = await client.post(f"{TRUST_BASE}/decisions/{code}/approve")

    assert response.status_code == 422
    assert response.json()["code"] == "simulation_decision_immutable"


async def test_unknown_simulation_code_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"{TRUST_BASE}/decisions/SIM_00000000000000000000000000000000/lineage")

    assert response.status_code == 404
