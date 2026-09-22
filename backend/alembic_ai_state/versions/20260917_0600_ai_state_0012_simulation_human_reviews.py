"""Add Simulation Center human-review (escalation) persistence.

One append-only row per escalation request against a persisted run —
who it was routed to, why, and when. The eventual decision (approve/
reject) is still recorded via the existing ``simulation_approvals``
table, so this never duplicates that record; it only captures the
escalation request itself. See app/models/simulation.py and the
Compliance Trust Ledger audit (2026-09-17).

Revision ID: ai_state_0012
Revises: ai_state_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0012"
down_revision: str | None = "ai_state_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "simulation_human_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_simulation_human_reviews"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{AI_STATE_SCHEMA}.simulation_runs.id"],
            name="fk_ai_simulation_human_reviews_run_id",
            ondelete="CASCADE",
        ),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_simulation_human_reviews_run_id",
        "simulation_human_reviews",
        ["run_id"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("simulation_human_reviews", schema=AI_STATE_SCHEMA)
