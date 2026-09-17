"""Add Simulation Center run and approval persistence.

One row per what-if run (inputs, baseline, scenario outputs, driver
evidence, recommendation, confidence, model lineage) plus a separate
append-only human-decision table, keyed to the run. See
app/models/simulation.py and
docs/simulation_centre_implementation.md §2.

Revision ID: ai_state_0011
Revises: ai_state_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0011"
down_revision: str | None = "ai_state_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("scenario_name", sa.String(length=64), nullable=False, server_default="Baseline FY26"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("baseline_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("driver_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommendation_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("confidence_band", sa.String(length=16), nullable=False),
        sa.Column("confidence_basis", sa.String(length=24), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_simulation_runs"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_ai_simulation_runs_confidence_range"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_simulation_runs_domain",
        "simulation_runs",
        ["domain"],
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_simulation_runs_status",
        "simulation_runs",
        ["status"],
        schema=AI_STATE_SCHEMA,
    )

    op.create_table(
        "simulation_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="demo_user"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_simulation_approvals"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{AI_STATE_SCHEMA}.simulation_runs.id"],
            name="fk_ai_simulation_approvals_run_id",
            ondelete="CASCADE",
        ),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_simulation_approvals_run_id",
        "simulation_approvals",
        ["run_id"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("simulation_approvals", schema=AI_STATE_SCHEMA)
    op.drop_table("simulation_runs", schema=AI_STATE_SCHEMA)
