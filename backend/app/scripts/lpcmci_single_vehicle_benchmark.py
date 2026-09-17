"""Developer/profiling benchmark: ONE telematics vehicle through the real
production preprocessing + LPCMCI path, at multiple history-window sizes.

Why this exists
----------------
Production LPCMCI profiling showed a single vehicle (VEHUNIT_SYN_0001275,
994 analytical rows x 16 variables, tau_max=2, pc_alpha=0.10,
test_contemporaneous=True) staying inside Tigramite's LPCMCI.run_lpcmci()
for 20+ minutes at ~300% CPU. Preprocessing/database/scheduler overhead is
already known not to be the bottleneck (panel_runtime_seconds=0.756s), so
before changing ANY production behavior (algorithm parameters, conditioning
limits, multiprocessing), we need controlled, repeatable measurements of how
LPCMCI's own runtime scales with history-window size for one real vehicle.

What this does and does not do
-------------------------------
- Fetches exactly ONE vehicle's real rows via the SAME production loader
  (``fetch_vehicle_rows``) the scheduler/service use, at a given
  ``history_hours`` window. Read-only against the database.
- Runs the SAME production per-vehicle analysis function
  (``app.services.telematics_causal._analyse_vehicle``), unmodified --
  meaning the SAME preprocessing pipeline, the SAME
  ``run_lpcmci_tests()`` call, the SAME resolved tau_max/pc_alpha/tau_min
  (via ``effective_tau_max``/``effective_pc_alpha``, never hardcoded here),
  and the SAME ``causal_lpcmci_input_ready``/``causal_lpcmci_discovery_
  completed`` structured logs.
- Never calls ``TelematicsCausalService.get_or_run()`` (or
  ``ManufacturingCausalService``), so it never inserts into
  ``telematics_causal_runs``/``telematics_causal_edges`` and never touches
  ``causal_scheduler_state``/``causal_ingestion_state``. There is nothing
  in this module for a live scheduler tick to "see".
- Never imports or starts ``app.scheduler.causal_scheduler`` -- EXCEPT for
  ``--window scheduler-plan`` mode, which deliberately imports and calls the
  real, read-only ``build_telematics_source_plan()`` (see below) but never
  the scheduler's execution/persistence functions.
- Runs each window's CPU-bound panel+LPCMCI work in a killable subprocess
  with a hard wall-clock timeout, so a pathological LPCMCI call is
  terminated (not just abandoned-but-still-running) rather than being able
  to consume hours of CPU unbounded. This subprocess use is scoped
  entirely to this diagnostic tool's timeout safety mechanism -- it is not
  production parallelism and does not touch the scheduler's sequential
  per-asset execution.
- Only runs automatically-invoked code when executed as
  ``python -m app.scripts.lpcmci_single_vehicle_benchmark`` (the
  ``if __name__ == "__main__"`` guard). Importing this module (e.g. from
  tests) never starts a benchmark, a subprocess, or a database session.

Diagnostic variable exclusion (--exclude-metric)
-------------------------------------------------
The current/effective production window's matrix carries 16 variables
where the 24h/48h benchmarks carry 15 -- the extra variable being
``transmission_slip_ms``. ``--exclude-metric`` isolates that variable's
effect on LPCMCI's own runtime, WITHOUT touching production code: real
``build_telematics_panel()`` preprocessing still runs completely
unmodified and determines the full surviving variable set exactly as
production would; the requested metric(s) are then dropped from the
resulting panel -- diagnostic-only, benchmark-side -- strictly AFTER
preprocessing and BEFORE the matrix is handed to ``run_lpcmci_tests()``.
This never touches ``TelematicsCausalService``, ``Settings``, the
scheduler, or any database table -- it exists only inside this script's
own subprocess worker.

Scheduler-plan mode (--window scheduler-plan)
-----------------------------------------------
The 24h/48h/current modes above anchor each fetch to the requested
VEHICLE's own latest observation. The live scheduler does not: it anchors
to the DOMAIN-WIDE telematics ingestion cursor (the replay watermark
shared across all vehicles) via ``build_telematics_source_plan()``, which
can select a materially different [source_from, source_to] window than a
per-vehicle latest anchor would -- this is exactly why a real scheduler
run (994 analytical rows) diverged so sharply from this benchmark's
"current" mode (2016 analytical rows) for the identical vehicle.

``--window scheduler-plan`` reproduces that divergence by calling the
REAL, unmodified ``app.scheduler.causal_scheduler.build_telematics_source_
plan()`` -- the same function ``_run_telematics_job()`` calls -- so the
scheduler's watermark/window arithmetic is never reimplemented here. It:

1. Reads (never writes) the current replay clock position
   (``CausalReplayState.simulation_as_of`` via ``get_replay_state(...,
   initialize=False)``) and the telematics ingestion cursor
   (``_domain_cursor(session, "telematics")``, also read-only).
2. Calls the real ``build_telematics_source_plan()`` to get the exact
   ``vehicle_ids``/``source_from``/``source_to``/``signature`` the
   scheduler would currently compute.
3. Verifies the requested vehicle is actually IN that plan's
   ``vehicle_ids`` -- if not, returns an explicit FAILED status rather
   than silently substituting a different window.
4. Fetches ONLY that vehicle's rows bounded by the plan's own
   ``source_from``/``source_to`` (the real ``fetch_vehicle_rows()``
   called with explicit bounds, exactly as ``TelematicsCausalService.
   get_or_run()`` does when the scheduler passes them -- NOT this
   script's latest-anchored history_hours path).
5. Runs the identical production preprocessing + ``run_lpcmci_tests()``
   path as the other modes (no metric exclusion), through the same
   killable subprocess + timeout mechanism.

It NEVER calls ``run_scheduler_once``/``scheduler_loop``/
``_run_telematics_job``/``_service_domain`` (the scheduler's own
execution entry points), ``TelematicsCausalService.get_or_run()``,
``ensure_scheduler_states()``, ``advance_replay_clock()``, any advisory
lock function, or ``update_scheduler_state()`` -- so it cannot advance the
replay watermark, create/mutate scheduler or ingestion state, or acquire
the scheduler's advisory lock, regardless of how many times it runs.

Usage
-----
    # Exactly the 24-hour window (the mandated first benchmark):
    python -m app.scripts.lpcmci_single_vehicle_benchmark --window 24h

    # 24h, then 48h, then the current/effective production window (168h),
    # stopping automatically after the first window that does not COMPLETE:
    python -m app.scripts.lpcmci_single_vehicle_benchmark --window all

    # A different vehicle, or a shorter/longer per-window timeout:
    python -m app.scripts.lpcmci_single_vehicle_benchmark \\
        --vehicle-id VEHUNIT_SYN_0001275 --window 24h --timeout-seconds 900

    # Diagnostic: current window, excluding transmission_slip_ms only:
    python -m app.scripts.lpcmci_single_vehicle_benchmark \\
        --vehicle-id VEHUNIT_SYN_0001275 --window current \\
        --exclude-metric transmission_slip_ms --timeout-seconds 180

    # Diagnostic: reproduce EXACTLY the data slice the live telematics
    # scheduler would currently pass to TelematicsCausalService for this
    # vehicle (its replay-cursor-anchored source plan, not this script's
    # own latest-anchored "current" window) -- without starting the
    # scheduler and without persisting or mutating anything:
    python -m app.scripts.lpcmci_single_vehicle_benchmark \\
        --vehicle-id VEHUNIT_SYN_0001275 --window scheduler-plan \\
        --timeout-seconds 180
"""

