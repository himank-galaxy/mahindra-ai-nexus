"""Track the causal-analysis CONFIGURATION signature alongside the source one.

The scheduler's fast-path reuse check previously compared only the source-
data signature (causal_scheduler_state.last_source_signature). A
deployment-time configuration change -- e.g. flipping causal_algorithm from
"pcmci" to "lpcmci" -- does not touch source data, so it was invisible to
that check: the scheduler would keep resurfacing a historical PCMCI run as
"reused" forever, whenever the source itself happened not to have changed,
without ever calling the orchestration service to compute a fresh LPCMCI
run.

This adds a second, independent fingerprint covering the analysis
configuration itself (algorithm, tau_max, pc_alpha, panel/filter config,
...). The scheduler's fast path now requires BOTH signatures to match
before skipping the service call.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "ai_state_0009"
down_revision: str | None = "ai_state_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai_state"
TABLE = "causal_scheduler_state"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("last_analysis_config_signature", sa.String(length=64), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "last_analysis_config_signature", schema=SCHEMA)
