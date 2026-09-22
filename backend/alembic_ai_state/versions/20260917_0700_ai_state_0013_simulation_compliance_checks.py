"""Add Simulation Center compliance-check persistence.

One row per rule evaluated against a persisted run, mirroring the real
canonical ``compliance_checks`` shape (rule_code/rule_name/result/reason)
so both tracks share one contract. Evaluated once (by
app/services/compliance_engine.py) and cached here — a run's inputs are
immutable once created, so re-evaluating would always produce the same
result; persisting still gives a stable, inspectable historical record.

Revision ID: ai_state_0013
Revises: ai_state_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0013"
down_revision: str | None = "ai_state_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "simulation_compliance_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("rule_name", sa.String(length=128), nullable=False),
        sa.Column("rule_version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column("result", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_simulation_compliance_checks"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{AI_STATE_SCHEMA}.simulation_runs.id"],
            name="fk_ai_simulation_compliance_checks_run_id",
            ondelete="CASCADE",
        ),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_simulation_compliance_checks_run_id",
        "simulation_compliance_checks",
        ["run_id"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("simulation_compliance_checks", schema=AI_STATE_SCHEMA)
