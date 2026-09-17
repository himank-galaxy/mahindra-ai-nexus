"""Add independent vehicle-telematics causal state.

Revision ID: ai_state_0002
Revises: ai_state_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0002"
down_revision: str | None = "ai_state_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"
RUN_TABLE = "telematics_causal_runs"
EDGE_TABLE = "telematics_causal_edges"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        RUN_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column("source_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_rows", sa.BigInteger(), nullable=False),
        sa.Column("vehicles_requested", sa.Integer(), nullable=False),
        sa.Column("vehicles_evaluated", sa.Integer(), nullable=False),
        sa.Column("candidate_pairs", sa.Integer(), nullable=False),
        sa.Column("stable_edge_count", sa.Integer(), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=True),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("vehicle_ids", JSONB, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_telematics_causal_runs"),
        sa.UniqueConstraint("signature", name="uq_ai_telematics_runs_signature"),
        sa.CheckConstraint("source_rows >= 1", name="ck_ai_telematics_runs_source_rows"),
        sa.CheckConstraint("vehicles_requested >= 1", name="ck_ai_telematics_runs_requested"),
        sa.CheckConstraint("vehicles_evaluated >= 1", name="ck_ai_telematics_runs_evaluated"),
        sa.CheckConstraint("vehicles_evaluated <= vehicles_requested", name="ck_ai_telematics_runs_vehicle_counts"),
        sa.CheckConstraint("candidate_pairs >= 0", name="ck_ai_telematics_runs_candidate_pairs"),
        sa.CheckConstraint("stable_edge_count >= 0", name="ck_ai_telematics_runs_stable_edges"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index("ix_ai_telematics_runs_computed_at", RUN_TABLE, ["computed_at"], schema=AI_STATE_SCHEMA)

    op.create_table(
        EDGE_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_metric", sa.String(length=64), nullable=False),
        sa.Column("target_metric", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("consensus_sign", sa.String(length=1), nullable=False),
        sa.Column("eligible_vehicles", sa.Integer(), nullable=False),
        sa.Column("recurring_vehicles", sa.Integer(), nullable=False),
        sa.Column("recurrence_fraction", sa.Float(), nullable=False),
        sa.Column("sign_agreement", sa.Float(), nullable=False),
        sa.Column("mean_abs_score", sa.Float(), nullable=False),
        sa.Column("median_abs_score", sa.Float(), nullable=False),
        sa.Column("best_q_value", sa.Float(), nullable=False),
        sa.Column("min_p_value", sa.Float(), nullable=False),
        sa.Column("max_p_value", sa.Float(), nullable=False),
        sa.Column("min_q_value", sa.Float(), nullable=False),
        sa.Column("max_q_value", sa.Float(), nullable=False),
        sa.Column("observed_lags", JSONB, nullable=False),
        sa.Column("observed_lag_minutes", JSONB, nullable=False),
        sa.Column("vehicle_ids", JSONB, nullable=False),
        sa.Column("evidence", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{AI_STATE_SCHEMA}.{RUN_TABLE}.id"],
            name="fk_ai_telematics_edges_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_telematics_causal_edges"),
        sa.UniqueConstraint(
            "run_id", "source_metric", "target_metric", "scope", name="uq_ai_telematics_edges_run_pair_scope"
        ),
        sa.CheckConstraint("source_metric <> target_metric", name="ck_ai_telematics_edges_non_self"),
        sa.CheckConstraint("consensus_sign IN ('+', '-')", name="ck_ai_telematics_edges_sign"),
        sa.CheckConstraint("eligible_vehicles >= 1", name="ck_ai_telematics_edges_eligible"),
        sa.CheckConstraint("recurring_vehicles >= 1", name="ck_ai_telematics_edges_recurring"),
        sa.CheckConstraint("recurring_vehicles <= eligible_vehicles", name="ck_ai_telematics_edges_vehicle_counts"),
        sa.CheckConstraint(
            "recurrence_fraction >= 0 AND recurrence_fraction <= 1", name="ck_ai_telematics_edges_recurrence"
        ),
        sa.CheckConstraint("sign_agreement >= 0 AND sign_agreement <= 1", name="ck_ai_telematics_edges_sign_agreement"),
        sa.CheckConstraint("mean_abs_score >= 0", name="ck_ai_telematics_edges_mean_score"),
        sa.CheckConstraint("median_abs_score >= 0", name="ck_ai_telematics_edges_median_score"),
        sa.CheckConstraint("best_q_value >= 0 AND best_q_value <= 1", name="ck_ai_telematics_edges_q_value"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index("ix_ai_telematics_edges_run_id", EDGE_TABLE, ["run_id"], schema=AI_STATE_SCHEMA)
    op.create_index(
        "ix_ai_telematics_edges_pair", EDGE_TABLE, ["source_metric", "target_metric"], schema=AI_STATE_SCHEMA
    )
    op.create_index(
        "ix_ai_telematics_edges_stability",
        EDGE_TABLE,
        ["recurrence_fraction", "sign_agreement"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_telematics_edges_stability", table_name=EDGE_TABLE, schema=AI_STATE_SCHEMA)
    op.drop_index("ix_ai_telematics_edges_pair", table_name=EDGE_TABLE, schema=AI_STATE_SCHEMA)
    op.drop_index("ix_ai_telematics_edges_run_id", table_name=EDGE_TABLE, schema=AI_STATE_SCHEMA)
    op.drop_table(EDGE_TABLE, schema=AI_STATE_SCHEMA)
    op.drop_index("ix_ai_telematics_runs_computed_at", table_name=RUN_TABLE, schema=AI_STATE_SCHEMA)
    op.drop_table(RUN_TABLE, schema=AI_STATE_SCHEMA)
