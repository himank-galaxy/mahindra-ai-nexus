"""Add persistent replay clock and causal scheduler checkpoints.

Revision ID: ai_state_0003
Revises: ai_state_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ai_state_0003"
down_revision: str | None = "ai_state_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "causal_replay_state",
        sa.Column("state_key", sa.String(length=32), nullable=False),
        sa.Column("simulation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_speed", sa.Float(), nullable=False, server_default=sa.text("60.0")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_tick_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tick_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("state_key", name="pk_ai_causal_replay_state"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_table(
        "causal_scheduler_state",
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'NOT_READY'")),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_source_signature", sa.String(length=64), nullable=True),
        sa.Column("last_source_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_source_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_diagnostics", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("domain", name="pk_ai_causal_scheduler_state"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_causal_scheduler_state_next_refresh",
        "causal_scheduler_state",
        ["next_refresh_at"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_causal_scheduler_state_next_refresh",
        table_name="causal_scheduler_state",
        schema=AI_STATE_SCHEMA,
    )
    op.drop_table("causal_scheduler_state", schema=AI_STATE_SCHEMA)
    op.drop_table("causal_replay_state", schema=AI_STATE_SCHEMA)
