"""Persistent replay and causal-scheduler state in the isolated AI schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.ai_state_base import AI_STATE_SCHEMA, AiStateBase
from app.database.base import JSONType, TimestampMixin


class CausalReplayState(TimestampMixin, AiStateBase):
    """Singleton synthetic-clock state; no canonical data is mutated."""

    __tablename__ = "causal_replay_state"

    state_key: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    simulation_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replay_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replay_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replay_speed: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    paused: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_tick_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tick_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class CausalSchedulerState(TimestampMixin, AiStateBase):
    """Per-domain scheduler checkpoint and last successful run metadata."""

    __tablename__ = "causal_scheduler_state"

    domain: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_READY")
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    last_source_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Fingerprint of the causal-analysis CONFIGURATION (algorithm, tau_max,
    # pc_alpha, panel/filter config, ...) the last completed run used --
    # distinct from last_source_signature (pure source-data identity). See
    # app.scheduler.causal_scheduler._analysis_config_signature. A scheduler
    # fast-path reuse requires BOTH to match the current tick's values;
    # either changing (e.g. a PCMCI -> LPCMCI deployment-time cutover with
    # unchanged source data) forces the scheduler to call the orchestration
    # service rather than silently resurfacing a historical run computed
    # under a different configuration.
    last_analysis_config_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_source_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_source_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    active_run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_target_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_refresh: Mapped[bool] = mapped_column(nullable=False, default=False)
    pending_target_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


class CausalIngestionState(TimestampMixin, AiStateBase):
    """Per-source transactional ingestion checkpoint with an own replay cursor.

    Each domain replays its own immutable source.  ``replay_cursor`` is the
    authoritative watermark and always advances; ``last_ingested_timestamp``
    is the newest row physically inserted and only advances when the source
    actually had rows due in the interval.
    """

    __tablename__ = "causal_ingestion_state"

    domain: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_table: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_READY")
    source_available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_available_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replay_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replay_cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tick_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_ingested_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingested_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_ingested_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_batch_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    last_batch_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_commit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    __table_args__ = {"schema": AI_STATE_SCHEMA}