from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing as mp
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Literal

from app.ai.causal.telematics_loader import (
    DEFAULT_HISTORY_HOURS,
    TELEMATICS_METRICS,
    fetch_vehicle_rows,
)
from app.ai.causal.telematics_panel import (
    DEFAULT_TELEMATICS_PANEL_CONFIG,
    TelematicsPanelConfig,
)
from app.database.session import get_session_factory
from app.services.telematics_causal import (
    DEFAULT_TELEMATICS_FILTER_CONFIG,
    TelematicsFilterConfig,
    effective_pc_alpha,
    effective_tau_max,
    effective_tau_min,
)

#: Vehicle this benchmark is scoped to, per the production LPCMCI profile
#: this tool exists to investigate. Overridable via --vehicle-id for other
#: single-vehicle investigations, but always exactly one vehicle.
DEFAULT_VEHICLE_ID = "VEHUNIT_SYN_0001275"

#: History-window sizes, run in this order. "current" mirrors production's
#: own default exactly (imported, never hardcoded) so it can never silently
#: drift from what the live scheduler actually requests.
WindowLabel = Literal["24h", "48h", "current", "scheduler-plan"]
WINDOW_ORDER: tuple[WindowLabel, ...] = ("24h", "48h", "current")
WINDOW_HOURS: dict[WindowLabel, float] = {
    "24h": 24.0,
    "48h": 48.0,
    "current": DEFAULT_HISTORY_HOURS,
}

