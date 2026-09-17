"""Add immutable replay-source storage for live causal ingestion.

The validated ``public`` runtime tables remain the operational read model.  A
separate ``replay`` schema holds a complete, deterministic source snapshot so
the ingestion worker can expose only rows due at the persisted simulation
watermark.  The source tables are append-only after cutover; UPDATE/DELETE is
blocked by a database trigger.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "runtime_0003"
down_revision: str | None = "runtime_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPLAY_SCHEMA = "replay"
IMMUTABLE_FUNCTION = "replay.reject_source_mutation"
SOURCE_TABLES = (
    "manufacturing_timeseries",
    "vehicle_telematics_timeseries",
    "service_events",
    "warranty_claims",
)


def upgrade() -> None:
    op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {REPLAY_SCHEMA}"))
    op.execute(
        sa.text(
            """
            CREATE TABLE replay.cutover_manifest (
                manifest_key TEXT PRIMARY KEY,
                source_version TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                row_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
                source_windows JSONB NOT NULL DEFAULT '{}'::jsonb,
                notes JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION replay.reject_source_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'replay source table % is immutable after cutover', TG_TABLE_NAME
                    USING ERRCODE = '55006';
            END;
            $$
            """
        )
    )
    for table_name in SOURCE_TABLES:
        op.execute(
            sa.text(
                f"CREATE TABLE replay.{table_name} "
                f"(LIKE public.{table_name} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {table_name}_immutable "
                f"BEFORE UPDATE OR DELETE ON replay.{table_name} "
                "FOR EACH ROW EXECUTE FUNCTION replay.reject_source_mutation()"
            )
        )
        op.execute(
            sa.text(
                f"CREATE INDEX ix_replay_{table_name}_time "
                f"ON replay.{table_name} "
                + (
                    "(timestamp)"
                    if table_name in {"manufacturing_timeseries", "vehicle_telematics_timeseries"}
                    else "(service_started_at)"
                    if table_name == "service_events"
                    else "(claim_submitted_at)"
                )
            )
        )


def downgrade() -> None:
    for table_name in reversed(SOURCE_TABLES):
        op.execute(sa.text(f"DROP TABLE IF EXISTS replay.{table_name}"))
    op.execute(sa.text("DROP TABLE IF EXISTS replay.cutover_manifest"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS replay.reject_source_mutation()"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS replay"))
