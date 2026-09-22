"""Collections & Recovery AI Swarm: live governance state for real cases.

Lives in ``ai_state`` (see app/database/ai_state_base.py), the same
app-generated persistence domain as Simulation Center's
``simulation_runs``/``simulation_approvals``/``simulation_human_reviews``
(app/models/simulation.py) — this mirrors that decision/human-review
shape, keyed by a real ``collection_cases.collection_case_id`` string
instead of a ``simulation_runs.id`` UUID, because the "run" here already
exists as a real canonical case rather than something this app creates.

Unlike a simulation run's inputs (immutable once created, which is
exactly why ``simulation_compliance_checks`` persists a cached
evaluation), a case's effective recommendation can change across
re-decisions (e.g. escalated, then later approved with a human-modified
channel/offer) while the underlying case facts (DPD, arrears, loan
terms) stay the same — so compliance here is always recomputed live from
this decision row's own stored channel/offer choice, never cached in a
separate table (see app/services/collections.py).

There is deliberately no foreign key to ``collection_cases`` — that table
is Synthetic Data Factory-owned runtime-schema data (a different
SQLAlchemy metadata/schema entirely), the same reason canonical
``trust_decisions.target_entity_id`` has no physical FK either.

A subset of real cases already carry an immutable canonical
``trust_decisions`` row (``target_entity_type='COLLECTION_CASE'``) from
the Synthetic Data Factory's own governance history — those cases never
get a row here (see app/services/collections.py); this table only ever
holds decisions made live, from the Collections AI Swarm screen itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import TimestampMixin, uuid_pk


class CollectionCaseDecision(TimestampMixin, AiStateBase):
    """One human decision (approve/modify) against a real collection case —
    at most one row per case; re-deciding updates this same row rather
    than creating a second decision (mirrors the Trust Ledger's
    simulation-track rule of never duplicating a decision record)."""

    __tablename__ = "collection_case_decisions"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    collection_case_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # APPROVED | ESCALATED
    recommended_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recommended_offer: Mapped[str] = mapped_column(String(32), nullable=False)
    modified_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modified_offer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class CollectionCaseHumanReview(TimestampMixin, AiStateBase):
    """One "Send to Human Review" request against a real case — append-only;
    the eventual decision is still recorded via ``CollectionCaseDecision``,
    never duplicated here (mirrors ``SimulationHumanReview``)."""

    __tablename__ = "collection_case_human_reviews"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    collection_case_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reviewer_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


# Re-exported for callers that only need the type, not the whole module.
__all__ = [
    "CollectionCaseDecision",
    "CollectionCaseHumanReview",
]
