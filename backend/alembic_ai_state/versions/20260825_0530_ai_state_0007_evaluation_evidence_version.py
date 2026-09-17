"""Record the field-evidence version each warning evaluation was derived from.

Warning traceability requires four anchors: the manufacturing causal run, the
telematics causal run, the field-evidence version and the evaluation instant.
The first two were already persisted; this adds the third explicitly instead
of leaving it folded into the opaque evaluation signature.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "ai_state_0007"
down_revision: str | None = "ai_state_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"
TABLE = "warranty_quality_evaluation_runs"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("field_evidence_signature", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("manufacturing_cursor", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("telematics_cursor", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for column in ("telematics_cursor", "manufacturing_cursor", "field_evidence_signature"):
        op.drop_column(TABLE, column, schema=SCHEMA)
