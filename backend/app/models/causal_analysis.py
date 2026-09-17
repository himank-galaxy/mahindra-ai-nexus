"""Persisted evidence from genuine PCMCI causal-discovery executions."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk


class CausalAnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "causal_analysis_runs"

    signature: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_from: Mapped[date] = mapped_column(Date)
    source_to: Mapped[date] = mapped_column(Date)
    observations: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CausalAnalysisEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "causal_analysis_edges"

    run_id: Mapped[uuid.UUID] = mapped_column(uuid_pk(), ForeignKey("causal_analysis_runs.id", ondelete="CASCADE"), index=True)
    source_metric: Mapped[str] = mapped_column(String(64))
    target_metric: Mapped[str] = mapped_column(String(64))
    lag: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    p_value: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("run_id", "source_metric", "target_metric", "lag", name="uq_causal_analysis_edge"),
        CheckConstraint("lag >= 1", name="causal_analysis_lag_positive"),
        CheckConstraint("p_value BETWEEN 0 AND 1", name="causal_analysis_p_value_range"),
    )