#: "scheduler-plan" is deliberately absent from WINDOW_ORDER/WINDOW_HOURS:
#: it has fundamentally different fetch semantics (scheduler-visible
#: bounds, not a per-vehicle latest-anchored history_hours window) and its
#: own dedicated orchestration (run_scheduler_plan_benchmark), never part
#: of the --window all auto-sequence.
SCHEDULER_PLAN_WINDOW_LABEL: WindowLabel = "scheduler-plan"

#: Default per-window wall-clock budget. A window that does not complete
#: within this many seconds is recorded as TIMED_OUT and, in --window all
#: mode, no further (larger) windows are attempted.
DEFAULT_TIMEOUT_SECONDS = 1200.0

#: Recommended (not enforced-as-default) budget for --window scheduler-plan,
#: per the controlled variable-sensitivity experiment this mode exists for.
RECOMMENDED_SCHEDULER_PLAN_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class BenchmarkRecord:
    vehicle_id: str
    window_label: str
    requested_history_hours: float
    status: Literal["COMPLETED", "TIMED_OUT", "FAILED"]
    source_from: str | None
    source_to: str | None
    raw_rows_loaded: int | None
    analytical_rows: int | None
    variables_used: int | None
    variable_names: list[str] | None
    matrix_shape: str | None
    panel_runtime_seconds: float | None
    causal_discovery_runtime_seconds: float | None
    total_runtime_seconds: float
    raw_pag_relationship_count: int | None
    tau_min: int
    tau_max: int
    pc_alpha: float
    test_contemporaneous: bool
    algorithm_config: dict[str, Any]
    excluded_metrics: list[str]
    metrics_before_exclusion: list[str] | None
    metrics_after_exclusion: list[str] | None
    error: str | None = None
    # --window scheduler-plan diagnostics only; all remain their defaults
    # (False/None) for the 24h/48h/current/all modes.
    scheduler_plan_mode: bool = False
    simulation_as_of: str | None = None
    plan_source_from: str | None = None
    plan_source_to: str | None = None
    plan_vehicle_count: int | None = None
    requested_vehicle_in_plan: bool | None = None
    plan_source_signature: str | None = None


