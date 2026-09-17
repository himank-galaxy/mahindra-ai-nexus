"""Versioned, process-local mobility snapshots refreshed when sampled input changes."""

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.ai.causal.data_loader import CausalInput, load_daily_causal_input
from app.ai.causal.mobility_engine import MobilityEdge, discover_edges
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError
from app.core.logging import get_logger
from app.database.session import get_session_factory
from app.schemas.mobility import MobilitySnapshotOut

logger = get_logger(__name__)


@dataclass(frozen=True, eq=False)
class MobilityCausalState:
    edges: tuple[MobilityEdge, ...]
    source: CausalInput
    computed_at: datetime
    snapshot_id: str
    stride_hours: int
    tau_max: int
    alpha: float

    @property
    def metrics(self):
        return self.source.metrics

    @property
    def values(self):
        return self.source.values

    @property
    def dates(self):
        return self.source.dates

    @property
    def latest(self):
        return dict(zip(self.metrics, self.values[-1], strict=True))

    @property
    def previous(self):
        return dict(zip(self.metrics, self.values[-2], strict=True))

    @property
    def comparison_minutes(self):
        return self.stride_hours * 60

    @property
    def observation_count(self):
        return len(self.dates)

    @property
    def effective_observation_count(self):
        return sum(end - start - 2 * self.tau_max for start, end in self.source.segments)


_current: MobilityCausalState | None = None
_prior: MobilityCausalState | None = None
_refresh_lock = asyncio.Lock()
_checked_at: datetime | None = None
_source_latest_at: datetime | None = None
_last_error: str | None = None


def get_current_state() -> MobilityCausalState | None:
    return _current


def get_prior_state() -> MobilityCausalState | None:
    return _prior


def snapshot_metadata(state: MobilityCausalState) -> MobilitySnapshotOut:
    settings = get_settings()
    now = datetime.now(UTC)
    warnings = list(state.source.warnings)
    stale = now - state.dates[-1] > timedelta(
        hours=state.stride_hours, minutes=settings.mobility_causal_refresh_minutes
    )
    if stale:
        warnings.append("The analysis does not cover the latest expected complete sampling period.")
    if state.effective_observation_count < settings.mobility_causal_min_observations * 2:
        warnings.append("Limited usable history: treat these relationships as preliminary evidence.")
    if _last_error:
        warnings.append("Refresh failed; showing the last successful analysis.")
    if any(feature.aggregation == "regional mean" for feature in state.source.features):
        warnings.append(
            "Measures without event weights use equal regional averages; inspect each measure's aggregation."
        )
    connected = {key for edge in state.edges for key in (edge.source, edge.target)}
    return MobilitySnapshotOut(
        snapshot_id=state.snapshot_id,
        computed_at=state.computed_at,
        data_start=state.source.source_dates[0],
        data_end=state.source.source_dates[-1],
        source_latest_at=_source_latest_at or state.source.source_latest_at,
        checked_at=_checked_at,
        next_check_at=(_checked_at + timedelta(minutes=settings.mobility_causal_refresh_minutes))
        if _checked_at
        else None,
        observation_count=state.observation_count,
        effective_observation_count=state.effective_observation_count,
        segment_count=len(state.source.segments),
        sample_stride_hours=state.stride_hours,
        refresh_check_minutes=settings.mobility_causal_refresh_minutes,
        max_lag_hours=state.tau_max * state.stride_hours,
        significance_threshold=state.alpha,
        status="stale" if stale or _last_error else "ready",
        refreshing=_refresh_lock.locked(),
        last_error=_last_error,
        warnings=warnings,
        excluded_metrics=state.source.excluded,
        data_origins=list(state.source.data_origins),
        connected_measure_count=len(connected),
        hidden_isolated_measure_count=len(state.source.metrics) - len(connected),
    )


async def refresh() -> MobilityCausalState:
    global _current, _prior, _checked_at, _source_latest_at, _last_error
    settings = get_settings()
    async with _refresh_lock:
        try:
            async with get_session_factory()() as session:
                source = await load_daily_causal_input(
                    session,
                    window_days=settings.mobility_causal_window_days,
                    stride_hours=settings.mobility_causal_sample_stride_hours,
                    min_observations=settings.mobility_causal_min_observations,
                    tau_max=settings.mobility_causal_tau_max,
                )
            _source_latest_at = source.source_latest_at
            signature = hashlib.sha256(
                source.values.tobytes()
                + repr(
                    (
                        source.dates,
                        source.source_dates,
                        source.features,
                        source.segments,
                        source.excluded,
                        source.warnings,
                        settings.mobility_causal_tau_max,
                        settings.mobility_causal_pc_alpha,
                        settings.mobility_causal_sample_stride_hours,
                    )
                ).encode()
            ).hexdigest()
            if _current and _current.snapshot_id == signature:
                _last_error = None
                return _current
            edges = await asyncio.to_thread(
                discover_edges,
                source,
                tau_max=settings.mobility_causal_tau_max,
                alpha=settings.mobility_causal_pc_alpha,
            )
            state = MobilityCausalState(
                edges,
                source,
                datetime.now(UTC),
                signature,
                settings.mobility_causal_sample_stride_hours,
                settings.mobility_causal_tau_max,
                settings.mobility_causal_pc_alpha,
            )
            _prior, _current = _current, state
            _last_error = None
            logger.info(
                "mobility_causal_refreshed",
                edge_count=len(edges),
                metric_count=len(source.metrics),
                observation_count=state.observation_count,
                snapshot_id=signature,
            )
            return state
        except Exception as exc:
            _last_error = (
                str(exc) if isinstance(exc, ValueError) else "Mobility analysis could not refresh. Check backend logs."
            )
            logger.warning("mobility_causal_refresh_failed", error=str(exc))
            raise AppError(_last_error, code="mobility_analysis_unavailable", status_code=503) from exc
        finally:
            _checked_at = datetime.now(UTC)


async def get_or_refresh(snapshot_id: str | None = None) -> MobilityCausalState:
    state = _current or await refresh()
    if snapshot_id is None or state.snapshot_id == snapshot_id:
        return state
    if _prior and _prior.snapshot_id == snapshot_id:
        return _prior
    raise ConflictError("This analysis has expired. Refresh the graph to continue.", code="mobility_snapshot_expired")


async def refresh_loop() -> None:
    while True:
        with suppress(AppError):  # Failure is exposed in metadata; the next check retries.
            await refresh()
        await asyncio.sleep(get_settings().mobility_causal_refresh_minutes * 60)
