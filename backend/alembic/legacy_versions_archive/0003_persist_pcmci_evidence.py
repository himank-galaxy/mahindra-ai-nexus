"""Persist calculated PCMCI runs and edge statistics.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.text("now()")


def upgrade() -> None:
    audit = (sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False))
    op.create_table("causal_analysis_runs", sa.Column("id", UUID, primary_key=True), sa.Column("signature", sa.String(64), nullable=False), sa.Column("source_from", sa.Date(), nullable=False), sa.Column("source_to", sa.Date(), nullable=False), sa.Column("observations", sa.Integer(), nullable=False), sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False), *audit, sa.UniqueConstraint("signature", name="uq_causal_analysis_runs_signature"))
    op.create_index("ix_causal_analysis_runs_signature", "causal_analysis_runs", ["signature"])
    op.create_table("causal_analysis_edges", sa.Column("id", UUID, primary_key=True), sa.Column("run_id", UUID, sa.ForeignKey("causal_analysis_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("source_metric", sa.String(64), nullable=False), sa.Column("target_metric", sa.String(64), nullable=False), sa.Column("lag", sa.Integer(), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("p_value", sa.Float(), nullable=False), *audit, sa.UniqueConstraint("run_id", "source_metric", "target_metric", "lag", name="uq_causal_analysis_edge"), sa.CheckConstraint("lag >= 1", name="ck_causal_analysis_edges_causal_analysis_lag_positive"), sa.CheckConstraint("p_value BETWEEN 0 AND 1", name="ck_causal_analysis_edges_causal_analysis_p_value_range"))
    op.create_index("ix_causal_analysis_edges_run_id", "causal_analysis_edges", ["run_id"])


def downgrade() -> None:
    op.drop_table("causal_analysis_edges")
    op.drop_table("causal_analysis_runs")
