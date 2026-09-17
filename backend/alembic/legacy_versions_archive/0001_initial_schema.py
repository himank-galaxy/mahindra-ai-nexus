"""Initial schema: all tables, enums, indexes and constraints.

Revision ID: 0001
Revises:
Create Date: 2026-08-03

Hand-written to mirror ``app.models`` exactly (Docker was unavailable for
autogenerate at authoring time; verified via offline SQL render + live
``alembic upgrade head`` before merge).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# ENUM types. Alembic emits CREATE TYPE inline at each column's first table
# usage. AGENT_STATUS is referenced by two tables; its second usage below
# passes create_type=False to avoid a duplicate type. Downgrade drops all
# types explicitly after the tables are gone.
# ---------------------------------------------------------------------------
RECOMMENDATION_RISK = sa.Enum("low", "medium", "high", name="recommendation_risk", create_type=False)
RECOMMENDATION_STATUS = sa.Enum("pending", "approved", "under_review", name="recommendation_status", create_type=False)
DEALER_LEAD_STATUS = sa.Enum(
    "hot", "warm", "cool", "message_sent", "converted", name="dealer_lead_status", create_type=False
)
TWIN_APPROVAL_STATUS = sa.Enum("draft", "under_review", "approved", name="twin_approval_status", create_type=False)
AGENT_STATUS = sa.Enum("active", "reviewing", "recommended", name="agent_status", create_type=False)
COLLECTIONS_FLAG = sa.Enum("ok", "review", "escalate", name="collections_compliance_flag", create_type=False)
COLLECTIONS_CASE_STATUS = sa.Enum(
    "pending", "approved", "human_review", "modified", name="collections_case_status", create_type=False
)
TRUST_APPROVAL = sa.Enum(
    "approved", "human_review", "pending", "rejected", "escalated", name="trust_approval", create_type=False
)
TRUST_RISK = sa.Enum("low", "medium", "high", name="trust_risk", create_type=False)
TRUST_AUDIT = sa.Enum("complete", "pending", name="trust_audit", create_type=False)
COPILOT_ROLE = sa.Enum("user", "assistant", name="copilot_role", create_type=False)
SIMULATION_DOMAIN = sa.Enum(
    "auto_sales",
    "dealer_allocation",
    "collections",
    "logistics_delay",
    "credit_pricing",
    name="simulation_domain",
    create_type=False,
)
SIGNAL_PANEL = sa.Enum("warehouse", "collections_metrics", "rvsf", name="signal_panel", create_type=False)
QA_CATEGORY = sa.Enum("mobility", "dmrv", name="qa_category", create_type=False)

ALL_ENUMS = [
    RECOMMENDATION_RISK,
    RECOMMENDATION_STATUS,
    DEALER_LEAD_STATUS,
    TWIN_APPROVAL_STATUS,
    AGENT_STATUS,
    COLLECTIONS_FLAG,
    COLLECTIONS_CASE_STATUS,
    TRUST_APPROVAL,
    TRUST_RISK,
    TRUST_AUDIT,
    COPILOT_ROLE,
    SIMULATION_DOMAIN,
    SIGNAL_PANEL,
    QA_CATEGORY,
]

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
NOW = sa.text("now()")


def _audit_columns() -> tuple:
    """created_at / updated_at audit columns shared by every table."""
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------
    op.create_table("regions", sa.Column("code", sa.String(length=32), primary_key=True))
    op.create_table("vehicle_models", sa.Column("name", sa.String(length=64), primary_key=True))

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *_audit_columns(),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ------------------------------------------------------------------
    # Overview: KPIs, drivers, recommendations
    # ------------------------------------------------------------------
    op.create_table(
        "kpis",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=False),
        sa.Column("trend_up", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_kpis_code"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_kpis_confidence_range"),
    )
    op.create_table(
        "kpi_drivers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "kpi_id",
            UUID,
            sa.ForeignKey("kpis.id", ondelete="CASCADE", name="fk_kpi_drivers_kpi_id_kpis"),
            nullable=False,
        ),
        sa.Column("driver_text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
    )
    op.create_index("ix_kpi_drivers_kpi_id", "kpi_drivers", ["kpi_id"])
    op.create_table(
        "recommendations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("impact", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("risk", RECOMMENDATION_RISK, nullable=False, server_default="low"),
        sa.Column("status", RECOMMENDATION_STATUS, nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_recommendations_code"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_recommendations_confidence_range"),
    )
    op.create_index("ix_recommendations_deleted_at", "recommendations", ["deleted_at"])
    op.create_index(
        "ix_recommendations_status_pending",
        "recommendations",
        ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------
    op.create_table(
        "solution_buckets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_solution_buckets_name"),
    )
    op.create_index("ix_solution_buckets_tag", "solution_buckets", ["tag"])
    op.create_table(
        "solutions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "bucket_id",
            UUID,
            sa.ForeignKey("solution_buckets.id", ondelete="RESTRICT", name="fk_solutions_bucket_id_solution_buckets"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("solution", sa.Text(), nullable=False),
        sa.Column("differentiator", sa.Text(), nullable=False),
        sa.Column("impact", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_solutions_name"),
    )
    op.create_index("ix_solutions_bucket_id", "solutions", ["bucket_id"])

    # ------------------------------------------------------------------
    # Dealers
    # ------------------------------------------------------------------
    op.create_table(
        "dealers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("leads", sa.Integer(), nullable=False),
        sa.Column("hot_leads", sa.Integer(), nullable=False),
        sa.Column("test_drives_pending", sa.Integer(), nullable=False),
        sa.Column("booking_prob", sa.Integer(), nullable=False),
        sa.Column("revenue_at_risk", sa.String(length=32), nullable=False),
        sa.Column("leakage_pct", sa.Integer(), nullable=False),
        sa.Column("bay_util_pct", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_dealers_code"),
        sa.CheckConstraint("booking_prob BETWEEN 0 AND 100", name="ck_dealers_booking_prob_range"),
        sa.CheckConstraint("leakage_pct BETWEEN 0 AND 100", name="ck_dealers_leakage_pct_range"),
        sa.CheckConstraint("bay_util_pct BETWEEN 0 AND 100", name="ck_dealers_bay_util_pct_range"),
    )
    op.create_table(
        "dealer_leads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "dealer_id",
            UUID,
            sa.ForeignKey("dealers.id", ondelete="CASCADE", name="fk_dealer_leads_dealer_id_dealers"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("vehicle", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("prob", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=256), nullable=False),
        sa.Column("revenue", sa.String(length=32), nullable=False),
        sa.Column("status", DEALER_LEAD_STATUS, nullable=False, server_default="warm"),
        sa.Column("test_drive_slot", sa.String(length=64), nullable=True),
        sa.Column("message_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_dealer_leads_score_range"),
        sa.CheckConstraint("prob BETWEEN 0 AND 100", name="ck_dealer_leads_prob_range"),
    )
    op.create_index("ix_dealer_leads_dealer_id", "dealer_leads", ["dealer_id"])
    op.create_index("ix_dealer_leads_deleted_at", "dealer_leads", ["deleted_at"])

    # ------------------------------------------------------------------
    # Finance
    # ------------------------------------------------------------------
    op.create_table(
        "finance_products",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("customers", sa.String(length=32), nullable=False),
        sa.Column("risk", sa.String(length=32), nullable=False),
        sa.Column("cross_sell", sa.String(length=32), nullable=False),
        sa.Column("opportunity", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_finance_products_name"),
    )
    op.create_table(
        "customer_twins",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=False),
        sa.Column("income_stability", sa.String(length=32), nullable=False),
        sa.Column("repayment", sa.String(length=32), nullable=False),
        sa.Column("products", JSONB, nullable=False),
        sa.Column("nba", JSONB, nullable=False),
        sa.Column("risk_decomposition", JSONB, nullable=False),
        sa.Column("cross_sell", JSONB, nullable=False),
        sa.Column("approval_status", TWIN_APPROVAL_STATUS, nullable=False, server_default="draft"),
        *_audit_columns(),
    )

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------
    op.create_table(
        "collections_agents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", AGENT_STATUS, nullable=False, server_default="active"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_collections_agents_name"),
    )
    op.create_table(
        "collections_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("customer", sa.String(length=128), nullable=False),
        sa.Column("dpd", sa.Integer(), nullable=False),
        sa.Column("outstanding", sa.String(length=32), nullable=False),
        sa.Column("roll_forward_risk", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("prob", sa.Integer(), nullable=False),
        sa.Column("compliance_flag", COLLECTIONS_FLAG, nullable=False, server_default="ok"),
        sa.Column("status", COLLECTIONS_CASE_STATUS, nullable=False, server_default="pending"),
        sa.Column("modified_action", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint("roll_forward_risk BETWEEN 0 AND 100", name="ck_collections_cases_roll_forward_risk_range"),
        sa.CheckConstraint("prob BETWEEN 0 AND 100", name="ck_collections_cases_prob_range"),
    )
    op.create_index("ix_collections_cases_deleted_at", "collections_cases", ["deleted_at"])

    # ------------------------------------------------------------------
    # Logistics
    # ------------------------------------------------------------------
    op.create_table(
        "logistics_routes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sla_risk", sa.Integer(), nullable=False),
        sa.Column("delay_prob", sa.Integer(), nullable=False),
        sa.Column("cost", sa.String(length=32), nullable=False),
        sa.Column("recommended_action", sa.String(length=128), nullable=False),
        sa.Column("rerouted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rerouted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_healed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_logistics_routes_name"),
        sa.CheckConstraint("sla_risk BETWEEN 0 AND 100", name="ck_logistics_routes_sla_risk_range"),
        sa.CheckConstraint("delay_prob BETWEEN 0 AND 100", name="ck_logistics_routes_delay_prob_range"),
    )
    op.create_table(
        "warehouse_signals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("panel", SIGNAL_PANEL, nullable=False, server_default="warehouse"),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("tone", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
    )
    op.create_index("ix_warehouse_signals_panel", "warehouse_signals", ["panel"])

    # ------------------------------------------------------------------
    # Circularity
    # ------------------------------------------------------------------
    op.create_table(
        "carbon_credits",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("price", sa.String(length=32), nullable=False),
        sa.Column("buyer_match", sa.Integer(), nullable=False),
        sa.Column("closure_prob", sa.Integer(), nullable=False),
        sa.Column("traceability", sa.Integer(), nullable=False),
        sa.Column("repriced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buyer_matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_carbon_credits_code"),
        sa.CheckConstraint("buyer_match BETWEEN 0 AND 100", name="ck_carbon_credits_buyer_match_range"),
        sa.CheckConstraint("closure_prob BETWEEN 0 AND 100", name="ck_carbon_credits_closure_prob_range"),
        sa.CheckConstraint("traceability BETWEEN 0 AND 100", name="ck_carbon_credits_traceability_range"),
    )
    op.create_index("ix_carbon_credits_deleted_at", "carbon_credits", ["deleted_at"])

    # ------------------------------------------------------------------
    # Trust ledger
    # ------------------------------------------------------------------
    op.create_table(
        "trust_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("recommendation", sa.String(length=256), nullable=False),
        sa.Column("data_sources", sa.String(length=256), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("approval", TRUST_APPROVAL, nullable=False, server_default="pending"),
        sa.Column("risk", TRUST_RISK, nullable=False),
        sa.Column("audit", TRUST_AUDIT, nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("lineage", JSONB, nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_trust_decisions_code"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_trust_decisions_confidence_range"),
    )
    op.create_index("ix_trust_decisions_deleted_at", "trust_decisions", ["deleted_at"])
    op.create_table(
        "compliance_rules",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OK"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("label", name="uq_compliance_rules_label"),
    )

    # ------------------------------------------------------------------
    # AI factory agents + XR
    # ------------------------------------------------------------------
    op.create_table(
        "ai_agents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=False),
        sa.Column("status", AGENT_STATUS, nullable=False, server_default="active"),
        sa.Column("last_activity", sa.String(length=256), nullable=False),
        sa.Column("use_areas", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_ai_agents_name"),
    )
    op.create_index("ix_ai_agents_use_areas", "ai_agents", ["use_areas"], postgresql_using="gin")
    op.create_table(
        "xr_experiences",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("feature", sa.String(length=128), nullable=False),
        sa.Column("impact", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_xr_experiences_code"),
    )

    # ------------------------------------------------------------------
    # Mobility causal twin
    # ------------------------------------------------------------------
    op.create_table(
        "causal_nodes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("metric", sa.String(length=128), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=False),
        sa.Column("drivers", JSONB, nullable=False),
        sa.Column("action", sa.String(length=256), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("label", name="uq_causal_nodes_label"),
    )
    op.create_table(
        "causal_edges",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "source_node_id",
            UUID,
            sa.ForeignKey("causal_nodes.id", ondelete="CASCADE", name="fk_causal_edges_source_node_id_causal_nodes"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            UUID,
            sa.ForeignKey("causal_nodes.id", ondelete="CASCADE", name="fk_causal_edges_target_node_id_causal_nodes"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("source_node_id", "target_node_id", name="uq_causal_edges_pair"),
    )
    op.create_index("ix_causal_edges_source_node_id", "causal_edges", ["source_node_id"])
    op.create_index("ix_causal_edges_target_node_id", "causal_edges", ["target_node_id"])
    op.create_table(
        "mobility_kpis",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("trend", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("label", name="uq_mobility_kpis_label"),
    )
    op.create_table(
        "causal_qa",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("category", QA_CATEGORY, nullable=False, server_default="mobility"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
    )
    op.create_index("ix_causal_qa_category", "causal_qa", ["category"])
    op.create_index("ix_causal_qa_category_question", "causal_qa", ["category", "question"])

    # ------------------------------------------------------------------
    # PoC roadmap
    # ------------------------------------------------------------------
    op.create_table(
        "poc_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("bucket", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("complexity", sa.String(length=16), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("name", name="uq_poc_items_name"),
    )
    op.create_index("ix_poc_items_deleted_at", "poc_items", ["deleted_at"])

    # ------------------------------------------------------------------
    # Copilot
    # ------------------------------------------------------------------
    op.create_table(
        "copilot_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        *_audit_columns(),
    )
    op.create_table(
        "copilot_messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "session_id",
            UUID,
            sa.ForeignKey(
                "copilot_sessions.id", ondelete="CASCADE", name="fk_copilot_messages_session_id_copilot_sessions"
            ),
            nullable=False,
        ),
        sa.Column("role", COPILOT_ROLE, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        *_audit_columns(),
    )
    op.create_index("ix_copilot_messages_session_id", "copilot_messages", ["session_id"])
    op.create_table(
        "suggested_prompts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        *_audit_columns(),
        sa.UniqueConstraint("text", name="uq_suggested_prompts_text"),
    )

    # ------------------------------------------------------------------
    # Simulation audit
    # ------------------------------------------------------------------
    op.create_table(
        "simulation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("domain", SIMULATION_DOMAIN, nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("outputs", JSONB, nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 100", name="ck_simulation_runs_confidence_range"
        ),
    )
    op.create_index("ix_simulation_runs_domain", "simulation_runs", ["domain"])


def downgrade() -> None:
    # Tables (reverse of creation order; enums last).
    for table in [
        "simulation_runs",
        "suggested_prompts",
        "copilot_messages",
        "copilot_sessions",
        "poc_items",
        "causal_qa",
        "mobility_kpis",
        "causal_edges",
        "causal_nodes",
        "xr_experiences",
        "ai_agents",
        "compliance_rules",
        "trust_decisions",
        "carbon_credits",
        "warehouse_signals",
        "logistics_routes",
        "collections_cases",
        "collections_agents",
        "customer_twins",
        "finance_products",
        "dealer_leads",
        "dealers",
        "solutions",
        "solution_buckets",
        "recommendations",
        "kpi_drivers",
        "kpis",
        "users",
        "vehicle_models",
        "regions",
    ]:
        op.drop_table(table)

    # Types survive drop_table; remove them explicitly (safe on a clean
    # downgrade since every table referencing them is already gone).
    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