def _worker_run_panel_and_lpcmci(
    vehicle_id: str,
    rows: list[dict[str, Any]],
    panel_config: TelematicsPanelConfig,
    filter_config: TelematicsFilterConfig,
    tau_max: int,
    pc_alpha: float,
    test_contemporaneous: bool,
    algorithm_config: dict[str, Any] | None,
    excluded_metrics: frozenset[str],
    result_queue: "mp.Queue[dict[str, Any]]",
) -> None:
    """Runs INSIDE the killable subprocess.

    With no exclusion requested (the default, existing behavior): calls the
    real, unmodified production per-vehicle analysis function directly --
    no reimplementation of preprocessing or discovery logic lives here.

    With ``excluded_metrics`` non-empty (diagnostic-only): re-composes the
    SAME real production functions ``_analyse_vehicle`` itself calls, in
    the same order (rows_to_telematics_records -> build_telematics_panel ->
    run_lpcmci_tests), because faithfully reusing _analyse_vehicle as a
    single call offers no hook between preprocessing and discovery. The
    excluded metric(s) are dropped from the panel strictly AFTER
    build_telematics_panel() has already determined the full production-
    surviving variable set, and strictly BEFORE run_lpcmci_tests() sees the
    matrix -- diagnostic-only, never inside a production module.
    """

    try:
        # Imported inside the worker (spawn context re-imports the module
        # anyway) so a subprocess-import failure surfaces as a clean FAILED
        # result rather than crashing benchmark orchestration.
        if not excluded_metrics:
            from app.services.telematics_causal import _analyse_vehicle

            analysis = _analyse_vehicle(
                vehicle_id,
                rows,
                algorithm="lpcmci",
                tau_max=tau_max,
                pc_alpha=pc_alpha,
                test_contemporaneous=test_contemporaneous,
                algorithm_config=algorithm_config,
                panel_config=panel_config,
                filter_config=filter_config,
            )
            variable_names = list(analysis.variables_used)
            result_queue.put(
                {
                    "status": "COMPLETED",
                    "analytical_rows": analysis.analytical_rows,
                    "variables_used": len(analysis.variables_used),
                    "variable_names": variable_names,
                    "panel_runtime_seconds": analysis.panel_runtime_seconds,
                    "causal_discovery_runtime_seconds": analysis.pcmci_runtime_seconds,
                    "raw_pag_relationship_count": analysis.filtered.total_tests,
                    "metrics_before_exclusion": variable_names,
                    "metrics_after_exclusion": variable_names,
                }
            )
            return

        from app.ai.causal.pcmci_engine import run_lpcmci_tests
        from app.ai.causal.telematics_loader import rows_to_telematics_records
        from app.ai.causal.telematics_panel import build_telematics_panel

        records = rows_to_telematics_records(rows)

        panel_started = time.perf_counter()
        panel_result = build_telematics_panel(records, config=panel_config)
        panel_runtime = time.perf_counter() - panel_started

        panel = panel_result.panel
        metrics_before_exclusion = [str(column) for column in panel.columns]

        # Diagnostic-only column drop: matches on the metric name AFTER
        # the "<vehicle_id>||<metric>" separator, applied strictly after
        # real production preprocessing has already run to completion.
        columns_to_drop = [
            column for column in panel.columns if str(column).split("||", 1)[-1] in excluded_metrics
        ]
        reduced_panel = panel.drop(columns=columns_to_drop)
        metrics_after_exclusion = [str(column) for column in reduced_panel.columns]

        if reduced_panel.shape[1] < 2:
            raise ValueError(
                "fewer than two variables remain after diagnostic exclusion "
                f"of {sorted(excluded_metrics)}"
            )

        column_names = tuple(metrics_after_exclusion)

        causal_discovery_started = time.perf_counter()
        tests = run_lpcmci_tests(
            reduced_panel.to_numpy(dtype=float),
            column_names,
            tau_max=tau_max,
            pc_alpha=pc_alpha,
            test_contemporaneous=test_contemporaneous,
            **(algorithm_config or {}),
        )
        causal_discovery_runtime = time.perf_counter() - causal_discovery_started

        result_queue.put(
            {
                "status": "COMPLETED",
                "analytical_rows": len(reduced_panel),
                "variables_used": len(column_names),
                "variable_names": list(column_names),
                "panel_runtime_seconds": panel_runtime,
                "causal_discovery_runtime_seconds": causal_discovery_runtime,
                "raw_pag_relationship_count": len(tests),
                "metrics_before_exclusion": metrics_before_exclusion,
                "metrics_after_exclusion": metrics_after_exclusion,
            }
        )
    except Exception as exc:  # noqa: BLE001 - report, never crash silently
        result_queue.put({"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"})


