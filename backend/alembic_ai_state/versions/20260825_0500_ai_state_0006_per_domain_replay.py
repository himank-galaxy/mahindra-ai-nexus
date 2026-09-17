"""Per-domain replay watermarks for independent physical minute ingestion.

Manufacturing minute data and vehicle telematics minute data do not share a
source window: production observations end when the production history ends,
while field telemetry begins after delivery.  A single global watermark can
therefore never make both streams physically ingest at the same simulated
minute.  Each domain gets its own replay anchor and cursor instead.

``replay_cursor`` is how far the domain has been replayed and always advances.
``last_ingested_timestamp`` is the newest row actually inserted, which only
advances when the source had rows due.  Keeping them apart lets a sparse
field-evidence stream advance without pretending it produced evidence.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "ai_state_0006"
down_revision: str | None = "ai_state_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"
TABLE = "causal_ingestion_state"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("source_available_from", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("replay_start", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("replay_cursor", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("initialized_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("exhausted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("tick_count", sa.BigInteger(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_causal_ingestion_cursor",
        TABLE,
        ["replay_cursor"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_causal_ingestion_cursor", table_name=TABLE, schema=SCHEMA)
    for column in (
        "tick_count",
        "last_tick_at",
        "exhausted_at",
        "initialized_at",
        "replay_cursor",
        "replay_start",
        "source_available_from",
    ):
        op.drop_column(TABLE, column, schema=SCHEMA)
