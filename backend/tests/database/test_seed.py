"""Seed determinism and data-integrity tests (no database required)."""

from __future__ import annotations

from app.database import seed_data as sd
from app.database.seed import build_lineage, uid
from app.models.enums import (
    AgentStatus,
    CollectionsComplianceFlag,
    DealerLeadStatus,
    QaCategory,
    RecommendationRisk,
    SignalPanel,
    SimulationDomain,
    TrustApproval,
    TrustAudit,
    TrustRisk,
)


def test_uid_is_deterministic() -> None:
    assert uid("kpi", "rev") == uid("kpi", "rev")


def test_uid_differs_across_natural_keys() -> None:
    assert uid("kpi", "rev") != uid("kpi", "leak")
    assert uid("kpi", "rev") != uid("recommendation", "rev")


def test_uid_is_version_5() -> None:
    assert uid("dealer", "d1").version == 5


def test_enum_values_in_seed_data_are_valid() -> None:
    for row in sd.RECOMMENDATIONS:
        RecommendationRisk(row["risk"])
    for row in sd.DEALER_LEADS:
        DealerLeadStatus(row["status"])
    for row in sd.COLLECTIONS_AGENTS:
        AgentStatus(row["status"])
    for row in sd.AI_AGENTS:
        AgentStatus(row["status"])
    for row in sd.COLLECTIONS_CASES:
        CollectionsComplianceFlag(row["compliance_flag"])
    for row in sd.WAREHOUSE_SIGNALS:
        SignalPanel(row["panel"])
    for row in sd.TRUST_DECISIONS:
        TrustApproval(row["approval"])
        TrustRisk(row["risk"])
        TrustAudit(row["audit"])
    SimulationDomain(sd.SAMPLE_SIMULATION_RUN["domain"])


def test_natural_keys_are_unique() -> None:
    assert len({k["code"] for k in sd.KPIS}) == len(sd.KPIS)
    assert len({r["code"] for r in sd.RECOMMENDATIONS}) == len(sd.RECOMMENDATIONS)
    assert len({d["code"] for d in sd.DEALERS}) == len(sd.DEALERS)
    assert len({b["name"] for b in sd.SOLUTION_BUCKETS}) == len(sd.SOLUTION_BUCKETS)
    solutions = [item["name"] for bucket in sd.SOLUTION_BUCKETS for item in bucket["items"]]
    assert len(set(solutions)) == len(solutions)
    assert len({c["code"] for c in sd.CARBON_CREDITS}) == len(sd.CARBON_CREDITS)
    assert len({t["code"] for t in sd.TRUST_DECISIONS}) == len(sd.TRUST_DECISIONS)
    assert len({n["label"] for n in sd.CAUSAL_NODES}) == len(sd.CAUSAL_NODES)
    assert len(set(sd.SUGGESTED_PROMPTS)) == len(sd.SUGGESTED_PROMPTS)


def test_causal_edges_reference_known_nodes() -> None:
    labels = {node["label"] for node in sd.CAUSAL_NODES}
    for source, target in sd.CAUSAL_EDGES:
        assert source in labels
        assert target in labels


def test_qa_categories_covered() -> None:
    for row in sd.MOBILITY_QA + sd.DMRV_QA:
        assert row["question"] and row["answer"]
    QaCategory("mobility")
    QaCategory("dmrv")


def test_build_lineage_has_six_steps() -> None:
    row = sd.TRUST_DECISIONS[0]
    lineage = build_lineage(row)
    assert [step["step"] for step in lineage] == [1, 2, 3, 4, 5, 6]
    assert lineage[0]["detail"] == row["data_sources"]
    assert f"confidence {row['confidence']}%" in str(lineage[1]["detail"])
    assert lineage[3]["detail"] == "Approved"


def test_sample_simulation_outputs_match_autosales_formula() -> None:
    """Golden outputs for West / XUV700 / 8% / ₹30,000 / 4 Cr / High.

    Recomputed by hand from implementation_plan.md §4.1 using JS-style
    half-up rounding; the Phase 4 engine must reproduce these exactly.
    """
    outputs = sd.SAMPLE_SIMULATION_RUN["outputs"]
    assert outputs["uplift_pct"] == 41
    assert outputs["margin_impact_pct"] == -10
    assert outputs["cancellation_pct"] == 4
    assert outputs["revenue_index"] == 113
    assert sd.SAMPLE_SIMULATION_RUN["confidence"] == 89