def _benchmark_window_from_rows(
    *,
    vehicle_id: str,
    window_label: WindowLabel,
    requested_history_hours: float,
    rows: list[dict[str, Any]],
    panel_config: TelematicsPanelConfig = DEFAULT_TELEMATICS_PANEL_CONFIG,
    filter_config: TelematicsFilterConfig = DEFAULT_TELEMATICS_FILTER_CONFIG,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    algorithm_config: dict[str, Any] | None = None,
    excluded_metrics: frozenset[str] = frozenset(),
) -> BenchmarkRecord:
    """Pure (no DB access) benchmark of one already-fetched row set.

    Separated from the DB-fetch step specifically so it is directly unit-
    testable with synthetic rows -- no live database required.

    ``excluded_metrics`` is diagnostic-only (see module docstring): when
    non-empty, production preprocessing still runs unmodified and the
    named metric(s) are dropped from the resulting panel afterward, before
    run_lpcmci_tests() sees it. Default (empty) reproduces the exact
    pre-existing benchmark behavior.
    """

    algorithm = "lpcmci"
    tau_max = effective_tau_max(algorithm, None)
    pc_alpha = effective_pc_alpha(algorithm, None)
    test_contemporaneous = True
    tau_min = effective_tau_min(algorithm, test_contemporaneous)
    effective_algorithm_config = dict(algorithm_config or {})

    unknown_exclusions = sorted(set(excluded_metrics) - set(TELEMATICS_METRICS))
    if unknown_exclusions:
        raise ValueError(f"Unknown telematics metric(s) for --exclude-metric: {unknown_exclusions}")

    timestamps = [row["timestamp"] for row in rows if row.get("timestamp") is not None]
    source_from = min(timestamps) if timestamps else None
    source_to = max(timestamps) if timestamps else None

    common_fields = dict(
        vehicle_id=vehicle_id,
        window_label=window_label,
        requested_history_hours=requested_history_hours,
        source_from=source_from.isoformat() if source_from else None,
        source_to=source_to.isoformat() if source_to else None,
        raw_rows_loaded=len(rows),
        tau_min=tau_min,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        test_contemporaneous=test_contemporaneous,
        algorithm_config=effective_algorithm_config,
        excluded_metrics=sorted(excluded_metrics),
    )

    if not rows:
        return BenchmarkRecord(
            **common_fields,
            status="FAILED",
            analytical_rows=None,
            variables_used=None,
            variable_names=None,
            matrix_shape=None,
            panel_runtime_seconds=None,
            causal_discovery_runtime_seconds=None,
            total_runtime_seconds=0.0,
            raw_pag_relationship_count=None,
            metrics_before_exclusion=None,
            metrics_after_exclusion=None,
            error="no rows fetched for this vehicle/window",
        )

    ctx = mp.get_context("spawn")
    result_queue: "mp.Queue[dict[str, Any]]" = ctx.Queue()
    process = ctx.Process(
        target=_worker_run_panel_and_lpcmci,
        args=(
            vehicle_id,
            rows,
            panel_config,
            filter_config,
            tau_max,
            pc_alpha,
            test_contemporaneous,
            effective_algorithm_config,
            frozenset(excluded_metrics),
            result_queue,
        ),
    )

    started = time.perf_counter()
    process.start()
    process.join(timeout=timeout_seconds)
    total_runtime_seconds = time.perf_counter() - started

    if process.is_alive():
        # A pathological LPCMCI call: terminate rather than let it keep
        # consuming CPU in the background, and never fabricate a result.
        process.terminate()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join()
        return BenchmarkRecord(
            **common_fields,
            status="TIMED_OUT",
            analytical_rows=None,
            variables_used=None,
            variable_names=None,
            matrix_shape=None,
            panel_runtime_seconds=None,
            causal_discovery_runtime_seconds=None,
            total_runtime_seconds=total_runtime_seconds,
            raw_pag_relationship_count=None,
            metrics_before_exclusion=None,
            metrics_after_exclusion=None,
            error=f"exceeded {timeout_seconds}s wall-clock budget",
        )

    if result_queue.empty():
        return BenchmarkRecord(
            **common_fields,
            status="FAILED",
            analytical_rows=None,
            variables_used=None,
            variable_names=None,
            matrix_shape=None,
            panel_runtime_seconds=None,
            causal_discovery_runtime_seconds=None,
            total_runtime_seconds=total_runtime_seconds,
            raw_pag_relationship_count=None,
            metrics_before_exclusion=None,
            metrics_after_exclusion=None,
            error=f"worker exited (code={process.exitcode}) without a result",
        )

    payload = result_queue.get()

    if payload["status"] == "FAILED":
        return BenchmarkRecord(
            **common_fields,
            status="FAILED",
            analytical_rows=None,
            variables_used=None,
            variable_names=None,
            matrix_shape=None,
            panel_runtime_seconds=None,
            causal_discovery_runtime_seconds=None,
            total_runtime_seconds=total_runtime_seconds,
            raw_pag_relationship_count=None,
            metrics_before_exclusion=None,
            metrics_after_exclusion=None,
            error=payload["error"],
        )

    return BenchmarkRecord(
        **common_fields,
        status="COMPLETED",
        analytical_rows=payload["analytical_rows"],
        variables_used=payload["variables_used"],
        variable_names=payload["variable_names"],
        matrix_shape=f"{payload['analytical_rows']}x{payload['variables_used']}",
        panel_runtime_seconds=payload["panel_runtime_seconds"],
        causal_discovery_runtime_seconds=payload["causal_discovery_runtime_seconds"],
        total_runtime_seconds=total_runtime_seconds,
        raw_pag_relationship_count=payload["raw_pag_relationship_count"],
        metrics_before_exclusion=payload["metrics_before_exclusion"],
        metrics_after_exclusion=payload["metrics_after_exclusion"],
    )


