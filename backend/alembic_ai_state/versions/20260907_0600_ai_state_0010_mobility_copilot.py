"""Add Auto Mobility Causal Twin copilot conversation turns.

One row per turn (user question or assistant reply), keyed by a
client-generated session_id — see
docs/Implementation_plan_mobility_causal.md §7 and
app/models/mobility_copilot_state.py.

Revision ID: ai_state_0010
Revises: ai_state_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ai_state_0010"
down_revision: str | None = "ai_state_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AI_STATE_SCHEMA = "ai_state"


def upgrade() -> None:
    op.create_table(
        "mobility_copilot_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_ai_mobility_copilot_turns"),
        schema=AI_STATE_SCHEMA,
    )
    op.create_index(
        "ix_ai_mobility_copilot_turns_session_created",
        "mobility_copilot_turns",
        ["session_id", "created_at"],
        schema=AI_STATE_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_mobility_copilot_turns_session_created",
        table_name="mobility_copilot_turns",
        schema=AI_STATE_SCHEMA,
    )
    op.drop_table("mobility_copilot_turns", schema=AI_STATE_SCHEMA)
