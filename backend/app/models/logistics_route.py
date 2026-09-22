"""Logistics AI Control Tower: live governance state for real shipments.

Lives in ``ai_state`` (see app/database/ai_state_base.py), mirroring
``app/models/collections_case.py``'s decision/human-review shape exactly
— keyed by a real ``shipments.shipment_id`` string instead of a
``collection_case_id``, for the same reason: the "run" here already
exists as a real canonical shipment rather than something this app
creates.

Like Collections (and unlike a simulation run's immutable inputs), a
shipment's effective recommendation can change across re-decisions (e.g.
escalated, then later approved with a human-modified route) while the
underlying shipment facts stay the same — so compliance is always
recomputed live from this decision row's own stored action, never cached
in a separate table (see app/services/operational_logistics.py).

There is deliberately no foreign key to ``shipments`` — that table is
Synthetic Data Factory-owned runtime-schema data (a different SQLAlchemy
metadata/schema entirely), the same reason canonical
``trust_decisions.target_entity_id`` has no physical FK either.

A subset of real shipments already carry an immutable canonical
``trust_decisions`` row (``target_entity_type='SHIPMENT'``, ``domain=
'LOGISTICS'``) from the Synthetic Data Factory's own governance history —
those shipments never get a row here; this table only ever holds
decisions made live, from the Logistics AI Control Tower screen itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import TimestampMixin, uuid_pk


class RouteShipmentDecision(TimestampMixin, AiStateBase):
    """One human decision (approve/modify) against a real shipment — at
    most one row per shipment; re-deciding updates this same row rather
    than creating a second decision (mirrors ``CollectionCaseDecision``)."""

    __tablename__ = "route_shipment_decisions"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # APPROVED | ESCALATED
    recommended_action: Mapped[str] = mapped_column(String(16), nullable=False)  # MAINTAIN | REROUTE
    recommended_route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modified_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    modified_route_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    modification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class RouteShipmentHumanReview(TimestampMixin, AiStateBase):
    """One "Send to Human Review" request against a real shipment —
    append-only; the eventual decision is still recorded via
    ``RouteShipmentDecision``, never duplicated here (mirrors
    ``CollectionCaseHumanReview``)."""

    __tablename__ = "route_shipment_human_reviews"

    id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reviewer_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_user")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


__all__ = [
    "RouteShipmentDecision",
    "RouteShipmentHumanReview",
]
