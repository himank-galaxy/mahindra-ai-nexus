"""Add live ingestion, scheduler flight state, and warning lifecycle tables."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "ai_state_0004"
down_revision: str | None = "ai_state_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"
JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("causal_scheduler_state", sa.Column("active_run_started_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("causal_scheduler_state", sa.Column("active_target_watermark", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("causal_scheduler_state", sa.Column("pending_refresh", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column("causal_scheduler_state", sa.Column("pending_target_watermark", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("causal_scheduler_state", sa.Column("last_runtime_seconds", sa.Float(), nullable=True), schema=SCHEMA)
    op.add_column("causal_scheduler_state", sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    op.create_table(
        "causal_ingestion_state",
        sa.Column("domain", sa.String(32), nullable=False),
        sa.Column("source_table", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'NOT_READY'")),
        sa.Column("last_ingested_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ingested_rows", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_ingested_total", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_batch_id", UUID, nullable=True),
        sa.Column("last_batch_signature", sa.String(64), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("diagnostics", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("domain", name="pk_ai_causal_ingestion_state"),
        schema=SCHEMA,
    )
    op.create_index("ix_ai_causal_ingestion_commit", "causal_ingestion_state", ["last_commit_at"], schema=SCHEMA)

    op.create_table(
        "warranty_quality_evaluation_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("evaluation_signature", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'READY'")),
        sa.Column("simulation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manufacturing_causal_run_id", UUID, nullable=True),
        sa.Column("telematics_causal_run_id", UUID, nullable=True),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lifecycle_counts", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("snapshot", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("runtime_seconds", sa.Float(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_warranty_quality_evaluation_runs"),
        sa.UniqueConstraint("evaluation_signature", name="uq_ai_warranty_quality_evaluation_signature"),
        schema=SCHEMA,
    )
    op.create_index("ix_ai_warranty_quality_evaluation_computed", "warranty_quality_evaluation_runs", ["computed_at"], schema=SCHEMA)

    op.create_table(
        "warranty_quality_warnings",
        sa.Column("warning_key", sa.String(128), nullable=False),
        sa.Column("warning_signature", sa.String(64), nullable=False),
        sa.Column("issue_category", sa.String(128), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_transition_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluation_id", UUID, nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("warning_key", name="pk_ai_warranty_quality_warnings"),
        schema=SCHEMA,
    )
    op.create_index("ix_ai_warranty_quality_warning_state", "warranty_quality_warnings", ["lifecycle_state"], schema=SCHEMA)

    op.create_table(
        "warranty_quality_warning_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("warning_key", sa.String(128), nullable=False),
        sa.Column("evaluation_id", UUID, nullable=False),
        sa.Column("previous_state", sa.String(32), nullable=True),
        sa.Column("new_state", sa.String(32), nullable=False),
        sa.Column("warning_signature", sa.String(64), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_warranty_quality_warning_events"),
        schema=SCHEMA,
    )
    op.create_index("ix_ai_warranty_quality_warning_events_key", "warranty_quality_warning_events", ["warning_key", "event_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_ai_warranty_quality_warning_events_key", table_name="warranty_quality_warning_events", schema=SCHEMA)
    op.drop_table("warranty_quality_warning_events", schema=SCHEMA)
    op.drop_index("ix_ai_warranty_quality_warning_state", table_name="warranty_quality_warnings", schema=SCHEMA)
    op.drop_table("warranty_quality_warnings", schema=SCHEMA)
    op.drop_index("ix_ai_warranty_quality_evaluation_computed", table_name="warranty_quality_evaluation_runs", schema=SCHEMA)
    op.drop_table("warranty_quality_evaluation_runs", schema=SCHEMA)
    op.drop_index("ix_ai_causal_ingestion_commit", table_name="causal_ingestion_state", schema=SCHEMA)
    op.drop_table("causal_ingestion_state", schema=SCHEMA)
    for column in (
        "last_completed_at",
        "last_runtime_seconds",
        "pending_target_watermark",
        "pending_refresh",
        "active_target_watermark",
        "active_run_started_at",
    ):
        op.drop_column("causal_scheduler_state", column, schema=SCHEMA)
