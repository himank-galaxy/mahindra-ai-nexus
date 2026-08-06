"""Idempotent database seeding.

Loads the verbatim seed data (``seed_data.py``) into PostgreSQL using
deterministic UUID5 primary keys derived from each row's natural key, so the
script can be re-run any number of times (``session.merge`` upserts) and
always converges to the same state.

Design rules:
- IDs: ``uid(*parts)`` = uuid5 over a fixed namespace — stable across runs.
- FKs are set by id (computed from the parent's natural key), never via
  relationship loading, so seeding order is flat and predictable.
- ``--reset`` TRUNCATEs every seeded table first (dev/demo escape hatch).
- Copilot sessions/messages are intentionally NOT seeded; the copilot engine
  lands in Phase 4 and owns that data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import DEMO_USER_ID
from app.database import seed_data as sd
from app.models import (
    AiAgent,
    CarbonCredit,
    CausalEdge,
    CausalNode,
    CausalQa,
    CollectionsAgent,
    CollectionsCase,
    ComplianceRule,
    CustomerTwin,
    Dealer,
    DealerLead,
    FinanceProduct,
    Kpi,
    KpiDriver,
    LogisticsRoute,
    MobilityKpi,
    Recommendation,
    Region,
    SimulationRun,
    Solution,
    SolutionBucket,
    SuggestedPrompt,
    TrustDecision,
    User,
    VehicleModel,
    WarehouseSignal,
    XrExperience,
)
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

logger = get_logger(__name__)

# Fixed namespace for every seeded primary key — never change it, or re-runs
# will duplicate rows instead of upserting.
SEED_NAMESPACE = uuid.UUID("4f1a2b3c-5d6e-4f70-8192-a3b4c5d6e7f8")

# Tables emptied by ``--reset`` (CASCADE covers FK children automatically).
SEEDED_TABLES = (
    "users",
    "kpis",
    "kpi_drivers",
    "recommendations",
    "solution_buckets",
    "solutions",
    "dealers",
    "dealer_leads",
    "finance_products",
    "customer_twins",
    "collections_agents",
    "collections_cases",
    "logistics_routes",
    "warehouse_signals",
    "carbon_credits",
    "trust_decisions",
    "compliance_rules",
    "ai_agents",
    "xr_experiences",
    "causal_nodes",
    "causal_edges",
    "mobility_kpis",
    "causal_qa",
    "suggested_prompts",
    "simulation_runs",
    "regions",
    "vehicle_models",
)

# Human-readable approval labels rendered in the trust lineage modal.
APPROVAL_DISPLAY = {
    TrustApproval.APPROVED: "Approved",
    TrustApproval.HUMAN_REVIEW: "Human review",
    TrustApproval.PENDING: "Pending",
    TrustApproval.REJECTED: "Rejected",
    TrustApproval.ESCALATED: "Escalated",
}


def uid(*parts: str) -> uuid.UUID:
    """Deterministic primary key for a seed row's natural key."""
    return uuid.uuid5(SEED_NAMESPACE, "|".join(parts))


@dataclass
class SeedReport:
    """Row counts written per table (for logging and tests)."""

    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def add(self, table: str, count: int) -> None:
        self.counts[table] = self.counts.get(table, 0) + count


