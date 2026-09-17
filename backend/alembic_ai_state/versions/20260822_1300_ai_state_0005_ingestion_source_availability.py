"""Track immutable source availability for live-ingestion diagnostics."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "ai_state_0005"
down_revision: str | None = "ai_state_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"


def upgrade() -> None:
    op.add_column(
        "causal_ingestion_state",
        sa.Column("source_available_to", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("causal_ingestion_state", "source_available_to", schema=SCHEMA)
