"""Persistent synthetic replay clock and causal-runtime helpers.

The replay clock is a watermark over immutable canonical operational tables. It
is deliberately separate from causal discovery: advancing the clock changes
which source rows are visible, never the rows themselves.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.runtime_schema import runtime_tables
from app.models.causal_runtime_state import CausalReplayState, CausalSchedulerState
from app.models.manufacturing_causal_state import ManufacturingCausalEdge, ManufacturingCausalRun
from app.models.telematics_causal_state import TelematicsCausalEdge, TelematicsCausalRun

REPLAY_STATE_KEY = "default"
CAUSAL_DOMAINS = ("manufacturing", "telematics")


@dataclass(frozen=True)
class ReplayAdvance:
    simulation_as_of: datetime
    last_tick_at: datetime
    ticked: bool
    elapsed_seconds: float


def utc_now(value: datetime | None = None) -> datetime:
    """Return an aware UTC timestamp, rejecting ambiguous naive inputs."""
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Replay timestamps must be timezone-aware.")
    return current.astimezone(UTC)


def calculate_replay_advance(
    *,
    simulation_as_of: datetime,
    last_tick_at: datetime,
    now: datetime,
    replay_speed: float,
    paused: bool,
    replay_end: datetime,
    tick_interval_seconds: int = 60,
) -> ReplayAdvance:
    """Calculate one persistent clock update without touching a database.

    A scheduler may poll more often than once per minute. The interval gate
    makes the clock tick at the configured real-time cadence while preserving
    all elapsed time if a process is delayed or restarted.
    """
    as_of = utc_now(simulation_as_of)
    last = utc_now(last_tick_at)
    current = utc_now(now)
    end = utc_now(replay_end)
    elapsed = max(0.0, (current - last).total_seconds())
    if paused or elapsed < max(1, tick_interval_seconds):
        return ReplayAdvance(as_of, current if paused else last, False, elapsed)
    if replay_speed < 0:
        raise ValueError("replay_speed must be non-negative.")
    advanced = as_of + timedelta(minutes=(elapsed / 60.0) * replay_speed)
    return ReplayAdvance(min(advanced, end), current, True, elapsed)


def stable_source_signature(payload: Mapping[str, Any]) -> str:
    """Create a deterministic fingerprint for a visible causal source cohort."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def graph_delta(
    current_edges: Sequence[Mapping[str, Any]],
    previous_edges: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Compare consecutive discovered edges by source/target/scope identity."""
    def identity(edge: Mapping[str, Any]) -> tuple[str, str, str]:
        return (str(edge.get("source_metric", "")), str(edge.get("target_metric", "")), str(edge.get("scope", "")))

    current = {identity(edge): edge for edge in current_edges}
    previous = {identity(edge): edge for edge in previous_edges}
    shared = current.keys() & previous.keys()
    strengthened = 0
    weakened = 0
    sign_changed = 0
    mark_changed = 0
    for key in shared:
        now_edge = current[key]
        old_edge = previous[key]
        if str(now_edge.get("consensus_sign", "")) != str(old_edge.get("consensus_sign", "")):
            sign_changed += 1
        if str(now_edge.get("consensus_edge_mark", "")) != str(old_edge.get("consensus_edge_mark", "")):
            mark_changed += 1
        now_score = float(now_edge.get("mean_abs_score") or 0.0)
        old_score = float(old_edge.get("mean_abs_score") or 0.0)
        if now_score > old_score:
            strengthened += 1
        elif now_score < old_score:
            weakened += 1
    return {
        "new_edges": len(current.keys() - previous.keys()),
        "removed_edges": len(previous.keys() - current.keys()),
        "unchanged_edges": len(shared),
        "strengthened_edges": strengthened,
        "weakened_edges": weakened,
        "sign_changed_edges": sign_changed,
        "mark_changed_edges": mark_changed,
    }


async def derive_replay_bounds(session: AsyncSession) -> tuple[datetime, datetime]:
    """Derive immutable replay bounds from canonical operational timestamps."""
    settings = get_settings()
    tables = runtime_tables
    min_query = select(func.min(tables["vehicle_telematics_timeseries"].c.timestamp))
    derived_start = (await session.execute(min_query)).scalar_one_or_none()
    if derived_start is None:
        derived_start = datetime.now(UTC)

    maxima: list[datetime] = []
    timestamp_columns = (
        ("manufacturing_timeseries", "timestamp"),
        ("vehicle_telematics_timeseries", "timestamp"),
        ("service_events", "service_started_at"),
        ("warranty_claims", "claim_submitted_at"),
        ("deliveries", "actual_delivery_date"),
    )
    for table_name, column_name in timestamp_columns:
        value = (
            await session.execute(select(func.max(tables[table_name].c[column_name])))
        ).scalar_one_or_none()
        if value is not None:
            maxima.append(utc_now(value))
    derived_end = max([utc_now(derived_start), *maxima])
    start = utc_now(settings.simulation_replay_start or derived_start)
    end = utc_now(settings.simulation_replay_end or derived_end)
    if end < start:
        raise ValueError("simulation_replay_end must be at or after simulation_replay_start.")
    return start, end


async def initialize_replay_state(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> CausalReplayState:
    """Create the singleton clock once, then always return the persisted row."""
    current = utc_now(now)
    start, end = await derive_replay_bounds(session)
    settings = get_settings()
    statement = pg_insert(CausalReplayState).values(
        state_key=REPLAY_STATE_KEY,
        simulation_as_of=start,
        replay_start=start,
        replay_end=end,
        replay_speed=settings.simulation_minutes_per_real_minute,
        paused=False,
        last_tick_at=current,
        tick_count=0,
    ).on_conflict_do_nothing(index_elements=[CausalReplayState.state_key])
    await session.execute(statement)
    await session.commit()
    state = (
        await session.execute(
            select(CausalReplayState).where(CausalReplayState.state_key == REPLAY_STATE_KEY)
        )
    ).scalar_one()
    return state


async def get_replay_state(
    session: AsyncSession,
    *,
    initialize: bool = True,
    now: datetime | None = None,
) -> CausalReplayState | None:
    state = (
        await session.execute(
            select(CausalReplayState).where(CausalReplayState.state_key == REPLAY_STATE_KEY)
        )
    ).scalar_one_or_none()
    if state is None and initialize:
        return await initialize_replay_state(session, now=now)
    return state


async def advance_replay_clock(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> CausalReplayState:
    """Advance the singleton clock under a row lock; safe across restarts."""
    current = utc_now(now)
    state = await get_replay_state(session, initialize=True, now=current)
    assert state is not None
    state = (
        await session.execute(
            select(CausalReplayState)
            .where(CausalReplayState.state_key == REPLAY_STATE_KEY)
            .with_for_update()
        )
    ).scalar_one()
    result = calculate_replay_advance(
        simulation_as_of=state.simulation_as_of,
        last_tick_at=state.last_tick_at,
        now=current,
        replay_speed=state.replay_speed,
        paused=state.paused,
        replay_end=state.replay_end,
        tick_interval_seconds=get_settings().simulation_tick_interval_seconds,
    )
    state.simulation_as_of = result.simulation_as_of
    state.last_tick_at = result.last_tick_at
    if result.ticked:
        state.tick_count += 1
    await session.commit()
    return state


async def set_replay_paused(session: AsyncSession, paused: bool, *, now: datetime | None = None) -> CausalReplayState:
    state = await get_replay_state(session, initialize=True, now=now)
    assert state is not None
    state = (
        await session.execute(
            select(CausalReplayState)
            .where(CausalReplayState.state_key == REPLAY_STATE_KEY)
            .with_for_update()
        )
    ).scalar_one()
    state.paused = paused
    state.last_tick_at = utc_now(now)
    await session.commit()
    return state


async def reset_replay_clock(
    session: AsyncSession,
    *,
    simulation_as_of: datetime,
    replay_speed: float | None = None,
    paused: bool | None = None,
    now: datetime | None = None,
) -> CausalReplayState:
    """Move only the watermark; canonical rows and prior causal runs remain."""
    current = utc_now(now)
    state = await get_replay_state(session, initialize=True, now=current)
    assert state is not None
    state = (
        await session.execute(
            select(CausalReplayState)
            .where(CausalReplayState.state_key == REPLAY_STATE_KEY)
            .with_for_update()
        )
    ).scalar_one()
    target = utc_now(simulation_as_of)
    if target < state.replay_start or target > state.replay_end:
        raise ValueError("simulation_as_of must be inside the persisted replay bounds.")
    state.simulation_as_of = target
    state.last_tick_at = current
    if replay_speed is not None:
        if replay_speed < 0:
            raise ValueError("replay_speed must be non-negative.")
        state.replay_speed = replay_speed
    if paused is not None:
        state.paused = paused
    state.last_error = None
    await session.commit()
    return state


async def try_advisory_lock(session: AsyncSession, domain: str) -> bool:
    """Acquire an xact-scoped Postgres lock independent for each domain."""
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"mahindra-ai-causal:{domain}"},
    )
    return bool(result.scalar_one())


async def try_advisory_lock_session(session: AsyncSession, domain: str) -> bool:
    """Acquire a connection-scoped lock that survives worker commits."""
    result = await session.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
        {"lock_key": f"mahindra-ai-causal:{domain}"},
    )
    return bool(result.scalar_one())


async def release_advisory_lock(session: AsyncSession, domain: str) -> None:
    """Release a connection-scoped domain lock in the worker finally block."""
    await session.execute(
        text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
        {"lock_key": f"mahindra-ai-causal:{domain}"},
    )
    await session.commit()

async def get_scheduler_state(session: AsyncSession, domain: str) -> CausalSchedulerState | None:
    return (
        await session.execute(
            select(CausalSchedulerState).where(CausalSchedulerState.domain == domain)
        )


    ).scalar_one_or_none()
async def ensure_scheduler_states(session: AsyncSession) -> list[CausalSchedulerState]:
    for domain in CAUSAL_DOMAINS:
        statement = pg_insert(CausalSchedulerState).values(domain=domain, status="NOT_READY").on_conflict_do_nothing(
            index_elements=[CausalSchedulerState.domain]
        )
        await session.execute(statement)
    await session.commit()
    return list((await session.execute(select(CausalSchedulerState).order_by(CausalSchedulerState.domain))).scalars())


async def update_scheduler_state(
    session: AsyncSession,
    domain: str,
    *,
    status: str,
    now: datetime,
    next_refresh_at: datetime | None = None,
    run_id: Any = None,
    source_signature: str | None = None,
    analysis_config_signature: str | None = None,
    source_from: datetime | None = None,
    source_to: datetime | None = None,
    error: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    update_run: bool = False,
    active_run_started_at: datetime | None = None,
    active_target_watermark: datetime | None = None,
    pending_refresh: bool | None = None,
    pending_target_watermark: datetime | None = None,
    runtime_seconds: float | None = None,
    clear_active: bool = False,
) -> CausalSchedulerState:
    """Persist scheduler metadata after a job succeeds or reports readiness/error."""
    state = await get_scheduler_state(session, domain)
    if state is None:
        state = CausalSchedulerState(domain=domain, status=status)
        session.add(state)
    state.status = status
    state.next_refresh_at = next_refresh_at
    state.last_error = error
    state.last_diagnostics = dict(diagnostics) if diagnostics is not None else None
    if active_run_started_at is not None:
        state.active_run_started_at = active_run_started_at
    if active_target_watermark is not None:
        state.active_target_watermark = active_target_watermark
    if pending_refresh is not None:
        state.pending_refresh = pending_refresh
    if pending_target_watermark is not None:
        state.pending_target_watermark = pending_target_watermark
    if runtime_seconds is not None:
        state.last_runtime_seconds = runtime_seconds
    if clear_active:
        state.active_run_started_at = None
        state.active_target_watermark = None
    if update_run:
        state.last_refresh_at = utc_now(now)
        state.last_run_id = run_id
        state.last_source_signature = source_signature
        state.last_analysis_config_signature = analysis_config_signature
        state.last_source_from = source_from
        state.last_source_to = source_to
        state.last_completed_at = utc_now(now)
    await session.commit()
    return state


async def get_graph_delta(
    session: AsyncSession,
    domain: str,
    *,
    run_id: Any = None,
) -> dict[str, Any]:
    """Return structural deltas against the previous successful persisted run."""
    if domain == "manufacturing":
        run_model, edge_model = ManufacturingCausalRun, ManufacturingCausalEdge
    elif domain == "telematics":
        run_model, edge_model = TelematicsCausalRun, TelematicsCausalEdge
    else:
        raise ValueError(f"Unsupported causal domain: {domain}")
    runs = list(
        (
            await session.execute(
                select(run_model).order_by(run_model.computed_at.desc(), run_model.id.desc()).limit(20)
            )
        ).scalars()
    )
    current = next((item for item in runs if run_id is None or item.id == run_id), None)
    if current is None:
        return {
            "new_edges": 0,
            "removed_edges": 0,
            "unchanged_edges": 0,
            "strengthened_edges": 0,
            "weakened_edges": 0,
            "sign_changed_edges": 0,
            "mark_changed_edges": 0,
            "previous_run_id": None,
        }
    previous = next((item for item in runs if item.computed_at < current.computed_at), None)
    current_edges = list((await session.execute(select(edge_model).where(edge_model.run_id == current.id))).scalars())
    if previous is None:
        delta = {
            "new_edges": len(current_edges),
            "removed_edges": 0,
            "unchanged_edges": 0,
            "strengthened_edges": 0,
            "weakened_edges": 0,
            "sign_changed_edges": 0,
            "mark_changed_edges": 0,
        }
        delta["previous_run_id"] = None
        return delta
    previous_edges = list((await session.execute(select(edge_model).where(edge_model.run_id == previous.id))).scalars())
    delta = graph_delta(
        [
            {
                "source_metric": edge.source_metric,
                "target_metric": edge.target_metric,
                "scope": edge.scope,
                "consensus_sign": edge.consensus_sign,
                "consensus_edge_mark": edge.consensus_edge_mark,
                "mean_abs_score": edge.mean_abs_score,
            }
            for edge in current_edges
        ],
        [
            {
                "source_metric": edge.source_metric,
                "target_metric": edge.target_metric,
                "scope": edge.scope,
                "consensus_sign": edge.consensus_sign,
                "consensus_edge_mark": edge.consensus_edge_mark,
                "mean_abs_score": edge.mean_abs_score,
            }
            for edge in previous_edges
        ],
    )
    delta["previous_run_id"] = previous.id
    return delta


__all__ = [
    "CAUSAL_DOMAINS",
    "ReplayAdvance",
    "advance_replay_clock",
    "calculate_replay_advance",
    "derive_replay_bounds",
    "ensure_scheduler_states",
    "get_graph_delta",
    "get_replay_state",
    "get_scheduler_state",
    "graph_delta",
    "initialize_replay_state",
    "reset_replay_clock",
    "set_replay_paused",
    "stable_source_signature",
    "try_advisory_lock",
    "try_advisory_lock_session",
    "release_advisory_lock",
    "update_scheduler_state",
    "utc_now",
]