def build_lineage(row: dict[str, str | int]) -> list[dict[str, str | int]]:
    """Six-step lineage trail persisted with each trust decision."""
    approval = TrustApproval(str(row["approval"]))
    return [
        {"step": 1, "title": "Data used", "detail": str(row["data_sources"])},
        {
            "step": 2,
            "title": "Recommendation",
            "detail": f"{row['recommendation']} · confidence {row['confidence']}%",
        },
        {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"},
        {"step": 4, "title": "Approval", "detail": APPROVAL_DISPLAY[approval]},
        *[{"step": step, "title": title, "detail": detail} for step, title, detail in sd.TRUST_LINEAGE_STATIC_STEPS],
    ]


async def reset_database(session: AsyncSession) -> None:
    """TRUNCATE every seeded table (FK children handled by CASCADE)."""
    await session.execute(text(f"TRUNCATE TABLE {', '.join(SEEDED_TABLES)} CASCADE"))
    logger.info("seed_reset_complete", tables=len(SEEDED_TABLES))


async def seed_database(session: AsyncSession, *, reset: bool = False) -> SeedReport:
    """Seed all tables idempotently and commit. Returns the row report."""
    report = SeedReport()

    if reset:
        await reset_database(session)

    # ------------------------------------------------------------------
    # Reference data + demo user
    # ------------------------------------------------------------------
    for code in sd.REGIONS:
        await session.merge(Region(code=code))
    report.add("regions", len(sd.REGIONS))

    for name in sd.VEHICLE_MODELS:
        await session.merge(VehicleModel(name=name))
    report.add("vehicle_models", len(sd.VEHICLE_MODELS))

    await session.merge(User(id=DEMO_USER_ID, email="demo@mahindra-nexus.local", full_name="Demo User", is_active=True))
    report.add("users", 1)

    # ------------------------------------------------------------------
    # Executive overview
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.KPIS):
        await session.merge(
            Kpi(
                id=uid("kpi", row["code"]),
                code=row["code"],
                label=row["label"],
                value=row["value"],
                trend=row["trend"],
                trend_up=row["up"],
                confidence=row["confidence"],
                sort_order=order,
            )
        )
        for driver_order, driver_text in enumerate(row["drivers"]):
            await session.merge(
                KpiDriver(
                    id=uid("kpi_driver", row["code"], driver_text),
                    kpi_id=uid("kpi", row["code"]),
                    driver_text=driver_text,
                    sort_order=driver_order,
                )
            )
        report.add("kpi_drivers", len(row["drivers"]))
    report.add("kpis", len(sd.KPIS))

    for order, row in enumerate(sd.RECOMMENDATIONS):
        await session.merge(
            Recommendation(
                id=uid("recommendation", row["code"]),
                code=row["code"],
                title=row["title"],
                impact=row["impact"],
                confidence=row["confidence"],
                risk=RecommendationRisk(row["risk"]),
                sort_order=order,
            )
        )
    report.add("recommendations", len(sd.RECOMMENDATIONS))

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    for order, bucket in enumerate(sd.SOLUTION_BUCKETS):
        await session.merge(
            SolutionBucket(
                id=uid("bucket", bucket["name"]),
                name=bucket["name"],
                tag=bucket["tag"],
                sort_order=order,
            )
        )
        for item_order, item in enumerate(bucket["items"]):
            await session.merge(
                Solution(
                    id=uid("solution", item["name"]),
                    bucket_id=uid("bucket", bucket["name"]),
                    name=item["name"],
                    problem=item["problem"],
                    solution=item["solution"],
                    differentiator=item["diff"],
                    impact=item["impact"],
                    sort_order=item_order,
                )
            )
        report.add("solutions", len(bucket["items"]))
    report.add("solution_buckets", len(sd.SOLUTION_BUCKETS))

    # ------------------------------------------------------------------
    # Dealers
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.DEALERS):
        await session.merge(
            Dealer(
                id=uid("dealer", row["code"]),
                code=row["code"],
                name=row["name"],
                leads=row["leads"],
                hot_leads=row["hot_leads"],
                test_drives_pending=row["test_drives_pending"],
                booking_prob=row["booking_prob"],
                revenue_at_risk=row["revenue_at_risk"],
                leakage_pct=row["leakage_pct"],
                bay_util_pct=row["bay_util_pct"],
                sort_order=order,
            )
        )
    report.add("dealers", len(sd.DEALERS))

    for order, row in enumerate(sd.DEALER_LEADS):
        await session.merge(
            DealerLead(
                id=uid("dealer_lead", row["dealer"], row["name"]),
                dealer_id=uid("dealer", row["dealer"]),
                name=row["name"],
                vehicle=row["vehicle"],
                score=row["score"],
                prob=row["prob"],
                action=row["action"],
                revenue=row["revenue"],
                status=DealerLeadStatus(row["status"]),
                sort_order=order,
            )
        )
    report.add("dealer_leads", len(sd.DEALER_LEADS))

    # ------------------------------------------------------------------
    # Finance
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.FINANCE_PRODUCTS):
        await session.merge(
            FinanceProduct(
                id=uid("finance_product", row["name"]),
                name=row["name"],
                customers=row["customers"],
                risk=row["risk"],
                cross_sell=row["cross_sell"],
                opportunity=row["opportunity"],
                sort_order=order,
            )
        )
    report.add("finance_products", len(sd.FINANCE_PRODUCTS))

    for row in sd.CUSTOMER_TWINS:
        await session.merge(
            CustomerTwin(
                id=uid("customer_twin", row["name"]),
                name=row["name"],
                location=row["location"],
                income_stability=row["income_stability"],
                repayment=row["repayment"],
                products=row["products"],
                nba=row["nba"],
                risk_decomposition=row["risk_decomposition"],
                cross_sell=row["cross_sell"],
            )
        )
    report.add("customer_twins", len(sd.CUSTOMER_TWINS))

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.COLLECTIONS_AGENTS):
        await session.merge(
            CollectionsAgent(
                id=uid("collections_agent", row["name"]),
                name=row["name"],
                status=AgentStatus(row["status"]),
                sort_order=order,
            )
        )
    report.add("collections_agents", len(sd.COLLECTIONS_AGENTS))

    for order, row in enumerate(sd.COLLECTIONS_CASES):
        await session.merge(
            CollectionsCase(
                id=uid("collections_case", row["customer"]),
                customer=row["customer"],
                dpd=row["dpd"],
                outstanding=row["outstanding"],
                roll_forward_risk=row["roll_forward_risk"],
                channel=row["channel"],
                action=row["action"],
                prob=row["prob"],
                compliance_flag=CollectionsComplianceFlag(row["compliance_flag"]),
                sort_order=order,
            )
        )
    report.add("collections_cases", len(sd.COLLECTIONS_CASES))

    # ------------------------------------------------------------------
    # Logistics + signal tiles
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.LOGISTICS_ROUTES):
        await session.merge(
            LogisticsRoute(
                id=uid("logistics_route", row["name"]),
                name=row["name"],
                sla_risk=row["sla_risk"],
                delay_prob=row["delay_prob"],
                cost=row["cost"],
                recommended_action=row["recommended_action"],
                sort_order=order,
            )
        )
    report.add("logistics_routes", len(sd.LOGISTICS_ROUTES))

    for order, row in enumerate(sd.WAREHOUSE_SIGNALS):
        await session.merge(
            WarehouseSignal(
                id=uid("warehouse_signal", row["panel"], row["label"]),
                panel=SignalPanel(row["panel"]),
                label=row["label"],
                value=row["value"],
                tone=row["tone"],
                sort_order=order,
            )
        )
    report.add("warehouse_signals", len(sd.WAREHOUSE_SIGNALS))

    # ------------------------------------------------------------------
    # Circularity
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.CARBON_CREDITS):
        await session.merge(
            CarbonCredit(
                id=uid("carbon_credit", row["code"]),
                code=row["code"],
                type=row["type"],
                price=row["price"],
                buyer_match=row["buyer_match"],
                closure_prob=row["closure_prob"],
                traceability=row["traceability"],
                sort_order=order,
            )
        )
    report.add("carbon_credits", len(sd.CARBON_CREDITS))

    # ------------------------------------------------------------------
    # Trust ledger + compliance sidebar
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.TRUST_DECISIONS):
        await session.merge(
            TrustDecision(
                id=uid("trust_decision", row["code"]),
                code=row["code"],
                use_case=row["use_case"],
                recommendation=row["recommendation"],
                data_sources=row["data_sources"],
                confidence=row["confidence"],
                approval=TrustApproval(row["approval"]),
                risk=TrustRisk(row["risk"]),
                audit=TrustAudit(row["audit"]),
                lineage=build_lineage(row),
                sort_order=order,
            )
        )
    report.add("trust_decisions", len(sd.TRUST_DECISIONS))

    for order, row in enumerate(sd.COMPLIANCE_RULES):
        await session.merge(
            ComplianceRule(
                id=uid("compliance_rule", row["label"]),
                label=row["label"],
                status=row["status"],
                sort_order=order,
            )
        )
    report.add("compliance_rules", len(sd.COMPLIANCE_RULES))

    # ------------------------------------------------------------------
    # AI factory: agents + XR experiences
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.AI_AGENTS):
        await session.merge(
            AiAgent(
                id=uid("ai_agent", row["name"]),
                name=row["name"],
                role=row["role"],
                status=AgentStatus(row["status"]),
                last_activity=row["last_activity"],
                use_areas=row["use_areas"],
                sort_order=order,
            )
        )
    report.add("ai_agents", len(sd.AI_AGENTS))

    for order, row in enumerate(sd.XR_EXPERIENCES):
        await session.merge(
            XrExperience(
                id=uid("xr_experience", row["code"]),
                code=row["code"],
                title=row["title"],
                use_case=row["use_case"],
                feature=row["feature"],
                impact=row["impact"],
                sort_order=order,
            )
        )
    report.add("xr_experiences", len(sd.XR_EXPERIENCES))

    # ------------------------------------------------------------------
    # Mobility causal twin
    # ------------------------------------------------------------------
    for order, row in enumerate(sd.CAUSAL_NODES):
        await session.merge(
            CausalNode(
                id=uid("causal_node", row["label"]),
                label=row["label"],
                x=row["x"],
                y=row["y"],
                metric=row["metric"],
                trend=row["trend"],
                drivers=row["drivers"],
                action=row["action"],
                sort_order=order,
            )
        )
    report.add("causal_nodes", len(sd.CAUSAL_NODES))

    for order, (source, target) in enumerate(sd.CAUSAL_EDGES):
        await session.merge(
            CausalEdge(
                id=uid("causal_edge", source, target),
                source_node_id=uid("causal_node", source),
                target_node_id=uid("causal_node", target),
                sort_order=order,
            )
        )
    report.add("causal_edges", len(sd.CAUSAL_EDGES))

    for order, row in enumerate(sd.MOBILITY_KPIS):
        await session.merge(
            MobilityKpi(
                id=uid("mobility_kpi", row["label"]),
                label=row["label"],
                value=row["value"],
                trend=row["trend"],
                sort_order=order,
            )
        )
    report.add("mobility_kpis", len(sd.MOBILITY_KPIS))

    for category, qa_list in (("mobility", sd.MOBILITY_QA), ("dmrv", sd.DMRV_QA)):
        for order, row in enumerate(qa_list):
            await session.merge(
                CausalQa(
                    id=uid("causal_qa", category, row["question"]),
                    category=QaCategory(category),
                    question=row["question"],
                    answer=row["answer"],
                    sort_order=order,
                )
            )
        report.add("causal_qa", len(qa_list))

    # ------------------------------------------------------------------
    # Copilot suggested prompts + sample simulation run
    # ------------------------------------------------------------------
    for order, prompt in enumerate(sd.SUGGESTED_PROMPTS):
        await session.merge(
            SuggestedPrompt(
                id=uid("suggested_prompt", prompt),
                text=prompt,
                sort_order=order,
            )
        )
    report.add("suggested_prompts", len(sd.SUGGESTED_PROMPTS))

    sample = sd.SAMPLE_SIMULATION_RUN
    await session.merge(
        SimulationRun(
            id=uid("simulation_run", sample["domain"], "sample"),
            domain=SimulationDomain(sample["domain"]),
            inputs=sample["inputs"],
            outputs=sample["outputs"],
            confidence=sample["confidence"],
        )
    )
    report.add("simulation_runs", 1)

    await session.commit()
    logger.info("seed_complete", tables=len(report.counts), rows=report.total)
    return report