async def _fetch_and_benchmark_window(
    session: Any,
    *,
    vehicle_id: str,
    window_label: WindowLabel,
    timeout_seconds: float,
    excluded_metrics: frozenset[str] = frozenset(),
) -> BenchmarkRecord:
    history_hours = WINDOW_HOURS[window_label]
    rows = await fetch_vehicle_rows(session, vehicle_id, history_hours=history_hours)
    return _benchmark_window_from_rows(
        vehicle_id=vehicle_id,
        window_label=window_label,
        requested_history_hours=history_hours,
        rows=[dict(row) for row in rows],
        timeout_seconds=timeout_seconds,
        excluded_metrics=excluded_metrics,
    )


async def run_benchmark(
    *,
    vehicle_id: str = DEFAULT_VEHICLE_ID,
    windows: tuple[WindowLabel, ...] = ("24h",),
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    excluded_metrics: frozenset[str] = frozenset(),
) -> list[BenchmarkRecord]:
    """Fetch + benchmark ``vehicle_id`` across ``windows``, in order, in a
    real (read-only) database session -- stopping after the first window
    that does not COMPLETE.

    ``excluded_metrics`` is diagnostic-only -- see module docstring and
    _benchmark_window_from_rows. Empty (default) reproduces exact
    pre-existing behavior.
    """

    session_factory = get_session_factory()
    records: list[BenchmarkRecord] = []
    async with session_factory() as session:
        for window_label in windows:
            record = await _fetch_and_benchmark_window(
                session,
                vehicle_id=vehicle_id,
                window_label=window_label,
                timeout_seconds=timeout_seconds,
                excluded_metrics=excluded_metrics,
            )
            records.append(record)
            if record.status != "COMPLETED":
                break
    return records


