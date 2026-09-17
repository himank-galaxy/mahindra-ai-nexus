"""Add operational synthetic-business records without touching legacy data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
NOW = sa.text("now()")


def _audit_columns() -> tuple:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "business_dealers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("bay_capacity", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(96), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_business_dealers_code"),
        sa.UniqueConstraint("name", name="uq_business_dealers_name"),
        sa.UniqueConstraint("source_key", name="uq_business_dealers_source_key"),
    )
    op.create_index("ix_business_dealers_code", "business_dealers", ["code"])
    op.create_index("ix_business_dealers_region", "business_dealers", ["region"])
    op.create_index("ix_business_dealers_city", "business_dealers", ["city"])

    op.create_table(
        "business_leads",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lead_code", sa.String(64), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("customer_name", sa.String(128), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("lead_score", sa.Integer(), nullable=False),
        sa.Column("lead_quality", sa.Float(), nullable=False),
        sa.Column("source_channel", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("followup_completed_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("lead_code", name="uq_business_leads_lead_code"),
        sa.CheckConstraint("lead_score BETWEEN 0 AND 100", name="ck_business_leads_business_lead_score_range"),
        sa.CheckConstraint("lead_quality BETWEEN 0 AND 1", name="ck_business_leads_business_lead_quality_range"),
    )
    for column in ("lead_code", "dealer_id", "vehicle_model", "status", "received_at"):
        op.create_index(f"ix_business_leads_{column}", "business_leads", [column])

    op.create_table(
        "business_customers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("income_stability", sa.String(32), nullable=False),
        sa.Column("risk_band", sa.String(16), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("customer_code", name="uq_business_customers_customer_code"),
    )
    op.create_index("ix_business_customers_customer_code", "business_customers", ["customer_code"])

    op.create_table(
        "finance_applications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("application_code", sa.String(64), nullable=False),
        sa.Column("customer_id", UUID, sa.ForeignKey("business_customers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("approval_tat_hours", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("application_code", name="uq_finance_applications_application_code"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_finance_applications_finance_application_risk_score_range"),
    )
    for column in ("application_code", "customer_id", "dealer_id", "applied_at", "status"):
        op.create_index(f"ix_finance_applications_{column}", "finance_applications", [column])

    op.create_table(
        "bookings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("booking_code", sa.String(64), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("lead_id", UUID, sa.ForeignKey("business_leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", UUID, sa.ForeignKey("business_customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("booking_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("finance_assisted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_channel", sa.String(32), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("booking_code", name="uq_bookings_booking_code"),
    )
    for column in ("booking_code", "booked_at", "dealer_id", "lead_id", "customer_id", "region", "city", "vehicle_model", "status"):
        op.create_index(f"ix_bookings_{column}", "bookings", [column])

    op.create_table(
        "test_drives",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("test_drive_code", sa.String(64), nullable=False),
        sa.Column("lead_id", UUID, sa.ForeignKey("business_leads.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("customer_response", sa.String(24), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("test_drive_code", name="uq_test_drives_test_drive_code"),
    )
    for column in ("test_drive_code", "lead_id", "dealer_id", "vehicle_model", "requested_at", "status"):
        op.create_index(f"ix_test_drives_{column}", "test_drives", [column])

    op.create_table(
        "cancellations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("cancellation_code", sa.String(64), nullable=False),
        sa.Column("booking_id", UUID, sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(48), nullable=False),
        sa.Column("finance_delay", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("delivery_delay", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("competitor_offer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("customer_change", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dealer_issue", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("refund_status", sa.String(24), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("cancellation_code", name="uq_cancellations_cancellation_code"),
        sa.UniqueConstraint("booking_id", name="uq_cancellations_booking_id"),
    )
    for column in ("cancellation_code", "booking_id", "occurred_at", "reason"):
        op.create_index(f"ix_cancellations_{column}", "cancellations", [column])

    op.create_table(
        "vehicle_allocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("allocation_code", sa.String(64), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_units", sa.Integer(), nullable=False),
        sa.Column("allocated_units", sa.Integer(), nullable=False),
        sa.Column("available_inventory", sa.Integer(), nullable=False),
        sa.Column("waiting_list", sa.Integer(), nullable=False),
        sa.Column("allocation_status", sa.String(24), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("allocation_code", name="uq_vehicle_allocations_allocation_code"),
        sa.CheckConstraint("requested_units >= 0", name="ck_vehicle_allocations_allocation_requested_units_nonnegative"),
        sa.CheckConstraint("allocated_units >= 0", name="ck_vehicle_allocations_allocation_allocated_units_nonnegative"),
    )
    for column in ("allocation_code", "dealer_id", "vehicle_model", "region", "city", "allocated_at", "allocation_status"):
        op.create_index(f"ix_vehicle_allocations_{column}", "vehicle_allocations", [column])

    op.create_table(
        "shipments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("shipment_code", sa.String(64), nullable=False),
        sa.Column("route_name", sa.String(128), nullable=False),
        sa.Column("origin", sa.String(64), nullable=False),
        sa.Column("destination", sa.String(64), nullable=False),
        sa.Column("warehouse", sa.String(64), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("dispatch_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_arrival", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_arrival", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("delay_reason", sa.String(48), nullable=True),
        sa.Column("sla_status", sa.String(24), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("shipment_code", name="uq_shipments_shipment_code"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_shipments_shipment_risk_score_range"),
    )
    for column in ("shipment_code", "route_name", "warehouse", "vehicle_model", "dispatch_time", "sla_status"):
        op.create_index(f"ix_shipments_{column}", "shipments", [column])

    op.create_table(
        "elv_assessments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assessment_code", sa.String(64), nullable=False),
        sa.Column("vehicle_code", sa.String(64), nullable=False),
        sa.Column("vehicle_type", sa.String(64), nullable=False),
        sa.Column("vehicle_age_years", sa.Integer(), nullable=False),
        sa.Column("condition_score", sa.Float(), nullable=False),
        sa.Column("documents_complete", sa.Boolean(), nullable=False),
        sa.Column("scrap_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("recoverable_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("recommended_elv_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("risk_flags", JSONB, nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("assessment_code", name="uq_elv_assessments_assessment_code"),
        sa.UniqueConstraint("vehicle_code", name="uq_elv_assessments_vehicle_code"),
        sa.CheckConstraint("condition_score BETWEEN 0 AND 100", name="ck_elv_assessments_elv_condition_score_range"),
    )
    for column in ("assessment_code", "assessment_date"):
        op.create_index(f"ix_elv_assessments_{column}", "elv_assessments", [column])

    op.create_table(
        "rvsf_job_cards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("job_card_code", sa.String(64), nullable=False),
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("vehicle_code", sa.String(64), nullable=False),
        sa.Column("created_at_operational", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_operational", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_stage", sa.String(32), nullable=False),
        sa.Column("de_pollution_minutes", sa.Integer(), nullable=False),
        sa.Column("dismantling_minutes", sa.Integer(), nullable=False),
        sa.Column("throughput_status", sa.String(24), nullable=False),
        sa.Column("bottleneck", sa.String(48), nullable=True),
        sa.Column("compliance_status", sa.String(24), nullable=False),
        sa.Column("dmrv_completion", sa.Float(), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("job_card_code", name="uq_rvsf_job_cards_job_card_code"),
        sa.CheckConstraint("dmrv_completion BETWEEN 0 AND 1", name="ck_rvsf_job_cards_rvsf_dmrv_completion_range"),
    )
    for column in ("job_card_code", "facility_id", "vehicle_code", "created_at_operational", "processing_stage", "throughput_status", "compliance_status"):
        op.create_index(f"ix_rvsf_job_cards_{column}", "rvsf_job_cards", [column])

    op.create_table(
        "dmrv_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dmrv_code", sa.String(64), nullable=False),
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("vehicle_code", sa.String(64), nullable=False),
        sa.Column("material_type", sa.String(48), nullable=False),
        sa.Column("material_weight_kg", sa.Float(), nullable=False),
        sa.Column("recovery_percentage", sa.Float(), nullable=False),
        sa.Column("carbon_credit_estimate", sa.Float(), nullable=False),
        sa.Column("verification_status", sa.String(24), nullable=False),
        sa.Column("document_completeness", sa.Float(), nullable=False),
        sa.Column("evidence_reference", sa.String(128), nullable=False),
        sa.Column("audit_status", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint("dmrv_code", name="uq_dmrv_records_dmrv_code"),
        sa.CheckConstraint("recovery_percentage BETWEEN 0 AND 100", name="ck_dmrv_records_dmrv_recovery_percentage_range"),
        sa.CheckConstraint("document_completeness BETWEEN 0 AND 1", name="ck_dmrv_records_dmrv_document_completeness_range"),
    )
    for column in ("dmrv_code", "facility_id", "vehicle_code", "material_type", "verification_status", "audit_status", "observed_at"):
        op.create_index(f"ix_dmrv_records_{column}", "dmrv_records", [column])

    op.create_table(
        "causal_timeseries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("dealer_id", UUID, sa.ForeignKey("business_dealers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("city", sa.String(64), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("campaign_spend", sa.Numeric(14, 2), nullable=False),
        sa.Column("lead_volume", sa.Integer(), nullable=False),
        sa.Column("lead_quality", sa.Float(), nullable=False),
        sa.Column("dealer_followup_rate", sa.Float(), nullable=False),
        sa.Column("test_drive_requests", sa.Integer(), nullable=False),
        sa.Column("test_drive_completion_rate", sa.Float(), nullable=False),
        sa.Column("booking_count", sa.Integer(), nullable=False),
        sa.Column("booking_conversion_rate", sa.Float(), nullable=False),
        sa.Column("finance_application_count", sa.Integer(), nullable=False),
        sa.Column("finance_approval_rate", sa.Float(), nullable=False),
        sa.Column("vehicle_allocation_count", sa.Integer(), nullable=False),
        sa.Column("allocation_delay_days", sa.Float(), nullable=False),
        sa.Column("delivery_delay_days", sa.Float(), nullable=False),
        sa.Column("cancellation_count", sa.Integer(), nullable=False),
        sa.Column("cancellation_rate", sa.Float(), nullable=False),
        sa.Column("customer_satisfaction", sa.Float(), nullable=False),
        sa.Column("service_experience", sa.Float(), nullable=False),
        sa.Column("warranty_claim_count", sa.Integer(), nullable=False),
        sa.Column("warranty_claim_rate", sa.Float(), nullable=False),
        sa.Column("repeat_purchase_rate", sa.Float(), nullable=False),
        sa.Column("revenue", sa.Numeric(14, 2), nullable=False),
        *_audit_columns(),
        sa.UniqueConstraint("observed_on", "dealer_id", "vehicle_model", name="uq_causal_timeseries_grain"),
        sa.CheckConstraint("lead_quality BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_lead_quality_range"),
        sa.CheckConstraint("dealer_followup_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_followup_rate_range"),
        sa.CheckConstraint("test_drive_completion_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_test_drive_completion_range"),
        sa.CheckConstraint("booking_conversion_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_booking_conversion_range"),
        sa.CheckConstraint("finance_approval_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_finance_approval_range"),
        sa.CheckConstraint("cancellation_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_cancellation_rate_range"),
        sa.CheckConstraint("repeat_purchase_rate BETWEEN 0 AND 1", name="ck_causal_timeseries_causal_repeat_purchase_rate_range"),
    )
    for column in ("observed_on", "dealer_id", "region", "city", "vehicle_model"):
        op.create_index(f"ix_causal_timeseries_{column}", "causal_timeseries", [column])


def downgrade() -> None:
    # This downgrade removes only the newly introduced operational tables; it
    # never touches legacy application data from revision 0001.
    for table in (
        "causal_timeseries", "dmrv_records", "rvsf_job_cards", "elv_assessments",
        "shipments", "vehicle_allocations", "cancellations", "test_drives",
        "bookings", "finance_applications", "business_customers", "business_leads",
        "business_dealers",
    ):
        op.drop_table(table)
