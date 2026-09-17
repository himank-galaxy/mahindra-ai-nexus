"""Independent causal-discovery orchestration for vehicle telemetry."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.ai.causal.pcmci_engine import (
    pcmci_tests_as_causal_discovery_tests,
    run_lpcmci_tests,
    run_pcmci_tests,
)
from app.ai.causal.telematics_filter import (
    DEFAULT_TELEMATICS_FILTER_CONFIG,
    TelematicsFilterConfig,
    TelematicsFilterResult,
    aggregate_telematics_stability,
    filter_telematics_tests,
)
from app.ai.causal.telematics_loader import (
    DEFAULT_HISTORY_HOURS,
    TELEMATICS_CONTEXT_FIELDS,
    TELEMATICS_EXCLUDED_FIELDS,
    TELEMATICS_METRICS,
    detect_raw_frequency_minutes,
    fetch_vehicle_rows,
    get_vehicle_visible_latest_timestamp,
    rows_to_telematics_records,
)
from app.ai.causal.telematics_panel import (
    DEFAULT_TELEMATICS_PANEL_CONFIG,
    TelematicsPanelConfig,
    build_telematics_panel,
)
from app.core.logging import get_logger
from app.models.telematics_causal_state import TelematicsCausalEdge, TelematicsCausalRun
from app.services.base import BaseService

logger = get_logger(__name__)

ORCHESTRATOR_VERSION = "1.0.0"

CausalAlgorithm = Literal["lpcmci", "pcmci"]

DEFAULT_ALGORITHM: CausalAlgorithm = "lpcmci"

DEFAULT_TEST_CONTEMPORANEOUS = True


def _algorithm_label(algorithm: CausalAlgorithm) -> str:
    """Persisted-run algorithm string, keyed off the actual engine used."""

    prefix = "LPCMCI" if algorithm == "lpcmci" else "PCMCI"
    return f"{prefix}-ParCorr+BH-FDR+cross-vehicle-stability"


# --- Algorithm-specific tau_max/pc_alpha defaults ---------------------------
# See manufacturing_causal.py for the full rationale (identical here):
# PCMCI rollback keeps its established legacy values; LPCMCI defaults to the
# reference pipeline's much cheaper search window, since LPCMCI's cost grows
# far faster with tau_max than PCMCI's.
PCMCI_DEFAULT_TAU_MAX = 12
PCMCI_DEFAULT_PC_ALPHA = 0.05

LPCMCI_DEFAULT_TAU_MAX = 2
LPCMCI_DEFAULT_PC_ALPHA = 0.10

# Backward-compatible aliases -- see manufacturing_causal.py.
DEFAULT_TAU_MAX = PCMCI_DEFAULT_TAU_MAX
DEFAULT_PC_ALPHA = PCMCI_DEFAULT_PC_ALPHA


def effective_tau_max(algorithm: CausalAlgorithm, tau_max: int | None) -> int:
    """Resolve the tau_max actually used for one analysis. See
    manufacturing_causal.effective_tau_max for the full contract: an
    explicitly supplied value is always honored unchanged."""

    if tau_max is not None:
        return tau_max
    return LPCMCI_DEFAULT_TAU_MAX if algorithm == "lpcmci" else PCMCI_DEFAULT_TAU_MAX


def effective_pc_alpha(algorithm: CausalAlgorithm, pc_alpha: float | None) -> float:
    """Resolve the pc_alpha actually used for one analysis. See effective_tau_max."""

    if pc_alpha is not None:
        return pc_alpha
    return LPCMCI_DEFAULT_PC_ALPHA if algorithm == "lpcmci" else PCMCI_DEFAULT_PC_ALPHA


def effective_tau_min(algorithm: CausalAlgorithm, test_contemporaneous: bool) -> int:
    """Resolve the true minimum lag tested for one analysis.

    See manufacturing_causal.effective_tau_min for the full contract:
    LPCMCI+test_contemporaneous=True -> 0; LPCMCI+test_contemporaneous=False
    -> 1; PCMCI -> 1 (never tests lag 0).
    """

    if algorithm == "lpcmci" and test_contemporaneous:
        return 0
    return 1


@dataclass(frozen=True)
class TelematicsCausalEdgeResult:
    source_metric: str
    target_metric: str
    scope: str
    consensus_sign: str
    edge_orientation: str
    consensus_edge_mark: str
    mark_agreement: float
    eligible_vehicles: int
    recurring_vehicles: int
    recurrence_fraction: float
    sign_agreement: float
    mean_abs_score: float
    median_abs_score: float
    best_q_value: float
    min_p_value: float
    max_p_value: float
    min_q_value: float
    max_q_value: float
    observed_lags: tuple[int, ...]
    observed_lag_minutes: tuple[int, ...]
    vehicle_ids: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class TelematicsCausalAnalysisResult:
    run_id: uuid.UUID
    signature: str
    reused: bool
    source_from: datetime
    source_to: datetime
    source_rows: int
    raw_frequency_minutes: float
    analysis_frequency_minutes: int
    analysis_window_hours: float
    analytical_rows_total: int
    minimum_analytical_rows: int
    maximum_analytical_rows: int
    minimum_variables_used: int
    maximum_variables_used: int
    tau_min: int
    tau_max: int
    maximum_lag_minutes: int
    vehicles_requested: int
    vehicles_evaluated: int
    candidate_pairs: int
    stable_edge_count: int
    algorithm: str
    algorithm_version: str | None
    parameters: dict[str, Any]
    vehicle_ids: tuple[str, ...]
    computed_at: datetime
    edges: tuple[TelematicsCausalEdgeResult, ...]


@dataclass(frozen=True)
class _VehicleAnalysis:
    filtered: TelematicsFilterResult
    analytical_rows: int
    variables_used: tuple[str, ...]
    dropped_metrics: dict[str, str]
    missing_intervals: dict[str, int]
    transformed_metrics: tuple[str, ...]
    duplicate_records_removed: int
    panel_runtime_seconds: float
    pcmci_runtime_seconds: float


def _analysis_frequency_minutes(frequency: str) -> int:
    try:
        minutes = float(pd.Timedelta(frequency).total_seconds() / 60.0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid telematics analysis frequency: {frequency}") from exc
    if minutes < 1 or not math.isclose(minutes, round(minutes), abs_tol=1e-9):
        raise ValueError("Telematics analysis frequency must be a whole number of minutes.")
    return int(round(minutes))


def _normalise_timestamp(value: Any) -> datetime:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("Telemetry contains an invalid timestamp.")
    timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    return timestamp.to_pydatetime()


def _normalise_vehicle_ids(vehicle_ids: Sequence[str]) -> tuple[str, ...]:
    values = tuple(sorted({str(value).strip() for value in vehicle_ids if str(value).strip()}))
    if not values:
        raise ValueError("At least one vehicle ID must be supplied.")
    return values


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return _normalise_timestamp(value).isoformat()
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _configuration_parameters(
    vehicle_ids: Sequence[str],
    *,
    history_hours: float,
    source_from: datetime | None,
    source_to: datetime | None,
    raw_frequency_minutes: float,
    panel_config: TelematicsPanelConfig,
    filter_config: TelematicsFilterConfig,
    tau_max: int,
    pc_alpha: float,
    analysis_frequency_minutes: int,
    algorithm: CausalAlgorithm = DEFAULT_ALGORITHM,
    test_contemporaneous: bool = DEFAULT_TEST_CONTEMPORANEOUS,
    algorithm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _jsonable(
        {
            "pipeline": "vehicle_telematics",
            "orchestrator_version": ORCHESTRATOR_VERSION,
            # Participates in the source signature so switching algorithm
            # always triggers a fresh run rather than reusing a persisted
            # run computed under a different engine.
            "algorithm": algorithm,
            "test_contemporaneous": (
                test_contemporaneous if algorithm == "lpcmci" else None
            ),
            "algorithm_config": dict(algorithm_config or {}),
            "vehicle_ids": tuple(vehicle_ids),
            "history_hours": history_hours,
            "source_from": source_from,
            "source_to": source_to,
            "raw_frequency_minutes": raw_frequency_minutes,
            "analysis_frequency": panel_config.analysis_frequency,
            "analysis_frequency_minutes": analysis_frequency_minutes,
            "tau_min": effective_tau_min(algorithm, test_contemporaneous),
            "tau_max": tau_max,
            "pc_alpha": pc_alpha,
            "panel_config": asdict(panel_config),
            "filter_config": asdict(filter_config),
            "pcmci_variables": list(TELEMATICS_METRICS),
            "context_fields": list(TELEMATICS_CONTEXT_FIELDS),
            "excluded_fields": list(TELEMATICS_EXCLUDED_FIELDS),
            "aggregation": {
                "impact_g_force": "max",
                "other_physical_signals": "mean",
            },
        }
    )


def _row_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = sha256()
    fields = ("timestamp", *TELEMATICS_CONTEXT_FIELDS, *TELEMATICS_METRICS)
    for row in rows:
        parts: list[str] = []
        for field in fields:
            value = row.get(field)
            if isinstance(value, datetime):
                text = _normalise_timestamp(value).isoformat()
            elif isinstance(value, float):
                text = format(value, ".17g")
            else:
                text = str(value)
            parts.append(f"{field}={text}")
        digest.update("|".join(parts).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _source_signature(
    row_digests: Mapping[str, str],
    parameters: Mapping[str, Any],
) -> str:
    payload = json.dumps(
        {"parameters": _jsonable(parameters), "row_digests": dict(sorted(row_digests.items()))},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


async def _resolve_vehicle_analysis_window(
    session: Any,
    vehicle_id: str,
    *,
    source_from: datetime | None,
    source_to: datetime | None,
    history_hours: float,
) -> tuple[datetime | None, datetime | None, datetime | None]:
    """Resolve one vehicle's actual fetch bounds inside a shared domain
    source plan.

    Returns ``(vehicle_source_from, vehicle_source_to, vehicle_visible_to)``.

    A shared domain-level source plan hands every selected vehicle the same
    ``source_from``/``source_to``, but an individual vehicle's own telemetry
    may end earlier than the domain-wide ``source_to`` (e.g. the domain
    cursor advanced on other vehicles' data). When both bounds are
    supplied, this re-anchors the vehicle to its own latest telemetry
    visible at or before ``source_to`` (never later than that cutoff) and
    then takes ``history_hours`` back from there.

    When ``source_from``/``source_to`` are ``None`` (no domain plan bounds
    -- an ad hoc / non-scheduler call), the bounds pass through unchanged
    and ``fetch_vehicle_rows`` falls back to its own latest-anchored
    ``history_hours`` window per vehicle: unchanged behavior.

    ``vehicle_visible_to`` is ``None`` when the vehicle has no telemetry
    visible at or before ``source_to`` at all; in that case the original
    domain bounds are returned unchanged so ``fetch_vehicle_rows`` raises
    its own accurate "no telemetry" error rather than silently skipping the
    vehicle or substituting other data.
    """

    if source_from is None or source_to is None:
        return source_from, source_to, None
    vehicle_visible_to = await get_vehicle_visible_latest_timestamp(session, vehicle_id, source_to=source_to)
    if vehicle_visible_to is None:
        return source_from, source_to, None
    vehicle_visible_to = _normalise_timestamp(vehicle_visible_to)
    vehicle_source_from = vehicle_visible_to - timedelta(hours=history_hours)
    return vehicle_source_from, vehicle_visible_to, vehicle_visible_to


def _algorithm_version() -> str | None:
    try:
        return version("tigramite")
    except PackageNotFoundError:
        return None


def _analyse_vehicle(
    vehicle_id: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    algorithm: CausalAlgorithm,
    tau_max: int,
    pc_alpha: float,
    test_contemporaneous: bool,
    algorithm_config: dict[str, Any] | None,
    panel_config: TelematicsPanelConfig,
    filter_config: TelematicsFilterConfig,
) -> _VehicleAnalysis:
    records = rows_to_telematics_records(rows)
    panel_started = time.perf_counter()
    panel_result = build_telematics_panel(records, config=panel_config)
    panel_runtime = time.perf_counter() - panel_started
    if panel_result.panel.shape[1] < 2:
        raise ValueError(f"Telematics vehicle {vehicle_id} has fewer than two usable physical signals.")
    values = panel_result.panel.to_numpy(dtype=float)
    metrics = tuple(str(column) for column in panel_result.panel.columns)
    causal_discovery_started = time.perf_counter()
    if algorithm == "lpcmci":
        effective_tau_min_value = 0 if test_contemporaneous else 1
        logger.info(
            "causal_lpcmci_input_ready",
            domain="telematics",
            asset_id=vehicle_id,
            vehicle_id=vehicle_id,
            analytical_rows=len(panel_result.panel),
            variables_used=len(metrics),
            variable_names=list(metrics),
            tau_min=effective_tau_min_value,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            test_contemporaneous=test_contemporaneous,
            effective_algorithm_config=dict(algorithm_config or {}),
            panel_runtime_seconds=round(panel_runtime, 3),
            matrix_shape=f"{len(panel_result.panel)}x{len(metrics)}",
        )
        tests = run_lpcmci_tests(
            values,
            metrics,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            test_contemporaneous=test_contemporaneous,
            **(algorithm_config or {}),
        )
        causal_discovery_runtime = time.perf_counter() - causal_discovery_started
        logger.info(
            "causal_lpcmci_discovery_completed",
            domain="telematics",
            asset_id=vehicle_id,
            vehicle_id=vehicle_id,
            analytical_rows=len(panel_result.panel),
            variables_used=len(metrics),
            discovery_runtime_seconds=round(causal_discovery_runtime, 3),
            raw_pag_relationship_count=len(tests),
        )
        effective_min_lag = effective_tau_min_value
    else:
        raw_tests = run_pcmci_tests(values, metrics, tau_max=tau_max, pc_alpha=pc_alpha)
        tests = pcmci_tests_as_causal_discovery_tests(raw_tests)
        causal_discovery_runtime = time.perf_counter() - causal_discovery_started
        effective_min_lag = 1
    filtered = filter_telematics_tests(
        tests,
        panel_result.metadata,
        config=replace(
            filter_config,
            min_lag=effective_min_lag,
            # See ManufacturingFilterConfig.apply_fdr_correction: PCMCI
            # rollback reproduces prior behavior exactly; LPCMCI's tests
            # are already algorithm-selected, so the default path skips it.
            apply_fdr_correction=(algorithm == "pcmci"),
        ),
    )
    return _VehicleAnalysis(
        filtered=filtered,
        analytical_rows=len(panel_result.panel),
        variables_used=metrics,
        dropped_metrics=dict(panel_result.dropped_metrics),
        missing_intervals=dict(panel_result.missing_intervals),
        transformed_metrics=tuple(panel_result.transformed_metrics),
        duplicate_records_removed=panel_result.duplicate_records_removed,
        panel_runtime_seconds=panel_runtime,
        pcmci_runtime_seconds=causal_discovery_runtime,
    )


def _source_window(frames: Mapping[str, pd.DataFrame]) -> tuple[datetime, datetime]:
    timestamps = [frame["timestamp"].min() for frame in frames.values()]
    ends = [frame["timestamp"].max() for frame in frames.values()]
    if not timestamps or any(pd.isna(value) for value in (*timestamps, *ends)):
        raise ValueError("Telemetry source window is empty.")
    return _normalise_timestamp(min(timestamps)), _normalise_timestamp(max(ends))


def _edge_result(edge: TelematicsCausalEdge) -> TelematicsCausalEdgeResult:
    return TelematicsCausalEdgeResult(
        source_metric=edge.source_metric,
        target_metric=edge.target_metric,
        scope=edge.scope,
        consensus_sign=edge.consensus_sign,
        edge_orientation=edge.edge_orientation,
        consensus_edge_mark=edge.consensus_edge_mark,
        mark_agreement=float(edge.mark_agreement),
        eligible_vehicles=edge.eligible_vehicles,
        recurring_vehicles=edge.recurring_vehicles,
        recurrence_fraction=edge.recurrence_fraction,
        sign_agreement=edge.sign_agreement,
        mean_abs_score=edge.mean_abs_score,
        median_abs_score=edge.median_abs_score,
        best_q_value=edge.best_q_value,
        min_p_value=edge.min_p_value,
        max_p_value=edge.max_p_value,
        min_q_value=edge.min_q_value,
        max_q_value=edge.max_q_value,
        observed_lags=tuple(int(value) for value in edge.observed_lags),
        observed_lag_minutes=tuple(int(value) for value in edge.observed_lag_minutes),
        vehicle_ids=tuple(str(value) for value in edge.vehicle_ids),
        evidence=tuple(edge.evidence),
    )


def _analysis_result(
    run: TelematicsCausalRun,
    edges: Sequence[TelematicsCausalEdge],
    *,
    reused: bool,
) -> TelematicsCausalAnalysisResult:
    parameters = dict(run.parameters)
    diagnostics = dict(parameters.get("diagnostics", {}))
    analysis_frequency_minutes = int(parameters.get("analysis_frequency_minutes", 5))
    return TelematicsCausalAnalysisResult(
        run_id=run.id,
        signature=run.signature,
        reused=reused,
        source_from=_normalise_timestamp(run.source_from),
        source_to=_normalise_timestamp(run.source_to),
        source_rows=int(run.source_rows),
        raw_frequency_minutes=float(parameters.get("raw_frequency_minutes", 1.0)),
        analysis_frequency_minutes=analysis_frequency_minutes,
        analysis_window_hours=float(parameters.get("history_hours", DEFAULT_HISTORY_HOURS)),
        analytical_rows_total=int(diagnostics.get("analytical_rows_total", 0)),
        minimum_analytical_rows=int(diagnostics.get("minimum_analytical_rows", 0)),
        maximum_analytical_rows=int(diagnostics.get("maximum_analytical_rows", 0)),
        minimum_variables_used=int(diagnostics.get("minimum_variables_used", 0)),
        maximum_variables_used=int(diagnostics.get("maximum_variables_used", 0)),
        tau_min=int(parameters.get("tau_min", 1)),
        tau_max=int(parameters.get("tau_max", DEFAULT_TAU_MAX)),
        maximum_lag_minutes=int(parameters.get("tau_max", DEFAULT_TAU_MAX)) * analysis_frequency_minutes,
        vehicles_requested=int(run.vehicles_requested),
        vehicles_evaluated=int(run.vehicles_evaluated),
        candidate_pairs=int(run.candidate_pairs),
        stable_edge_count=int(run.stable_edge_count),
        algorithm=run.algorithm,
        algorithm_version=run.algorithm_version,
        parameters=parameters,
        vehicle_ids=tuple(str(value) for value in run.vehicle_ids),
        computed_at=_normalise_timestamp(run.computed_at),
        edges=tuple(_edge_result(edge) for edge in edges),
    )


class TelematicsCausalService(BaseService):
    """Run, reuse, and read only vehicle-telematics causal state."""

    async def _load_run_edges(self, run: TelematicsCausalRun, *, reused: bool) -> TelematicsCausalAnalysisResult:
        edge_rows = (
            (
                await self._session.execute(
                    select(TelematicsCausalEdge)
                    .where(TelematicsCausalEdge.run_id == run.id)
                    .order_by(
                        TelematicsCausalEdge.recurrence_fraction.desc(),
                        TelematicsCausalEdge.sign_agreement.desc(),
                        TelematicsCausalEdge.mean_abs_score.desc(),
                        TelematicsCausalEdge.best_q_value.asc(),
                        TelematicsCausalEdge.source_metric.asc(),
                        TelematicsCausalEdge.target_metric.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return _analysis_result(run, edge_rows, reused=reused)

    async def _load_by_signature(self, signature: str, *, reused: bool) -> TelematicsCausalAnalysisResult | None:
        run = (
            await self._session.execute(select(TelematicsCausalRun).where(TelematicsCausalRun.signature == signature))
        ).scalar_one_or_none()
        if run is None:
            return None
        return await self._load_run_edges(run, reused=reused)

    async def get_latest(self) -> TelematicsCausalAnalysisResult | None:
        run = (
            await self._session.execute(
                select(TelematicsCausalRun)
                .order_by(TelematicsCausalRun.computed_at.desc(), TelematicsCausalRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        return await self._load_run_edges(run, reused=True)

    async def get_or_run(
        self,
        vehicle_ids: Sequence[str],
        *,
        history_hours: float = DEFAULT_HISTORY_HOURS,
        source_from: datetime | None = None,
        source_to: datetime | None = None,
        tau_max: int | None = None,
        pc_alpha: float | None = None,
        panel_config: TelematicsPanelConfig = DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config: TelematicsFilterConfig = DEFAULT_TELEMATICS_FILTER_CONFIG,
        algorithm: CausalAlgorithm = DEFAULT_ALGORITHM,
        test_contemporaneous: bool = DEFAULT_TEST_CONTEMPORANEOUS,
        algorithm_config: dict[str, Any] | None = None,
    ) -> TelematicsCausalAnalysisResult:
        """Return cached causal state or execute a new telematics analysis.

        ``algorithm`` selects LPCMCI (production default) or PCMCI
        (rollback/comparison only); it participates in the source
        signature, so switching it always triggers a fresh run.

        ``tau_max``/``pc_alpha`` default to None, resolving to the
        algorithm-specific production default (see effective_tau_max/
        effective_pc_alpha) -- an explicitly supplied value is always
        honored unchanged regardless of algorithm.
        """
        job_started = time.perf_counter()
        ids = _normalise_vehicle_ids(vehicle_ids)
        if algorithm not in ("lpcmci", "pcmci"):
            raise ValueError("algorithm must be 'lpcmci' or 'pcmci'.")
        tau_max = effective_tau_max(algorithm, tau_max)
        pc_alpha = effective_pc_alpha(algorithm, pc_alpha)
        if not isinstance(tau_max, int) or tau_max < 1:
            raise ValueError("tau_max must be a positive integer.")
        if not 0.0 < pc_alpha <= 1.0:
            raise ValueError("pc_alpha must lie in (0, 1].")
        try:
            history_hours_value = float(history_hours)
        except (TypeError, ValueError) as exc:
            raise TypeError("history_hours must be numeric.") from exc
        if not math.isfinite(history_hours_value) or history_hours_value <= 0:
            raise ValueError("history_hours must be a finite positive duration.")
        if (source_from is None) != (source_to is None):
            raise ValueError("source_from and source_to must be supplied together.")
        if source_from is not None and source_to is not None:
            source_from = _normalise_timestamp(source_from)
            source_to = _normalise_timestamp(source_to)
            if source_from >= source_to:
                raise ValueError("source_from must be earlier than source_to.")

        analysis_minutes = _analysis_frequency_minutes(panel_config.analysis_frequency)
        frames: dict[str, pd.DataFrame] = {}
        row_digests: dict[str, str] = {}
        raw_frequencies: list[float] = []
        for vehicle_id in ids:
            vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
                self._session,
                vehicle_id,
                source_from=source_from,
                source_to=source_to,
                history_hours=history_hours_value,
            )
            rows = await fetch_vehicle_rows(
                self._session,
                vehicle_id,
                history_hours=history_hours_value,
                source_from=vehicle_source_from,
                source_to=vehicle_source_to,
            )
            row_digests[vehicle_id] = _row_digest(rows)
            raw_frequencies.append(detect_raw_frequency_minutes(rows))
            frames[vehicle_id] = pd.DataFrame([dict(row) for row in rows])
            vehicle_analysis_from = _normalise_timestamp(rows[0]["timestamp"])
            vehicle_analysis_to = _normalise_timestamp(rows[-1]["timestamp"])
            logger.info(
                "telematics_vehicle_analysis_window",
                domain="telematics",
                vehicle_id=vehicle_id,
                domain_plan_source_from=(source_from.isoformat() if source_from is not None else None),
                domain_plan_source_to=(source_to.isoformat() if source_to is not None else None),
                vehicle_visible_to=(vehicle_visible_to.isoformat() if vehicle_visible_to is not None else None),
                vehicle_analysis_from=vehicle_analysis_from.isoformat(),
                vehicle_analysis_to=vehicle_analysis_to.isoformat(),
                requested_history_hours=history_hours_value,
                raw_rows_loaded=len(rows),
            )

        raw_frequency_minutes = float(pd.Series(raw_frequencies).mode().iloc[0])
        ratio = analysis_minutes / raw_frequency_minutes
        if ratio < 1 or not math.isclose(ratio, round(ratio), abs_tol=1e-9):
            raise ValueError(
                "analysis_frequency must be an integer multiple of the detected raw telemetry cadence. "
                f"raw_minutes={raw_frequency_minutes}, analysis_minutes={analysis_minutes}"
            )
        effective_source_from, effective_source_to = _source_window(frames)
        parameters = _configuration_parameters(
            ids,
            history_hours=history_hours_value,
            source_from=source_from,
            source_to=source_to,
            raw_frequency_minutes=raw_frequency_minutes,
            panel_config=panel_config,
            filter_config=filter_config,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            analysis_frequency_minutes=analysis_minutes,
            algorithm=algorithm,
            test_contemporaneous=test_contemporaneous,
            algorithm_config=algorithm_config,
        )
        signature = _source_signature(row_digests, parameters)
        existing = await self._load_by_signature(signature, reused=True)
        if existing is not None:
            return existing

        analyses: list[_VehicleAnalysis] = []
        asset_total = len(ids)
        successful_assets = 0
        domain_loop_started = time.perf_counter()
        for asset_index, vehicle_id in enumerate(ids, start=1):
            logger.info(
                "causal_asset_started",
                domain="telematics",
                algorithm=algorithm,
                asset_id=vehicle_id,
                asset_index=asset_index,
                asset_total=asset_total,
                tau_max=tau_max,
                pc_alpha=pc_alpha,
            )
            asset_started = time.perf_counter()
            rows = frames[vehicle_id].to_dict(orient="records")
            analysis = await asyncio.to_thread(
                _analyse_vehicle,
                vehicle_id,
                rows,
                algorithm=algorithm,
                tau_max=tau_max,
                pc_alpha=pc_alpha,
                test_contemporaneous=test_contemporaneous,
                algorithm_config=algorithm_config,
                panel_config=panel_config,
                filter_config=filter_config,
            )
            analyses.append(analysis)
            successful_assets += 1
            logger.info(
                "causal_asset_completed",
                domain="telematics",
                algorithm=algorithm,
                asset_id=vehicle_id,
                asset_index=asset_index,
                asset_total=asset_total,
                runtime_seconds=round(time.perf_counter() - asset_started, 3),
                variables_used=len(analysis.variables_used),
                analytical_rows=analysis.analytical_rows,
                edge_count=len(analysis.filtered.accepted_edges),
            )

        logger.info(
            "causal_domain_completed",
            domain="telematics",
            algorithm=algorithm,
            asset_total=asset_total,
            successful_assets=successful_assets,
            total_runtime_seconds=round(time.perf_counter() - domain_loop_started, 3),
            tau_max=tau_max,
            pc_alpha=pc_alpha,
        )

        candidate_pairs = len(
            {
                (source, target)
                for analysis in analyses
                for source in analysis.variables_used
                for target in analysis.variables_used
                if source != target
            }
        )
        stability = aggregate_telematics_stability(
            [analysis.filtered for analysis in analyses],
            analysis_frequency_minutes=analysis_minutes,
            config=filter_config,
            candidate_pairs=candidate_pairs,
        )
        if stability.vehicles_evaluated != len(ids):
            raise RuntimeError("Telematics stability count does not match the evaluated vehicle cohort.")

        diagnostics = {
            "raw_rows_considered": int(sum(len(frame) for frame in frames.values())),
            "raw_long_records_loaded": int(
                sum(len(rows_to_telematics_records(frame.to_dict(orient="records"))) for frame in frames.values())
            ),
            "analytical_rows_total": int(sum(analysis.analytical_rows for analysis in analyses)),
            "minimum_analytical_rows": int(min(analysis.analytical_rows for analysis in analyses)),
            "maximum_analytical_rows": int(max(analysis.analytical_rows for analysis in analyses)),
            "minimum_variables_used": int(min(len(analysis.variables_used) for analysis in analyses)),
            "maximum_variables_used": int(max(len(analysis.variables_used) for analysis in analyses)),
            "vehicle_panels": {
                vehicle_id: {
                    "analytical_rows": analysis.analytical_rows,
                    "variables_used": list(analysis.variables_used),
                    "dropped_metrics": analysis.dropped_metrics,
                    "missing_intervals": analysis.missing_intervals,
                    "transformed_metrics": list(analysis.transformed_metrics),
                    "duplicate_records_removed": analysis.duplicate_records_removed,
                    "panel_runtime_seconds": round(analysis.panel_runtime_seconds, 6),
                    # Algorithm-neutral name; pcmci_runtime_seconds below is
                    # kept as a backward-compatible alias (identical value).
                    "causal_discovery_runtime_seconds": round(analysis.pcmci_runtime_seconds, 6),
                    "pcmci_runtime_seconds": round(analysis.pcmci_runtime_seconds, 6),
                    "boundary_isolation": "one_vehicle_panel",
                }
                for vehicle_id, analysis in zip(ids, analyses, strict=True)
            },
            "causal_discovery_runtime_seconds": round(
                sum(analysis.pcmci_runtime_seconds for analysis in analyses), 6
            ),
            "pcmci_runtime_seconds": round(sum(analysis.pcmci_runtime_seconds for analysis in analyses), 6),
            "panel_runtime_seconds": round(sum(analysis.panel_runtime_seconds for analysis in analyses), 6),
            "causal_job_runtime_before_persistence_seconds": round(time.perf_counter() - job_started, 6),
            "per_vehicle_source_windows": {
                vehicle_id: {
                    "source_from": _normalise_timestamp(frame["timestamp"].min()).isoformat(),
                    "source_to": _normalise_timestamp(frame["timestamp"].max()).isoformat(),
                    "source_rows": int(len(frame)),
                }
                for vehicle_id, frame in frames.items()
            },
        }
        persisted_parameters = {**parameters, "diagnostics": diagnostics}
        run_id = uuid.uuid4()
        run_table = TelematicsCausalRun.__table__
        insert_run = (
            pg_insert(run_table)
            .values(
                id=run_id,
                signature=signature,
                source_from=effective_source_from,
                source_to=effective_source_to,
                source_rows=int(sum(len(frame) for frame in frames.values())),
                vehicles_requested=len(ids),
                vehicles_evaluated=stability.vehicles_evaluated,
                candidate_pairs=stability.candidate_pairs,
                stable_edge_count=len(stability.stable_edges),
                algorithm=_algorithm_label(algorithm),
                algorithm_version=_algorithm_version(),
                parameters=persisted_parameters,
                vehicle_ids=list(ids),
                computed_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_ai_telematics_runs_signature")
            .returning(run_table.c.id)
        )
        inserted_run_id = (await self._session.execute(insert_run)).scalar_one_or_none()
        if inserted_run_id is None:
            raced = await self._load_by_signature(signature, reused=True)
            if raced is None:
                raise RuntimeError("Telematics signature conflicted but the persisted run could not be reloaded.")
            return raced

        persisted_edges = [
            TelematicsCausalEdge(
                run_id=inserted_run_id,
                source_metric=edge.source_metric,
                target_metric=edge.target_metric,
                scope=edge.scope,
                consensus_sign=edge.consensus_sign,
                edge_orientation=edge.consensus_edge_orientation,
                consensus_edge_mark=edge.consensus_edge_mark,
                mark_agreement=float(edge.mark_agreement),
                eligible_vehicles=edge.eligible_vehicles,
                recurring_vehicles=edge.recurring_vehicles,
                recurrence_fraction=float(edge.recurrence_fraction),
                sign_agreement=float(edge.sign_agreement),
                mean_abs_score=float(edge.mean_abs_score),
                median_abs_score=float(edge.median_abs_score),
                best_q_value=float(edge.best_q_value),
                min_p_value=float(edge.min_p_value),
                max_p_value=float(edge.max_p_value),
                min_q_value=float(edge.min_q_value),
                max_q_value=float(edge.max_q_value),
                observed_lags=list(edge.observed_lags),
                observed_lag_minutes=list(edge.observed_lag_minutes),
                vehicle_ids=list(edge.vehicle_ids),
                evidence=list(edge.evidence),
            )
            for edge in stability.stable_edges
        ]
        if persisted_edges:
            self._session.add_all(persisted_edges)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        persisted = await self._load_by_signature(signature, reused=False)
        if persisted is None:
            raise RuntimeError("Telematics causal state committed but could not be reloaded.")
        if persisted.stable_edge_count != len(persisted.edges):
            raise RuntimeError("Persisted telematics edge count does not match run metadata.")
        return persisted


__all__ = [
    "DEFAULT_ALGORITHM",
    "DEFAULT_PC_ALPHA",
    "DEFAULT_TAU_MAX",
    "DEFAULT_TEST_CONTEMPORANEOUS",
    "LPCMCI_DEFAULT_PC_ALPHA",
    "LPCMCI_DEFAULT_TAU_MAX",
    "PCMCI_DEFAULT_PC_ALPHA",
    "PCMCI_DEFAULT_TAU_MAX",
    "CausalAlgorithm",
    "TelematicsCausalAnalysisResult",
    "TelematicsCausalEdgeResult",
    "TelematicsCausalService",
    "effective_pc_alpha",
    "effective_tau_max",
]