def _scheduler_plan_failed_record(
    *,
    vehicle_id: str,
    timeout_seconds: float,
    error: str,
    simulation_as_of: str | None = None,
    plan_source_from: str | None = None,
    plan_source_to: str | None = None,
    plan_vehicle_count: int | None = None,
    requested_vehicle_in_plan: bool | None = None,
    plan_source_signature: str | None = None,
) -> BenchmarkRecord:
    """A FAILED scheduler-plan record with every data field honestly
    empty -- used whenever the real plan can't be built or the requested
    vehicle isn't in it, so nothing is ever fabricated."""

    algorithm = "lpcmci"
    tau_max = effective_tau_max(algorithm, None)
    pc_alpha = effective_pc_alpha(algorithm, None)
    test_contemporaneous = True
    tau_min = effective_tau_min(algorithm, test_contemporaneous)
    return BenchmarkRecord(
        vehicle_id=vehicle_id,
        window_label=SCHEDULER_PLAN_WINDOW_LABEL,
        requested_history_hours=0.0,
        status="FAILED",
        source_from=None,
        source_to=None,
        raw_rows_loaded=None,
        analytical_rows=None,
        variables_used=None,
        variable_names=None,
        matrix_shape=None,
        panel_runtime_seconds=None,
        causal_discovery_runtime_seconds=None,
        total_runtime_seconds=0.0,
        raw_pag_relationship_count=None,
        tau_min=tau_min,
        tau_max=tau_max,
        pc_alpha=pc_alpha,
        test_contemporaneous=test_contemporaneous,
        algorithm_config={},
        excluded_metrics=[],
        metrics_before_exclusion=None,
        metrics_after_exclusion=None,
        error=error,
        scheduler_plan_mode=True,
        simulation_as_of=simulation_as_of,
        plan_source_from=plan_source_from,
        plan_source_to=plan_source_to,
        plan_vehicle_count=plan_vehicle_count,
        requested_vehicle_in_plan=requested_vehicle_in_plan,
        plan_source_signature=plan_source_signature,
    )


