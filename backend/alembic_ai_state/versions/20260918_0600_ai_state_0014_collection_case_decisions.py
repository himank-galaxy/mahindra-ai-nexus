"""Add Collections AI Swarm live governance state.

Two tables mirroring the Simulation Center decision/human-review shape
(see app/models/simulation.py) but keyed by a real
``collection_cases.collection_case_id`` string rather than a generated
``simulation_runs.id``, since a real collections case is the "run" here.
No foreign key to ``collection_cases`` — that table lives in the
Synthetic Data Factory's own runtime-schema metadata, not this app's
ai_state schema (same reason canonical ``trust_decisions.target_entity_id``
has no physical FK either).

Unlike a simulation run, a case's effective recommendation can change
across re-decisions while the case facts stay the same, so there is
deliberately no compliance-check cache table here — compliance is always
recomputed live from the decision row's own stored channel/offer choice
(see app/services/collections.py).

Revision ID: ai_state_0014
Revises: ai_state_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0014"
down_revision: str | None = "ai_state_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "collection_case_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_case_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("recommended_channel", sa.String(length=32), nullable=False),
        sa.Column("recommended_offer", sa.String(length=32), nullable=False),
        sa.Column("modified_channel", sa.String(length=32), nullable=True),
        sa.Column("modified_offer", sa.String(length=32), nullable=True),
        sa.Column("modification_reason", sa.Text(), nullable=True),
        sa.Column("reviewer_role", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_collection_case_decisions"),
        sa.UniqueConstraint("collection_case_id", name="uq_ai_collection_case_decisions_case_id"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_collection_case_decisions_case_id",
        "collection_case_decisions",
        ["collection_case_id"],
        schema=AI_STATE_SCHEMA,
    )

    op.create_table(
        "collection_case_human_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_case_id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_collection_case_human_reviews"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_collection_case_human_reviews_case_id",
        "collection_case_human_reviews",
        ["collection_case_id"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("collection_case_human_reviews", schema=AI_STATE_SCHEMA)
    op.drop_table("collection_case_decisions", schema=AI_STATE_SCHEMA)
