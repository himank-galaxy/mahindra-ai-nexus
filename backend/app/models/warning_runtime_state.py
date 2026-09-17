"""Persisted early-warning evaluations and lifecycle state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import JSONType, TimestampMixin, uuid_pk


class WarrantyQualityEvaluationRun(TimestampMixin, AiStateBase):
    """One deterministic warning snapshot keyed by its causal/evidence signature."""

    __tablename__ = "warranty_quality_evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    evaluation_signature: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    simulation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    manufacturing_causal_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    telematics_causal_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    field_evidence_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manufacturing_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telematics_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lifecycle_counts: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class WarrantyQualityWarning(TimestampMixin, AiStateBase):
    """Current lifecycle row for one logical issue-category warning."""

    __tablename__ = "warranty_quality_warnings"

    warning_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    warning_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_category: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_transition_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class WarrantyQualityWarningEvent(TimestampMixin, AiStateBase):
    """Auditable lifecycle transition; unchanged observations create no event."""

    __tablename__ = "warranty_quality_warning_events"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    warning_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_state: Mapped[str] = mapped_column(String(32), nullable=False)
    warning_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


__all__ = [
    "WarrantyQualityEvaluationRun",
    "WarrantyQualityWarning",
    "WarrantyQualityWarningEvent",
]
