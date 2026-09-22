"""Add Logistics AI Control Tower live governance state.

Two tables mirroring the Collections AI Swarm decision/human-review
shape (see app/models/collections_case.py) but keyed by a real
``shipments.shipment_id`` string rather than a ``collection_case_id``,
since a real shipment is the "case" here. No foreign key to ``shipments``
— that table lives in the Synthetic Data Factory's own runtime-schema
metadata, not this app's ai_state schema (same reason canonical
``trust_decisions.target_entity_id`` has no physical FK either).

Revision ID: ai_state_0015
Revises: ai_state_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0015"
down_revision: str | None = "ai_state_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "route_shipment_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("recommended_action", sa.String(length=16), nullable=False),
        sa.Column("recommended_route_id", sa.String(length=64), nullable=True),
        sa.Column("modified_action", sa.String(length=16), nullable=True),
        sa.Column("modified_route_id", sa.String(length=64), nullable=True),
        sa.Column("modification_reason", sa.Text(), nullable=True),
        sa.Column("reviewer_role", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_route_shipment_decisions"),
        sa.UniqueConstraint("shipment_id", name="uq_ai_route_shipment_decisions_shipment_id"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_route_shipment_decisions_shipment_id",
        "route_shipment_decisions",
        ["shipment_id"],
        schema=AI_STATE_SCHEMA,
    )

    op.create_table(
        "route_shipment_human_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shipment_id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_route_shipment_human_reviews"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_route_shipment_human_reviews_shipment_id",
        "route_shipment_human_reviews",
        ["shipment_id"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("route_shipment_human_reviews", schema=AI_STATE_SCHEMA)
    op.drop_table("route_shipment_decisions", schema=AI_STATE_SCHEMA)