async def run_scheduler_plan_benchmark(
    *,
    vehicle_id: str = DEFAULT_VEHICLE_ID,
    timeout_seconds: float = RECOMMENDED_SCHEDULER_PLAN_TIMEOUT_SECONDS,
) -> BenchmarkRecord:
    """Reproduce EXACTLY the data slice the live telematics scheduler would
    currently pass to TelematicsCausalService for ``vehicle_id``, then
    benchmark it -- without starting the scheduler, without persisting
    anything, and without mutating replay/scheduler/ingestion state.

    Reuses the real, unmodified ``build_telematics_source_plan()`` (see
    module docstring for the full read-only guarantee) -- the watermark/
    window arithmetic is never reimplemented here.
    """

    # Imported here (not at module top level) so the non-scheduler-plan
    # code paths never need app.scheduler.causal_scheduler at all, and so
    # it's obvious at the call site exactly which two real, read-only
    # scheduler functions this mode depends on.
    from app.scheduler.causal_scheduler import _domain_cursor, build_telematics_source_plan
    from app.services.causal_runtime import get_replay_state, utc_now

    session_factory = get_session_factory()
    async with session_factory() as session:
        # initialize=False: a missing replay-state row must be reported,
        # never created (initialize=True would INSERT + commit a row).
        replay_state = await get_replay_state(session, initialize=False)
        if replay_state is None:
            return _scheduler_plan_failed_record(
                vehicle_id=vehicle_id,
                timeout_seconds=timeout_seconds,
                error="replay state is not initialized in this environment; the scheduler has never run here",
            )

        as_of = utc_now(replay_state.simulation_as_of)
        cursor = await _domain_cursor(session, "telematics")  # read-only

        try:
            plan = await build_telematics_source_plan(session, as_of, telematics_cursor=cursor)
        except Exception as exc:  # noqa: BLE001 - report, never crash
            return _scheduler_plan_failed_record(
                vehicle_id=vehicle_id,
                timeout_seconds=timeout_seconds,
                error=f"scheduler source plan could not be built: {type(exc).__name__}: {exc}",
                simulation_as_of=as_of.isoformat(),
            )

        requested_vehicle_in_plan = vehicle_id in plan.vehicle_ids
        if not requested_vehicle_in_plan:
            return _scheduler_plan_failed_record(
                vehicle_id=vehicle_id,
                timeout_seconds=timeout_seconds,
                error=(
                    f"{vehicle_id} is not present in the current scheduler-visible plan "
                    f"({len(plan.vehicle_ids)} vehicles selected)"
                ),
                simulation_as_of=as_of.isoformat(),
                plan_source_from=plan.source_from.isoformat(),
                plan_source_to=plan.source_to.isoformat(),
                plan_vehicle_count=len(plan.vehicle_ids),
                requested_vehicle_in_plan=False,
                plan_source_signature=plan.signature,
            )

        # Exactly the scheduler-visible bounds -- explicit source_from/
        # source_to, NOT a latest-anchored history_hours fetch. This is the
        # real production loader called exactly as TelematicsCausalService.
        # get_or_run() calls it when the scheduler supplies explicit bounds.
        rows = await fetch_vehicle_rows(
            session,
            vehicle_id,
            source_from=plan.source_from,
            source_to=plan.source_to,
        )

    record = _benchmark_window_from_rows(
        vehicle_id=vehicle_id,
        window_label=SCHEDULER_PLAN_WINDOW_LABEL,
        requested_history_hours=plan.history_hours,
        rows=[dict(row) for row in rows],
        timeout_seconds=timeout_seconds,
    )
    return replace(
        record,
        scheduler_plan_mode=True,
        simulation_as_of=as_of.isoformat(),
        plan_source_from=plan.source_from.isoformat(),
        plan_source_to=plan.source_to.isoformat(),
        plan_vehicle_count=len(plan.vehicle_ids),
        requested_vehicle_in_plan=True,
        plan_source_signature=plan.signature,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark ONE telematics vehicle through the real production "
            "preprocessing + LPCMCI path at multiple history-window sizes. "
            "Read-only; never persists causal-run/edge or scheduler state."
        )
    )
    parser.add_argument("--vehicle-id", default=DEFAULT_VEHICLE_ID)
    parser.add_argument(
        "--window",
        choices=(*WINDOW_ORDER, "all", SCHEDULER_PLAN_WINDOW_LABEL),
        default="24h",
        help="Single window (default: 24h, the mandated first benchmark); "
        "'all' to run 24h -> 48h -> current in order, stopping after the "
        "first window that does not COMPLETE; or 'scheduler-plan' to "
        "reproduce exactly the scheduler-visible data slice for this "
        "vehicle (see module docstring) instead of a latest-anchored window.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-window wall-clock budget (default: {DEFAULT_TIMEOUT_SECONDS}s). "
        "180 is recommended for a --window current --exclude-metric run, and "
        f"for --window {SCHEDULER_PLAN_WINDOW_LABEL}.",
    )
    parser.add_argument(
        "--exclude-metric",
        action="append",
        default=None,
        metavar="METRIC_NAME",
        help="DIAGNOSTIC ONLY, benchmark-scoped: drop this metric from the panel "
        "AFTER real production preprocessing determines the surviving variable "
        "set, and BEFORE run_lpcmci_tests() sees the matrix. Repeatable. Never "
        "affects TelematicsCausalService, Settings, the scheduler, or the "
        "database. Example: --exclude-metric transmission_slip_ms. Not "
        f"supported together with --window {SCHEDULER_PLAN_WINDOW_LABEL}.",
    )
    args = parser.parse_args()
    if args.exclude_metric:
        unknown = sorted(set(args.exclude_metric) - set(TELEMATICS_METRICS))
        if unknown:
            parser.error(f"--exclude-metric: unknown telematics metric(s): {unknown}")
        if args.window == SCHEDULER_PLAN_WINDOW_LABEL:
            parser.error(f"--exclude-metric is not supported with --window {SCHEDULER_PLAN_WINDOW_LABEL}")
    return args


def main() -> None:
    args = _parse_args()
    if args.window == SCHEDULER_PLAN_WINDOW_LABEL:
        plan_record = asyncio.run(
            run_scheduler_plan_benchmark(
                vehicle_id=args.vehicle_id,
                timeout_seconds=args.timeout_seconds,
            )
        )
        print(json.dumps(asdict(plan_record), indent=2, sort_keys=True, default=str))
        return

    windows: tuple[WindowLabel, ...] = WINDOW_ORDER if args.window == "all" else (args.window,)
    records = asyncio.run(
        run_benchmark(
            vehicle_id=args.vehicle_id,
            windows=windows,
            timeout_seconds=args.timeout_seconds,
            excluded_metrics=frozenset(args.exclude_metric or ()),
        )
    )
    print(json.dumps([asdict(record) for record in records], indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
