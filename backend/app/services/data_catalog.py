"""Screen/module to runtime-dataset catalog for the Data explorer.

The catalog mirrors the reviewed ``docs/Data_Dictionary.docx`` mapping while
keeping the API independent of a Word-document parser at runtime. A dataset
may be listed under several modules, and every runtime table is accounted for
either by an application module or by ``Other Supporting Datasets``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.database.runtime_schema import runtime_tables

DIRECT = "DIRECT"
SUPPORTING = "SUPPORTING"
LINEAGE = "LINEAGE"
REFERENCE = "REFERENCE"
GOVERNANCE = "GOVERNANCE"
EVALUATION = "EVALUATION"


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    label: str
    route: str | None
    description: str


@dataclass(frozen=True)
class DatasetLink:
    module_id: str
    relationship_type: str


@dataclass(frozen=True)
class DatasetSpec:
    id: str
    display_name: str
    table_name: str
    timestamp_column: str | None
    refresh_mode: str
    links: tuple[DatasetLink, ...]
    description: str


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec("overview", "Executive Overview", "/", "Group-wide AI cockpit and recommendation metrics."),
    ModuleSpec(
        "mobility-twin",
        "Auto Mobility Twin",
        "/mobility-twin",
        "Demand, production, dealer and customer causal intelligence.",
    ),
    ModuleSpec(
        "warranty-quality", "Warranty & Quality", "/warranty-quality", "Early-warning, evidence and production lineage."
    ),
    ModuleSpec("catalogue", "AI Solution Catalogue", "/catalogue", "Solution and proof-of-concept catalogue content."),
    ModuleSpec("simulation", "Simulation Center", "/simulation", "Scenario controls and causal simulation inputs."),
    ModuleSpec("dealer", "Dealer Revenue Optimizer", "/dealer", "Dealer funnel, lead and booking operations."),
    ModuleSpec("finance", "Financial Services", "/finance", "Retail and SME lending intelligence."),
    ModuleSpec(
        "collections", "Collections AI Swarm", "/collections", "Delinquency case management and recovery operations."
    ),
    ModuleSpec("logistics", "Logistics Control Tower", "/logistics", "Freight shipment and warehouse operations."),
    ModuleSpec("circularity", "Circular Economy", "/circularity", "ELV, RVSF, dMRV and carbon-credit operations."),
    ModuleSpec("xr", "AR/VR Experience", "/xr", "AR/VR experience catalogue and usage analytics."),
    ModuleSpec("trust", "Compliance Trust Ledger", "/trust", "Governance, compliance and audited AI decisions."),
    ModuleSpec("agents", "AI Factory Agents", "/agents", "Agent registry and governed workflow activity."),
    ModuleSpec("copilot", "Analytics Copilot", "/copilot", "Copilot prompts and evaluation support."),
    ModuleSpec(
        "other-supporting",
        "Other Supporting Datasets",
        None,
        "Reference, lineage, governance, evaluation and future-use datasets.",
    ),
)


def _link(module_id: str, relationship_type: str = DIRECT) -> DatasetLink:
    return DatasetLink(module_id, relationship_type)


DATASET_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        "agent_events",
        "Agent Runtime Events",
        "agent_events",
        "completed_at",
        "INGESTED",
        (_link("agents"), _link("other-supporting", SUPPORTING)),
        "Agent registry activity and governed workflow events.",
    ),
    DatasetSpec(
        "agent_workflow_runs",
        "Agent Workflow Runs",
        "agent_workflow_runs",
        "completed_at",
        "STATIC",
        (_link("agents", SUPPORTING), _link("other-supporting", GOVERNANCE)),
        "Workflow-run support records; the current Agents animation does not query this table.",
    ),
    DatasetSpec(
        "allocations",
        "Allocations",
        "allocations",
        "allocation_date",
        "STATIC",
        (_link("dealer", SUPPORTING), _link("overview", SUPPORTING), _link("other-supporting", SUPPORTING)),
        "Vehicle allocation and recommendation-evidence support.",
    ),
    DatasetSpec(
        "bookings",
        "Bookings",
        "bookings",
        "booking_timestamp",
        "STATIC",
        (_link("dealer"), _link("overview")),
        "Auto sales bookings used by dealer and overview metrics.",
    ),
    DatasetSpec(
        "cancellations",
        "Cancellations",
        "cancellations",
        "cancelled_at",
        "STATIC",
        (_link("dealer"), _link("overview")),
        "Booking cancellation and leakage evidence.",
    ),
    DatasetSpec(
        "customers",
        "Customers",
        "customers",
        "created_at",
        "STATIC",
        (_link("other-supporting", REFERENCE),),
        "Customer master/reference records; current screens use denormalized fields instead.",
    ),
    DatasetSpec(
        "deliveries",
        "Deliveries",
        "deliveries",
        "actual_delivery_date",
        "STATIC",
        (_link("warranty-quality", SUPPORTING), _link("other-supporting", LINEAGE)),
        "Delivery lineage used to gate field-telematics visibility.",
    ),
    DatasetSpec(
        "finance_applications",
        "Finance Applications (Auto)",
        "finance_applications",
        "submitted_at",
        "STATIC",
        (_link("overview"),),
        "Auto-finance decisions used by Executive Overview risk metrics.",
    ),
    DatasetSpec(
        "followups",
        "Followups",
        "followups",
        "scheduled_at",
        "STATIC",
        (_link("dealer"),),
        "Dealer follow-up activity and SLA evidence.",
    ),
    DatasetSpec(
        "leads",
        "Leads",
        "leads",
        "lead_created_at",
        "STATIC",
        (_link("dealer"),),
        "Dealer lead prioritization and intent scores.",
    ),
    DatasetSpec(
        "production_batches",
        "Production Batches",
        "production_batches",
        "production_date",
        "STATIC",
        (_link("warranty-quality", LINEAGE), _link("other-supporting", LINEAGE)),
        "Production batch lineage and manufacturing reference data.",
    ),
    DatasetSpec(
        "service_events",
        "Service Events",
        "service_events",
        "service_started_at",
        "INGESTED",
        (_link("warranty-quality"),),
        "Service complaints, repairs and early-warning evidence.",
    ),
    DatasetSpec(
        "supplier_lots",
        "Supplier Lots",
        "supplier_lots",
        "received_at",
        "STATIC",
        (_link("warranty-quality", LINEAGE), _link("other-supporting", REFERENCE)),
        "Supplier-lot lineage and quality reference data.",
    ),
    DatasetSpec(
        "suppliers",
        "Suppliers",
        "suppliers",
        None,
        "STATIC",
        (_link("warranty-quality", REFERENCE), _link("other-supporting", REFERENCE)),
        "Supplier master/reference records.",
    ),
    DatasetSpec(
        "test_drives",
        "Test Drives",
        "test_drives",
        "requested_at",
        "STATIC",
        (_link("dealer"),),
        "Dealer test-drive requests, completion and wait evidence.",
    ),
    DatasetSpec(
        "warranty_claims",
        "Warranty Claims",
        "warranty_claims",
        "claim_submitted_at",
        "INGESTED",
        (_link("warranty-quality"),),
        "Warranty exposure, supplier and market hotspot evidence.",
    ),
    DatasetSpec(
        "manufacturing_timeseries",
        "Manufacturing Time-Series",
        "manufacturing_timeseries",
        "timestamp",
        "LIVE",
        (_link("warranty-quality"),),
        "Minute-level manufacturing sensor observations and causal inputs.",
    ),
    DatasetSpec(
        "mobility_timeseries",
        "Auto Mobility Business Time Series",
        "mobility_timeseries",
        "window_start",
        "STATIC",
        (_link("mobility-twin"),),
        "Business-funnel time windows used by the Auto Mobility Twin.",
    ),
    DatasetSpec(
        "vehicle_telematics_timeseries",
        "Vehicle Telematics Time-Series",
        "vehicle_telematics_timeseries",
        "timestamp",
        "LIVE",
        (_link("warranty-quality"),),
        "Minute-level vehicle sensor observations and causal inputs.",
    ),
    DatasetSpec(
        "credit_listings",
        "Carbon Credit Listings",
        "credit_listings",
        "listing_at",
        "STATIC",
        (_link("circularity"),),
        "Carbon-credit marketplace listings and closure evidence.",
    ),
    DatasetSpec(
        "dmrv_records",
        "dMRV Records",
        "dmrv_records",
        "dmrv_recorded_at",
        "STATIC",
        (_link("circularity"), _link("overview", SUPPORTING)),
        "Digital measurement, reporting and verification evidence.",
    ),
    DatasetSpec(
        "elv_assessments",
        "ELV Assessments",
        "elv_assessments",
        "assessment_at",
        "STATIC",
        (_link("circularity", SUPPORTING),),
        "ELV intake and assessment records; the current price card is client-side calculated.",
    ),
    DatasetSpec(
        "rvsf_job_cards",
        "RVSF Job Cards",
        "rvsf_job_cards",
        "job_opened_at",
        "STATIC",
        (_link("circularity"),),
        "RVSF processing, recovery and quality records.",
    ),
    DatasetSpec(
        "collection_cases",
        "Collection Cases",
        "collection_cases",
        "case_created_at",
        "STATIC",
        (_link("collections"),),
        "Prioritized delinquency cases and arrears state.",
    ),
    DatasetSpec(
        "collection_interactions",
        "Collection Interactions",
        "collection_interactions",
        "interaction_at",
        "STATIC",
        (_link("collections"),),
        "Collector contact history, promises and payment outcomes.",
    ),
    DatasetSpec(
        "copilot_eval_questions",
        "Copilot Evaluation Question Bank",
        "copilot_eval_questions",
        "generated_at",
        "STATIC",
        (_link("copilot", EVALUATION), _link("other-supporting", EVALUATION)),
        "Analytics Copilot evaluation and routing cases.",
    ),
    DatasetSpec(
        "suggested_prompts",
        "Suggested Prompt",
        "suggested_prompts",
        None,
        "STATIC",
        (_link("copilot"),),
        "Enabled prompt chips displayed by Analytics Copilot.",
    ),
    DatasetSpec(
        "cross_sell_events",
        "Cross-Sell Events",
        "cross_sell_events",
        "offered_at",
        "STATIC",
        (_link("finance"),),
        "Finance cross-sell offers and customer responses.",
    ),
    DatasetSpec(
        "finance_customers",
        "Finance Customers",
        "finance_customers",
        "customer_since",
        "STATIC",
        (_link("finance"),),
        "Customer financial profile and income-stability inputs.",
    ),
    DatasetSpec(
        "loan_accounts",
        "Loan Accounts",
        "loan_accounts",
        "application_at",
        "STATIC",
        (_link("finance"), _link("collections", SUPPORTING)),
        "Loan book, product holdings and collection relationship data.",
    ),
    DatasetSpec(
        "payment_history",
        "Payment History",
        "payment_history",
        "payment_due_at",
        "STATIC",
        (_link("finance"), _link("collections")),
        "Repayment, DPD and arrears-recovery events.",
    ),
    DatasetSpec(
        "action_outcomes",
        "Action Outcomes",
        "action_outcomes",
        "observed_at",
        "STATIC",
        (_link("agents", GOVERNANCE), _link("trust", GOVERNANCE), _link("other-supporting", GOVERNANCE)),
        "Governed action and business-outcome support records.",
    ),
    DatasetSpec(
        "audit_events",
        "Immutable Audit Log",
        "audit_events",
        "event_at",
        "STATIC",
        (_link("trust", GOVERNANCE), _link("other-supporting", GOVERNANCE)),
        "Immutable recommendation-to-action audit-chain support.",
    ),
    DatasetSpec(
        "compliance_checks",
        "Compliance Rule Checks",
        "compliance_checks",
        "checked_at",
        "STATIC",
        (_link("trust"),),
        "Compliance rule outcomes shown by the Trust screen.",
    ),
    DatasetSpec(
        "human_reviews",
        "Human Reviews",
        "human_reviews",
        "requested_at",
        "STATIC",
        (_link("trust", GOVERNANCE), _link("other-supporting", GOVERNANCE)),
        "Human-review workflow support records.",
    ),
    DatasetSpec(
        "recommendations",
        "AI Recommendations (Governance)",
        "recommendations",
        "generated_at",
        "STATIC",
        (
            _link("overview", GOVERNANCE),
            _link("trust", GOVERNANCE),
            _link("agents", GOVERNANCE),
            _link("other-supporting", GOVERNANCE),
        ),
        "Governance recommendation records and evidence snapshots.",
    ),
    DatasetSpec(
        "trust_decisions",
        "Compliance Trust Ledger",
        "trust_decisions",
        "decided_at",
        "STATIC",
        (_link("trust"),),
        "Audited AI decision records.",
    ),
    DatasetSpec(
        "shipments",
        "Shipment Records",
        "shipments",
        "dispatch_time",
        "STATIC",
        (_link("logistics"), _link("overview", SUPPORTING)),
        "Freight shipment, delay and SLA evidence.",
    ),
    DatasetSpec(
        "warehouse_events",
        "Warehouse Events",
        "warehouse_events",
        "event_at",
        "STATIC",
        (_link("logistics"),),
        "Warehouse touchpoints, congestion and dock-wait records.",
    ),
    DatasetSpec(
        "cities",
        "Cities",
        "cities",
        None,
        "STATIC",
        (_link("other-supporting", REFERENCE),),
        "Geography master data; operational screens use denormalized city fields.",
    ),
    DatasetSpec(
        "dealers",
        "Dealers",
        "dealers",
        None,
        "STATIC",
        (_link("dealer"),),
        "Dealer selector and capacity reference data.",
    ),
    DatasetSpec(
        "finance_products",
        "Finance Products",
        "finance_products",
        None,
        "STATIC",
        (_link("finance"),),
        "Finance product portfolio reference and metrics.",
    ),
    DatasetSpec(
        "machines",
        "Machines",
        "machines",
        None,
        "STATIC",
        (_link("warranty-quality", SUPPORTING), _link("other-supporting", REFERENCE)),
        "Machine master data used to expand causal cohorts.",
    ),
    DatasetSpec(
        "plants",
        "Plants",
        "plants",
        None,
        "STATIC",
        (_link("warranty-quality", REFERENCE), _link("other-supporting", REFERENCE)),
        "Plant master/reference data.",
    ),
    DatasetSpec(
        "production_lines",
        "Production Lines",
        "production_lines",
        None,
        "STATIC",
        (_link("warranty-quality", SUPPORTING), _link("other-supporting", REFERENCE)),
        "Production-line taxonomy and causal-scope reference data.",
    ),
    DatasetSpec(
        "regions",
        "Regions",
        "regions",
        None,
        "STATIC",
        (_link("simulation"),),
        "Region selector and generation-weight reference data.",
    ),
    DatasetSpec(
        "routes",
        "Logistics Route Master",
        "routes",
        None,
        "STATIC",
        (_link("logistics"),),
        "Freight corridor and route reference data.",
    ),
    DatasetSpec(
        "vehicle_models",
        "Vehicle Models",
        "vehicle_models",
        None,
        "STATIC",
        (_link("dealer"), _link("simulation")),
        "Vehicle model selector and commercial reference data.",
    ),
    DatasetSpec(
        "warehouses",
        "Warehouse Master",
        "warehouses",
        None,
        "STATIC",
        (_link("logistics"),),
        "Warehouse reference and capacity data.",
    ),
    DatasetSpec(
        "xr_experiences",
        "XR Experience Catalog",
        "xr_experiences",
        None,
        "STATIC",
        (_link("xr"),),
        "AR/VR experience cards and capability metadata.",
    ),
    DatasetSpec(
        "xr_sessions",
        "XR Session Records",
        "xr_sessions",
        "started_at",
        "STATIC",
        (_link("xr", SUPPORTING), _link("other-supporting", SUPPORTING)),
        "XR usage and engagement analytics support records.",
    ),
)


MODULE_BY_ID = {module.id: module for module in MODULES}
DATASET_BY_ID = {dataset.id: dataset for dataset in DATASET_SPECS}


def validate_catalog() -> None:
    """Fail fast if the catalog drifts from the fixed runtime schema."""
    runtime_ids = set(runtime_tables)
    catalog_ids = set(DATASET_BY_ID)
    if runtime_ids != catalog_ids:
        missing = sorted(runtime_ids - catalog_ids)
        unknown = sorted(catalog_ids - runtime_ids)
        raise RuntimeError(f"Data catalog/runtime mismatch: missing={missing}, unknown={unknown}")
    for dataset in DATASET_SPECS:
        for link in dataset.links:
            if link.module_id not in MODULE_BY_ID:
                raise RuntimeError(f"Unknown data catalog module: {link.module_id}")
        if dataset.timestamp_column and dataset.timestamp_column not in runtime_tables[dataset.table_name].c:
            raise RuntimeError(f"Unknown timestamp column for {dataset.id}: {dataset.timestamp_column}")


validate_catalog()


def datasets_for_module(module_id: str) -> tuple[DatasetSpec, ...]:
    return tuple(dataset for dataset in DATASET_SPECS if any(link.module_id == module_id for link in dataset.links))


__all__ = [
    "DATASET_BY_ID",
    "DATASET_SPECS",
    "DIRECT",
    "DatasetLink",
    "DatasetSpec",
    "EVALUATION",
    "GOVERNANCE",
    "LINEAGE",
    "MODULES",
    "MODULE_BY_ID",
    "REFERENCE",
    "SUPPORTING",
    "datasets_for_module",
    "validate_catalog",
]
