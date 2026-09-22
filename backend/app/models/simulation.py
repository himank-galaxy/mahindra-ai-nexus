"""Simulation Center: persisted runs and human approval decisions.

Lives in the derived AI-state schema (``ai_state``), not the legacy
``Base``/synthetic-runtime metadata — a simulation run is app-generated
output, analogous to ``causal_runtime_state``/``manufacturing_causal_state``,
never a Synthetic Data Factory table. See
``app/database/ai_state_base.py`` and
``docs/simulation_centre_implementation.md`` §2.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import JSONType, TimestampMixin, uuid_pk


class SimulationRun(TimestampMixin, AiStateBase):
    """One what-if run: inputs, baseline, scenario outputs, and lineage."""

    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scenario_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Baseline FY26")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    baseline_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    driver_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    recommendation_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_basis: Mapped[str] = mapped_column(String(24), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_simulation_runs_confidence_range"),
        {"schema": AI_STATE_SCHEMA},
    )


class SimulationApproval(TimestampMixin, AiStateBase):
    """One human decision (approve/reject) against a persisted run."""

    __tablename__ = "simulation_approvals"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey(f"{AI_STATE_SCHEMA}.simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class SimulationHumanReview(TimestampMixin, AiStateBase):
    """One escalation request against a persisted run — who it was routed
    to, why, and when. Append-only; the eventual decision is still
    recorded via ``SimulationApproval``, never duplicated here."""

    __tablename__ = "simulation_human_reviews"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey(f"{AI_STATE_SCHEMA}.simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class SimulationComplianceCheck(TimestampMixin, AiStateBase):
    """One compliance-rule evaluation against a persisted run — mirrors
    the real canonical ``compliance_checks`` shape (rule_code/rule_name/
    result/reason). Evaluated once by app/services/compliance_engine.py
    and cached; a run's inputs never change after creation, so this is a
    stable historical record, not a live-recomputed value."""

    __tablename__ = "simulation_compliance_checks"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey(f"{AI_STATE_SCHEMA}.simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    result: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}
