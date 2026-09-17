"""Persisted derived state for the independent vehicle-telematics graph."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk


class TelematicsCausalRun(UUIDPrimaryKeyMixin, TimestampMixin, AiStateBase):
    """One independent per-vehicle PCMCI/stability execution."""

    __tablename__ = "telematics_causal_runs"

    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    source_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_rows: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vehicles_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicles_evaluated: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_pairs: Mapped[int] = mapped_column(Integer, nullable=False)
    stable_edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    vehicle_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("signature", name="uq_ai_telematics_runs_signature"),
        CheckConstraint("source_rows >= 1", name="ai_telematics_runs_source_rows"),
        CheckConstraint("vehicles_requested >= 1", name="ai_telematics_runs_requested"),
        CheckConstraint("vehicles_evaluated >= 1", name="ai_telematics_runs_evaluated"),
        CheckConstraint("vehicles_evaluated <= vehicles_requested", name="ai_telematics_runs_vehicle_counts"),
        CheckConstraint("candidate_pairs >= 0", name="ai_telematics_runs_candidate_pairs"),
        CheckConstraint("stable_edge_count >= 0", name="ai_telematics_runs_stable_edges"),
        {"schema": AI_STATE_SCHEMA},
    )


class TelematicsCausalEdge(UUIDPrimaryKeyMixin, TimestampMixin, AiStateBase):
    """Stable discovered relationship across eligible vehicles."""

    __tablename__ = "telematics_causal_edges"

    run_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey(
            f"{AI_STATE_SCHEMA}.telematics_causal_runs.id",
            ondelete="CASCADE",
            name="fk_ai_telematics_edges_run",
        ),
        nullable=False,
    )
    source_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    target_metric: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    consensus_sign: Mapped[str] = mapped_column(String(1), nullable=False)
    edge_orientation: Mapped[str] = mapped_column(String(32), nullable=False, server_default="DIRECTED")
    consensus_edge_mark: Mapped[str] = mapped_column(String(3), nullable=False, server_default="-->")
    mark_agreement: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    eligible_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    recurring_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    recurrence_fraction: Mapped[float] = mapped_column(Float, nullable=False)
    sign_agreement: Mapped[float] = mapped_column(Float, nullable=False)
    mean_abs_score: Mapped[float] = mapped_column(Float, nullable=False)
    median_abs_score: Mapped[float] = mapped_column(Float, nullable=False)
    best_q_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_p_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_p_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_q_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_q_value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_lags: Mapped[list[int]] = mapped_column(JSONType, nullable=False)
    observed_lag_minutes: Mapped[list[int]] = mapped_column(JSONType, nullable=False)
    vehicle_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "source_metric", "target_metric", "scope", name="uq_ai_telematics_edges_run_pair_scope"
        ),
        CheckConstraint("source_metric <> target_metric", name="ai_telematics_edges_non_self"),
        CheckConstraint("consensus_sign IN ('+', '-')", name="ai_telematics_edges_sign"),
        CheckConstraint(
            "edge_orientation IN ('DIRECTED', 'BIDIRECTED', 'PARTIALLY_ORIENTED', 'AMBIGUOUS')", name="ck_ai_telematics_edges_orientation"
        ),
        CheckConstraint("mark_agreement >= 0 AND mark_agreement <= 1", name="ck_ai_telematics_edges_mark_agreement"),
        CheckConstraint("eligible_vehicles >= 1", name="ai_telematics_edges_eligible"),
        CheckConstraint("recurring_vehicles >= 1", name="ai_telematics_edges_recurring"),
        CheckConstraint("recurring_vehicles <= eligible_vehicles", name="ai_telematics_edges_vehicle_counts"),
        CheckConstraint("recurrence_fraction >= 0 AND recurrence_fraction <= 1", name="ai_telematics_edges_recurrence"),
        CheckConstraint("sign_agreement >= 0 AND sign_agreement <= 1", name="ai_telematics_edges_sign_agreement"),
        CheckConstraint("mean_abs_score >= 0", name="ai_telematics_edges_mean_score"),
        CheckConstraint("median_abs_score >= 0", name="ai_telematics_edges_median_score"),
        CheckConstraint("best_q_value >= 0 AND best_q_value <= 1", name="ai_telematics_edges_q_value"),
        {"schema": AI_STATE_SCHEMA},
    )


__all__ = ["TelematicsCausalEdge", "TelematicsCausalRun"]
