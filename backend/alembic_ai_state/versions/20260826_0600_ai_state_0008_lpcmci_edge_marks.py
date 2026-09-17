"""Persist LPCMCI edge-orientation marks alongside directed edges.

LPCMCI (unlike PCMCI) can discover bidirected and partially-oriented/
ambiguous relationships in addition to plain directed ones, and can test
contemporaneous (lag-0) links. The manufacturing/telematics causal-edge
tables previously assumed every persisted edge was a directed, lagged
statistical link (via ``source_metric``/``target_metric`` alone). This adds
the missing orientation columns so LPCMCI's richer edge semantics survive
persistence instead of being silently collapsed to directed.

Every historical row was produced by PCMCI, which only ever emits directed,
lag>=1 links, so the server defaults ('DIRECTED', '-->', 1.0) are the exact
factual values for existing rows -- no explicit backfill UPDATE is needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "ai_state_0008"
down_revision: str | None = "ai_state_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"
TABLES = (
    ("manufacturing_causal_edges", "mfg"),
    ("telematics_causal_edges", "telematics"),
)


def upgrade() -> None:
    for table, short_name in TABLES:
        op.add_column(
            table,
            sa.Column(
                "edge_orientation",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'DIRECTED'"),
            ),
            schema=SCHEMA,
        )
        op.add_column(
            table,
            sa.Column(
                "consensus_edge_mark",
                sa.String(length=3),
                nullable=False,
                server_default=sa.text("'-->'"),
            ),
            schema=SCHEMA,
        )
        op.add_column(
            table,
            sa.Column(
                "mark_agreement",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
            schema=SCHEMA,
        )
        op.create_check_constraint(
            f"ck_ai_{short_name}_edges_orientation",
            table,
            "edge_orientation IN ('DIRECTED', 'BIDIRECTED', 'PARTIALLY_ORIENTED', 'AMBIGUOUS')",
            schema=SCHEMA,
        )
        op.create_check_constraint(
            f"ck_ai_{short_name}_edges_mark_agreement",
            table,
            "mark_agreement >= 0 AND mark_agreement <= 1",
            schema=SCHEMA,
        )


def downgrade() -> None:
    for table, short_name in TABLES:
        op.drop_constraint(f"ck_ai_{short_name}_edges_mark_agreement", table, schema=SCHEMA, type_="check")
        op.drop_constraint(f"ck_ai_{short_name}_edges_orientation", table, schema=SCHEMA, type_="check")
        op.drop_column(table, "mark_agreement", schema=SCHEMA)
        op.drop_column(table, "consensus_edge_mark", schema=SCHEMA)
        op.drop_column(table, "edge_orientation", schema=SCHEMA)
