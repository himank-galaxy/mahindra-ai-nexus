"""Metadata integrity: ORM registry matches the planned schema."""

from __future__ import annotations

from app.database.base import Base, SoftDeleteMixin
from app.database.seed import SEEDED_TABLES
from app.models import (  # noqa: F401 — importing registers all tables
    AiAgent,
    CarbonCredit,
    CausalEdge,
    CausalNode,
    CausalQa,
    CollectionsAgent,
    CollectionsCase,
    ComplianceRule,
    CopilotMessage,
    CopilotSession,
    CustomerTwin,
    Dealer,
    DealerLead,
    FinanceProduct,
    Kpi,
    KpiDriver,
    LogisticsRoute,
    MobilityKpi,
    PocItem,
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

EXPECTED_TABLE_COUNT = 30

# Tables carrying the soft-delete tombstone (implementation_plan.md §7).
SOFT_DELETE_TABLES = {
    "recommendations",
    "dealer_leads",
    "collections_cases",
    "carbon_credits",
    "trust_decisions",
    "poc_items",
}

SOFT_DELETE_MODELS = (
    Recommendation,
    DealerLead,
    CollectionsCase,
    CarbonCredit,
    TrustDecision,
    PocItem,
)


def test_table_count_matches_plan() -> None:
    assert len(Base.metadata.tables) == EXPECTED_TABLE_COUNT


def test_seeded_tables_all_exist_in_metadata() -> None:
    missing = set(SEEDED_TABLES) - set(Base.metadata.tables)
    assert not missing


def test_soft_delete_tables_carry_deleted_at() -> None:
    for table_name in SOFT_DELETE_TABLES:
        assert "deleted_at" in Base.metadata.tables[table_name].columns


def test_soft_delete_models_expose_is_deleted() -> None:
    for model in SOFT_DELETE_MODELS:
        assert issubclass(model, SoftDeleteMixin)


def test_audit_columns_present_on_uuid_tables() -> None:
    for table in Base.metadata.tables.values():
        if table.name in {"regions", "vehicle_models"}:  # natural-key references
            continue
        assert "created_at" in table.columns, table.name
        assert "updated_at" in table.columns, table.name
