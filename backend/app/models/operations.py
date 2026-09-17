"""Operational business records used as the data source for all dashboards.

These tables deliberately model events and entities, rather than the cards
shown in the UI.  Legacy ``kpis``/``mobility_kpis``/``warehouse_signals``
tables remain available for a reversible migration, but no new runtime path
should depend on them.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk


class BusinessDealer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Canonical synthetic dealer master, separate from legacy card rows."""

    __tablename__ = "business_dealers"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    bay_capacity: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(96), unique=True)


class BusinessLead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Lead-level facts from which dealer-funnel metrics are calculated."""

    __tablename__ = "business_leads"

    lead_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    lead_score: Mapped[int] = mapped_column(Integer)
    lead_quality: Mapped[float] = mapped_column(Float)
    source_channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    followup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("lead_score BETWEEN 0 AND 100", name="business_lead_score_range"),
        CheckConstraint("lead_quality BETWEEN 0 AND 1", name="business_lead_quality_range"),
    )


class BusinessCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Customer master for linked bookings, finance and collections events."""

    __tablename__ = "business_customers"

    customer_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    city: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(32))
    income_stability: Mapped[str] = mapped_column(String(32))
    risk_band: Mapped[str] = mapped_column(String(16))


class FinanceApplication(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Finance decision facts; approval/TAT values are not UI-card copies."""

    __tablename__ = "finance_applications"

    application_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_customers.id", ondelete="RESTRICT"), index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amount: Mapped[float] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(24), index=True)
    approval_tat_hours: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)

    __table_args__ = (CheckConstraint("risk_score BETWEEN 0 AND 1", name="finance_application_risk_score_range"),)


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Historical booking transaction."""

    __tablename__ = "bookings"

    booking_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(uuid_pk(), ForeignKey("business_leads.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(uuid_pk(), ForeignKey("business_customers.id", ondelete="SET NULL"), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    booking_value: Mapped[float] = mapped_column(Numeric(14, 2))
    finance_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    source_channel: Mapped[str] = mapped_column(String(32))


class TestDrive(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Test-drive request/schedule/completion event."""

    __tablename__ = "test_drives"

    test_drive_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_leads.id", ondelete="RESTRICT"), index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), index=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_response: Mapped[str] = mapped_column(String(24))


class Cancellation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Booking cancellation and contributing operational reasons."""

    __tablename__ = "cancellations"

    cancellation_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("bookings.id", ondelete="RESTRICT"), unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str] = mapped_column(String(48), index=True)
    finance_delay: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_delay: Mapped[bool] = mapped_column(Boolean, default=False)
    competitor_offer: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_change: Mapped[bool] = mapped_column(Boolean, default=False)
    dealer_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    refund_status: Mapped[str] = mapped_column(String(24))


class VehicleAllocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dealer/model allocation event used for imbalance and wait-list analysis."""

    __tablename__ = "vehicle_allocations"

    allocation_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    requested_units: Mapped[int] = mapped_column(Integer)
    allocated_units: Mapped[int] = mapped_column(Integer)
    available_inventory: Mapped[int] = mapped_column(Integer)
    waiting_list: Mapped[int] = mapped_column(Integer)
    allocation_status: Mapped[str] = mapped_column(String(24), index=True)

    __table_args__ = (
        CheckConstraint("requested_units >= 0", name="allocation_requested_units_nonnegative"),
        CheckConstraint("allocated_units >= 0", name="allocation_allocated_units_nonnegative"),
    )


class Shipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Shipment-level logistics event; route cards are aggregated from this."""

    __tablename__ = "shipments"

    shipment_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    route_name: Mapped[str] = mapped_column(String(128), index=True)
    origin: Mapped[str] = mapped_column(String(64))
    destination: Mapped[str] = mapped_column(String(64))
    warehouse: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    units: Mapped[int] = mapped_column(Integer)
    dispatch_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expected_arrival: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delay_minutes: Mapped[int] = mapped_column(Integer)
    delay_reason: Mapped[str | None] = mapped_column(String(48))
    sla_status: Mapped[str] = mapped_column(String(24), index=True)
    risk_score: Mapped[float] = mapped_column(Float)

    __table_args__ = (CheckConstraint("risk_score BETWEEN 0 AND 1", name="shipment_risk_score_range"),)


class ElvAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """End-of-life vehicle assessment with financially meaningful components."""

    __tablename__ = "elv_assessments"

    assessment_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    vehicle_code: Mapped[str] = mapped_column(String(64), unique=True)
    vehicle_type: Mapped[str] = mapped_column(String(64))
    vehicle_age_years: Mapped[int] = mapped_column(Integer)
    condition_score: Mapped[float] = mapped_column(Float)
    documents_complete: Mapped[bool] = mapped_column(Boolean)
    scrap_value: Mapped[float] = mapped_column(Numeric(12, 2))
    recoverable_value: Mapped[float] = mapped_column(Numeric(12, 2))
    recommended_elv_price: Mapped[float] = mapped_column(Numeric(12, 2))
    risk_flags: Mapped[list[str]] = mapped_column(JSONType)
    assessment_date: Mapped[date] = mapped_column(Date, index=True)

    __table_args__ = (CheckConstraint("condition_score BETWEEN 0 AND 100", name="elv_condition_score_range"),)


class RvsfJobCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """RVSF processing job-card; operational timings produce RVSF metrics."""

    __tablename__ = "rvsf_job_cards"

    job_card_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    facility_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_code: Mapped[str] = mapped_column(String(64), index=True)
    created_at_operational: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at_operational: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_stage: Mapped[str] = mapped_column(String(32), index=True)
    de_pollution_minutes: Mapped[int] = mapped_column(Integer)
    dismantling_minutes: Mapped[int] = mapped_column(Integer)
    throughput_status: Mapped[str] = mapped_column(String(24), index=True)
    bottleneck: Mapped[str | None] = mapped_column(String(48))
    compliance_status: Mapped[str] = mapped_column(String(24), index=True)
    dmrv_completion: Mapped[float] = mapped_column(Float)

    __table_args__ = (CheckConstraint("dmrv_completion BETWEEN 0 AND 1", name="rvsf_dmrv_completion_range"),)


class DmrvRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Structured dMRV evidence record used by the circularity copilot."""

    __tablename__ = "dmrv_records"

    dmrv_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    facility_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_code: Mapped[str] = mapped_column(String(64), index=True)
    material_type: Mapped[str] = mapped_column(String(48), index=True)
    material_weight_kg: Mapped[float] = mapped_column(Float)
    recovery_percentage: Mapped[float] = mapped_column(Float)
    carbon_credit_estimate: Mapped[float] = mapped_column(Float)
    verification_status: Mapped[str] = mapped_column(String(24), index=True)
    document_completeness: Mapped[float] = mapped_column(Float)
    evidence_reference: Mapped[str] = mapped_column(String(128))
    audit_status: Mapped[str] = mapped_column(String(24), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("recovery_percentage BETWEEN 0 AND 100", name="dmrv_recovery_percentage_range"),
        CheckConstraint("document_completeness BETWEEN 0 AND 1", name="dmrv_document_completeness_range"),
    )


class CausalTimeSeries(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Daily multivariate causal-discovery input, never a stored graph output."""

    __tablename__ = "causal_timeseries"

    observed_on: Mapped[date] = mapped_column(Date, index=True)
    dealer_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("business_dealers.id", ondelete="RESTRICT"), index=True)
    region: Mapped[str] = mapped_column(String(32), index=True)
    city: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    campaign_spend: Mapped[float] = mapped_column(Numeric(14, 2))
    lead_volume: Mapped[int] = mapped_column(Integer)
    lead_quality: Mapped[float] = mapped_column(Float)
    dealer_followup_rate: Mapped[float] = mapped_column(Float)
    test_drive_requests: Mapped[int] = mapped_column(Integer)
    test_drive_completion_rate: Mapped[float] = mapped_column(Float)
    booking_count: Mapped[int] = mapped_column(Integer)
    booking_conversion_rate: Mapped[float] = mapped_column(Float)
    finance_application_count: Mapped[int] = mapped_column(Integer)
    finance_approval_rate: Mapped[float] = mapped_column(Float)
    vehicle_allocation_count: Mapped[int] = mapped_column(Integer)
    allocation_delay_days: Mapped[float] = mapped_column(Float)
    delivery_delay_days: Mapped[float] = mapped_column(Float)
    cancellation_count: Mapped[int] = mapped_column(Integer)
    cancellation_rate: Mapped[float] = mapped_column(Float)
    customer_satisfaction: Mapped[float] = mapped_column(Float)
    service_experience: Mapped[float] = mapped_column(Float)
    warranty_claim_count: Mapped[int] = mapped_column(Integer)
    warranty_claim_rate: Mapped[float] = mapped_column(Float)
    repeat_purchase_rate: Mapped[float] = mapped_column(Float)
    revenue: Mapped[float] = mapped_column(Numeric(14, 2))

    __table_args__ = (
        UniqueConstraint("observed_on", "dealer_id", "vehicle_model", name="uq_causal_timeseries_grain"),
        CheckConstraint("lead_quality BETWEEN 0 AND 1", name="causal_lead_quality_range"),
        CheckConstraint("dealer_followup_rate BETWEEN 0 AND 1", name="causal_followup_rate_range"),
        CheckConstraint("test_drive_completion_rate BETWEEN 0 AND 1", name="causal_test_drive_completion_range"),
        CheckConstraint("booking_conversion_rate BETWEEN 0 AND 1", name="causal_booking_conversion_range"),
        CheckConstraint("finance_approval_rate BETWEEN 0 AND 1", name="causal_finance_approval_range"),
        CheckConstraint("cancellation_rate BETWEEN 0 AND 1", name="causal_cancellation_rate_range"),
        CheckConstraint("repeat_purchase_rate BETWEEN 0 AND 1", name="causal_repeat_purchase_rate_range"),
    )
