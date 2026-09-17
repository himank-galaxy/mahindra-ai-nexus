"""Add derived manufacturing causal-analysis state.

Revision ID: ai_state_0001
Revises: None
Create Date: 2026-08-18

Purpose
-------
Create persistence for the Warranty, Quality & Service Early-Warning Graph
without changing the validated 50-table Synthetic Data Factory runtime
contract.

Architectural separation
------------------------
public
    Validated runtime/business data imported from synthetic CSV artifacts.

ai_state
    Derived AI/ML state produced from runtime observations.

ground truth
    Evaluator-only data and never imported into PostgreSQL runtime state.

Important
---------
These tables store DISCOVERED causal evidence.

They do not:
- import synthetic causal ground truth,
- hardcode causal source -> target relationships,
- alter the validated 50-table public runtime contract.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------

revision: str = "ai_state_0001"

down_revision: str | None = None

branch_labels: str | Sequence[str] | None = None

depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AI_STATE_SCHEMA = "ai_state"

RUN_TABLE = "manufacturing_causal_runs"

EDGE_TABLE = "manufacturing_causal_edges"


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    """Create derived manufacturing causal-state persistence."""

    # Dedicated derived-state schema.
    op.execute(
        f"CREATE SCHEMA IF NOT EXISTS {AI_STATE_SCHEMA}"
    )

    # -----------------------------------------------------------------------
    # CAUSAL DISCOVERY RUN
    # -----------------------------------------------------------------------

    op.create_table(
        RUN_TABLE,

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        # Deterministic signature over source observations and parameters.
        sa.Column(
            "signature",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "source_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "source_to",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "source_rows",
            sa.BigInteger(),
            nullable=False,
        ),

        sa.Column(
            "machines_requested",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "machines_evaluated",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "candidate_pairs",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "stable_edge_count",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "algorithm",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "algorithm_version",
            sa.String(length=64),
            nullable=True,
        ),

        # PCMCI/FDR/stability configuration used by the run.
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),

        sa.Column(
            "machine_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),

        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_ai_mfg_causal_runs",
        ),

        sa.UniqueConstraint(
            "signature",
            name="uq_ai_mfg_runs_signature",
        ),

        sa.CheckConstraint(
            "source_rows >= 1",
            name="ck_ai_mfg_runs_source_rows",
        ),

        sa.CheckConstraint(
            "machines_requested >= 1",
            name="ck_ai_mfg_runs_requested",
        ),

        sa.CheckConstraint(
            "machines_evaluated >= 1",
            name="ck_ai_mfg_runs_evaluated",
        ),

        sa.CheckConstraint(
            "machines_evaluated <= machines_requested",
            name="ck_ai_mfg_runs_machine_counts",
        ),

        sa.CheckConstraint(
            "candidate_pairs >= 0",
            name="ck_ai_mfg_runs_candidate_pairs",
        ),

        sa.CheckConstraint(
            "stable_edge_count >= 0",
            name="ck_ai_mfg_runs_stable_edges",
        ),

        schema=AI_STATE_SCHEMA,
    )

    op.create_index(
        "ix_ai_mfg_runs_computed_at",
        RUN_TABLE,
        ["computed_at"],
        unique=False,
        schema=AI_STATE_SCHEMA,
    )

    # -----------------------------------------------------------------------
    # STABLE DISCOVERED CAUSAL EDGE
    #
    # Each row represents a relationship surviving:
    #
    # PCMCI
    #   -> multiple-testing correction
    #   -> effect-size filtering
    #   -> manufacturing scope validation
    #   -> cross-machine stability aggregation
    # -----------------------------------------------------------------------

    op.create_table(
        EDGE_TABLE,

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        sa.Column(
            "source_metric",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "target_metric",
            sa.String(length=64),
            nullable=False,
        ),

        # ALL or manufacturing-domain scope such as PAINT.
        sa.Column(
            "scope",
            sa.String(length=32),
            nullable=False,
        ),

        # Consensus effect direction across recurring machines.
        sa.Column(
            "consensus_sign",
            sa.String(length=1),
            nullable=False,
        ),

        sa.Column(
            "eligible_machines",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "recurring_machines",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "recurrence_fraction",
            sa.Float(),
            nullable=False,
        ),

        sa.Column(
            "sign_agreement",
            sa.Float(),
            nullable=False,
        ),

        # PCMCI/ParCorr effect-size evidence.
        sa.Column(
            "mean_abs_score",
            sa.Float(),
            nullable=False,
        ),

        sa.Column(
            "median_abs_score",
            sa.Float(),
            nullable=False,
        ),

        # Best multiple-testing corrected significance.
        sa.Column(
            "best_q_value",
            sa.Float(),
            nullable=False,
        ),

        # Accepted lag values across recurring machines.
        sa.Column(
            "observed_lags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),

        # Machines supporting this relationship.
        sa.Column(
            "machine_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),

        # Machine-level audit evidence.
        #
        # Expected objects later include:
        # machine_id
        # plant_id
        # production_line_id
        # lag
        # score
        # p_value
        # q_value
        # sign
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["run_id"],
            [
                f"{AI_STATE_SCHEMA}.{RUN_TABLE}.id",
            ],
            name="fk_ai_mfg_edges_run",
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_ai_mfg_causal_edges",
        ),

        sa.UniqueConstraint(
            "run_id",
            "source_metric",
            "target_metric",
            "scope",
            name="uq_ai_mfg_edges_run_pair_scope",
        ),

        sa.CheckConstraint(
            "source_metric <> target_metric",
            name="ck_ai_mfg_edges_non_self",
        ),

        sa.CheckConstraint(
            "consensus_sign IN ('+', '-')",
            name="ck_ai_mfg_edges_sign",
        ),

        sa.CheckConstraint(
            "eligible_machines >= 1",
            name="ck_ai_mfg_edges_eligible",
        ),

        sa.CheckConstraint(
            "recurring_machines >= 1",
            name="ck_ai_mfg_edges_recurring",
        ),

        sa.CheckConstraint(
            "recurring_machines <= eligible_machines",
            name="ck_ai_mfg_edges_machine_counts",
        ),

        sa.CheckConstraint(
            (
                "recurrence_fraction >= 0 "
                "AND recurrence_fraction <= 1"
            ),
            name="ck_ai_mfg_edges_recurrence",
        ),

        sa.CheckConstraint(
            (
                "sign_agreement >= 0 "
                "AND sign_agreement <= 1"
            ),
            name="ck_ai_mfg_edges_sign_agreement",
        ),

        sa.CheckConstraint(
            "mean_abs_score >= 0",
            name="ck_ai_mfg_edges_mean_score",
        ),

        sa.CheckConstraint(
            "median_abs_score >= 0",
            name="ck_ai_mfg_edges_median_score",
        ),

        sa.CheckConstraint(
            (
                "best_q_value >= 0 "
                "AND best_q_value <= 1"
            ),
            name="ck_ai_mfg_edges_q_value",
        ),

        schema=AI_STATE_SCHEMA,
    )

    op.create_index(
        "ix_ai_mfg_edges_run_id",
        EDGE_TABLE,
        ["run_id"],
        unique=False,
        schema=AI_STATE_SCHEMA,
    )

    op.create_index(
        "ix_ai_mfg_edges_pair",
        EDGE_TABLE,
        [
            "source_metric",
            "target_metric",
        ],
        unique=False,
        schema=AI_STATE_SCHEMA,
    )

    op.create_index(
        "ix_ai_mfg_edges_stability",
        EDGE_TABLE,
        [
            "recurrence_fraction",
            "sign_agreement",
        ],
        unique=False,
        schema=AI_STATE_SCHEMA,
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    """Remove derived manufacturing causal-state persistence."""

    op.drop_index(
        "ix_ai_mfg_edges_stability",
        table_name=EDGE_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    op.drop_index(
        "ix_ai_mfg_edges_pair",
        table_name=EDGE_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    op.drop_index(
        "ix_ai_mfg_edges_run_id",
        table_name=EDGE_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    op.drop_table(
        EDGE_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    op.drop_index(
        "ix_ai_mfg_runs_computed_at",
        table_name=RUN_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    op.drop_table(
        RUN_TABLE,
        schema=AI_STATE_SCHEMA,
    )

    # The dedicated Alembic environment owns its version table in this
    # schema. Do not drop the schema itself from an individual migration.
