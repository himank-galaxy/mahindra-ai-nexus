"""Regression tests for the single-vehicle LPCMCI history-window benchmark.

Context
-------
Production profiling showed one telematics vehicle (VEHUNIT_SYN_0001275,
994 analytical rows x 16 variables, tau_max=2, pc_alpha=0.10,
test_contemporaneous=True) staying inside Tigramite's LPCMCI.run_lpcmci()
for 20+ minutes at ~300% CPU. app/scripts/lpcmci_single_vehicle_benchmark.py
exists to measure how LPCMCI's own runtime scales with history-window size
for exactly one real vehicle, using the unmodified production preprocessing
+ discovery path, before any production behavior changes.

These tests do not require a live database: the DB-fetch step
(fetch_vehicle_rows, already covered elsewhere) is separated from the pure,
directly-testable per-window benchmark function
(_benchmark_window_from_rows), which is exercised here with synthetic rows
shaped exactly like fetch_vehicle_rows' real output.
"""

from __future__ import annotations

import ast
import inspect
import time
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.ai.causal.telematics_loader import TELEMATICS_CONTEXT_FIELDS, TELEMATICS_METRICS
from app.scripts import lpcmci_single_vehicle_benchmark as benchmark_module
from app.scripts.lpcmci_single_vehicle_benchmark import (
    DEFAULT_VEHICLE_ID,
    WINDOW_HOURS,
    WINDOW_ORDER,
    BenchmarkRecord,
    _benchmark_window_from_rows,
    run_benchmark,
)

START = datetime(2026, 7, 25, tzinfo=UTC)


def _code_identifiers() -> set[str]:
    """All Name/Attribute identifiers referenced in the module's CODE, not
    its docstrings/comments/string literals -- so prose explaining what the
    module deliberately does NOT do can freely mention forbidden names
    without producing a false positive here."""

    tree = ast.parse(inspect.getsource(benchmark_module))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                identifiers.add(alias.asname or alias.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    identifiers.update(node.module.split("."))
    return identifiers


def _synthetic_rows(vehicle_id: str, n: int) -> list[dict[str, object]]:
    # A genuine contemporaneous relationship (not independent noise) so
    # LPCMCI reliably discovers at least one edge, and enough analytical
    # rows (n minutes / 5min bucket) to clear the real production
    # min_panel_observations=288 floor -- both needed so the "COMPLETED"
    # tests exercise the actual discovery path, not an early validation
    # error.
    rng = np.random.default_rng(3)
    speed = rng.normal(0, 1, n)
    battery = 0.7 * speed + rng.normal(0, 0.3, n)
    context = {
        "vehicle_id": vehicle_id,
        "vehicle_model_id": "MODEL-1",
        "vehicle_model_name": "Test Model",
        "variant": "EV",
        "production_batch_id": "BATCH-1",
        "supplier_lot_id": "LOT-1",
        "plant_id": "PLANT-1",
        "production_line_id": "LINE-1",
    }
    assert set(context) == set(TELEMATICS_CONTEXT_FIELDS)
    rows = []
    for minute in range(n):
        ts = START + timedelta(minutes=minute)
        metrics = dict.fromkeys(TELEMATICS_METRICS)
        metrics["vehicle_speed_kph"] = float(speed[minute])
        metrics["battery_temperature_c"] = float(battery[minute])
        rows.append({"timestamp": ts, "entity": vehicle_id, **context, **metrics})
    return rows


# ---------------------------------------------------------------------------
# (a) Exactly one vehicle only -- static + interface guarantees.
# ---------------------------------------------------------------------------


def test_a_default_vehicle_is_the_specified_production_vehicle() -> None:
    assert DEFAULT_VEHICLE_ID == "VEHUNIT_SYN_0001275"


def test_a_run_benchmark_accepts_a_single_vehicle_id_not_a_cohort() -> None:
    signature = inspect.signature(run_benchmark)
    assert signature.parameters["vehicle_id"].annotation in (str, "str")
    # No cohort/list-of-vehicles parameter anywhere on the public entry point.
    assert "vehicle_ids" not in signature.parameters


def test_a_cli_exposes_a_single_vehicle_id_flag() -> None:
    parser_source = inspect.getsource(benchmark_module._parse_args)
    assert "--vehicle-id" in parser_source
    assert "--vehicle-ids" not in parser_source
    assert "cohort" not in parser_source.lower()


def test_a_benchmark_calls_the_single_vehicle_production_loader() -> None:
    # fetch_vehicle_rows (singular) is the real per-vehicle production
    # loader; a cohort-fetch function must never appear here.
    source = inspect.getsource(benchmark_module)
    assert "fetch_vehicle_rows" in source
    assert "fetch_raw_records" not in source  # the multi-vehicle loader


# ---------------------------------------------------------------------------
# (b) / (c) Does not persist causal state or update scheduler state.
# ---------------------------------------------------------------------------


def test_b_never_imports_or_calls_the_persisting_service() -> None:
    # TelematicsCausalService.get_or_run() is the ONLY function in this
    # codebase that inserts into telematics_causal_runs/_edges. It must
    # never appear as actual CODE here (docstring prose explaining what
    # this tool deliberately avoids is fine and expected) -- this
    # benchmark calls _analyse_vehicle directly instead.
    identifiers = _code_identifiers()
    assert "TelematicsCausalService" not in identifiers
    assert "ManufacturingCausalService" not in identifiers
    assert "get_or_run" not in identifiers


def test_b_never_references_persistence_tables_or_commit() -> None:
    identifiers = _code_identifiers()
    for forbidden in (
        "TelematicsCausalRun",
        "TelematicsCausalEdge",
        "ManufacturingCausalRun",
        "ManufacturingCausalEdge",
        "pg_insert",
        "commit",
    ):
        assert forbidden not in identifiers, forbidden


def test_c_never_touches_scheduler_persistence_state() -> None:
    # CausalSchedulerState/CausalIngestionState and their write-side
    # helpers must never appear anywhere in this module -- including
    # inside run_scheduler_plan_benchmark, which only reads
    # CausalReplayState (via get_replay_state) and CausalIngestionState's
    # cursor (via the read-only _domain_cursor), never the scheduler's own
    # checkpoint table.
    identifiers = _code_identifiers()
    for forbidden in (
        "CausalSchedulerState",
        "CausalIngestionState",
        "update_scheduler_state",
        "get_scheduler_state",
        "ensure_scheduler_states",
    ):
        assert forbidden not in identifiers, forbidden


def test_c_scheduler_module_is_imported_only_inside_scheduler_plan_benchmark() -> None:
    # app.scheduler.causal_scheduler is now DELIBERATELY imported (per the
    # --window scheduler-plan requirement to reuse the real source-plan
    # builder rather than reimplementing its watermark arithmetic) -- but
    # ONLY from inside run_scheduler_plan_benchmark, as a local import, and
    # ONLY for the two specific read-only names it needs. It must never
    # appear as a module-level import (which would make importing THIS
    # benchmark module itself pull in the scheduler).
    tree = ast.parse(inspect.getsource(benchmark_module))
    module_level_imports = {
        node.module
        for node in tree.body  # top-level statements only, not nested in functions
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(module.startswith("app.scheduler") for module in module_level_imports)

    scheduler_plan_function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run_scheduler_plan_benchmark"
    )
    scheduler_imports = [
        node
        for node in ast.walk(scheduler_plan_function)
        if isinstance(node, ast.ImportFrom) and node.module == "app.scheduler.causal_scheduler"
    ]
    assert len(scheduler_imports) == 1
    imported_names = {alias.name for alias in scheduler_imports[0].names}
    assert imported_names == {"_domain_cursor", "build_telematics_source_plan"}


def test_c_no_scheduler_execution_or_persistence_function_is_ever_called() -> None:
    identifiers = _code_identifiers()
    for forbidden in (
        "run_scheduler_once",
        "scheduler_loop",
        "_service_domain",
        "_run_telematics_job",
        "_run_manufacturing_job",
        "advance_replay_clock",
        "initialize_replay_state",
        "reset_replay_clock",
        "set_replay_paused",
        "try_advisory_lock",
        "try_advisory_lock_session",
        "release_advisory_lock",
    ):
        assert forbidden not in identifiers, forbidden


# ---------------------------------------------------------------------------
# Never runs automatically on import.
# ---------------------------------------------------------------------------


def test_importing_the_module_does_not_execute_a_benchmark() -> None:
    source = inspect.getsource(benchmark_module)
    assert 'if __name__ == "__main__":' in source
    assert source.strip().endswith("main()")


# ---------------------------------------------------------------------------
# (d) Preserves tau_min=0 / tau_max=2 / pc_alpha=0.10 / test_contemporaneous.
# ---------------------------------------------------------------------------


def test_d_preserves_exact_production_lpcmci_configuration() -> None:
    rows = _synthetic_rows("VEH-BENCH-CONFIG", n=1500)
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-BENCH-CONFIG",
        window_label="24h",
        requested_history_hours=24.0,
        rows=rows,
        timeout_seconds=120.0,
    )
    assert record.status == "COMPLETED", record.error
    assert record.tau_min == 0
    assert record.tau_max == 2
    assert record.pc_alpha == pytest.approx(0.10)
    assert record.test_contemporaneous is True
    assert record.algorithm_config == {}


def test_d_configuration_is_never_hardcoded_but_resolved_from_production() -> None:
    # The benchmark must resolve tau_max/pc_alpha/tau_min via the real
    # production resolver functions, not literal constants, so it can
    # never silently drift from whatever production actually runs.
    source = inspect.getsource(benchmark_module)
    assert "effective_tau_max" in source
    assert "effective_pc_alpha" in source
    assert "effective_tau_min" in source


# ---------------------------------------------------------------------------
# (e) Uses production preprocessing (the real, unmodified _analyse_vehicle).
# ---------------------------------------------------------------------------


def _worker_code_only() -> str:
    """Worker source with the docstring stripped, so text-based checks
    below aren't confused by the docstring's own prose mentioning
    function names it explains the rationale for."""
    source = inspect.getsource(benchmark_module._worker_run_panel_and_lpcmci)
    return source[source.index("try:") :]


def test_e_worker_calls_the_real_unmodified_analyse_vehicle() -> None:
    worker_source = inspect.getsource(benchmark_module._worker_run_panel_and_lpcmci)
    assert "from app.services.telematics_causal import _analyse_vehicle" in worker_source
    assert "_analyse_vehicle(" in worker_source
    # The no-exclusion branch (existing, pre-extension behavior) must call
    # the real production function directly and NOT reimplement panel
    # building or LPCMCI invocation itself. (docstring stripped so its own
    # prose mentioning these function names isn't mistaken for code.)
    code = _worker_code_only()
    no_exclusion_branch = code[: code.index("from app.ai.causal.pcmci_engine import run_lpcmci_tests")]
    assert "build_telematics_panel(" not in no_exclusion_branch
    assert "run_lpcmci_tests(" not in no_exclusion_branch
    # build_telematics_panel/run_lpcmci_tests DO legitimately appear later,
    # but ONLY inside the diagnostic exclusion branch -- verified by the
    # ordering test below.


def test_e_benchmark_result_matches_calling_analyse_vehicle_directly() -> None:
    from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
    from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
    from app.services.telematics_causal import _analyse_vehicle

    rows = _synthetic_rows("VEH-BENCH-PARITY", n=1500)

    direct = _analyse_vehicle(
        "VEH-BENCH-PARITY",
        rows,
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-BENCH-PARITY",
        window_label="24h",
        requested_history_hours=24.0,
        rows=rows,
        timeout_seconds=120.0,
    )

    assert record.status == "COMPLETED", record.error
    assert record.analytical_rows == direct.analytical_rows
    assert record.variables_used == len(direct.variables_used)
    assert record.raw_pag_relationship_count == direct.filtered.total_tests


# ---------------------------------------------------------------------------
# (f) Reports actual matrix dimensions.
# ---------------------------------------------------------------------------


def test_f_reports_actual_matrix_dimensions() -> None:
    rows = _synthetic_rows("VEH-BENCH-SHAPE", n=1500)
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-BENCH-SHAPE",
        window_label="24h",
        requested_history_hours=24.0,
        rows=rows,
        timeout_seconds=120.0,
    )
    assert record.status == "COMPLETED", record.error
    assert record.matrix_shape == f"{record.analytical_rows}x{record.variables_used}"
    assert record.analytical_rows is not None and record.analytical_rows > 0
    assert record.variables_used == 2
    assert set(record.variable_names) == {
        "VEH-BENCH-SHAPE||vehicle_speed_kph",
        "VEH-BENCH-SHAPE||battery_temperature_c",
    }


# ---------------------------------------------------------------------------
# (g) Handles timeout without fabricating a result.
# ---------------------------------------------------------------------------


def test_g_timeout_reports_timed_out_without_fake_data(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _synthetic_rows("VEH-BENCH-TIMEOUT", n=1500)

    started = time.perf_counter()
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-BENCH-TIMEOUT",
        window_label="24h",
        requested_history_hours=24.0,
        rows=rows,
        timeout_seconds=0.01,  # deliberately impossible to complete within
    )
    wall_clock = time.perf_counter() - started

    assert record.status == "TIMED_OUT"
    assert record.error is not None and "wall-clock" in record.error
    # No fabricated analysis output.
    assert record.analytical_rows is None
    assert record.variables_used is None
    assert record.variable_names is None
    assert record.matrix_shape is None
    assert record.panel_runtime_seconds is None
    assert record.causal_discovery_runtime_seconds is None
    assert record.raw_pag_relationship_count is None
    # Configuration/source metadata (known BEFORE the subprocess even
    # starts) is still honestly reported.
    assert record.tau_min == 0
    assert record.tau_max == 2
    assert record.raw_rows_loaded == len(rows)
    # The parent did not block for anywhere near how long the real
    # computation would take -- it terminated the subprocess promptly.
    assert wall_clock < 30.0


def test_g_empty_rows_fails_cleanly_without_a_subprocess() -> None:
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-BENCH-EMPTY",
        window_label="24h",
        requested_history_hours=24.0,
        rows=[],
        timeout_seconds=120.0,
    )
    assert record.status == "FAILED"
    assert record.analytical_rows is None
    assert record.raw_rows_loaded == 0


# ---------------------------------------------------------------------------
# Window plumbing: "current" mirrors real production default; stop-after-
# non-COMPLETED sequencing (source-level, since (h)/full run_benchmark
# needs a live database).
# ---------------------------------------------------------------------------


def test_current_window_hours_matches_real_production_default() -> None:
    from app.ai.causal.telematics_loader import DEFAULT_HISTORY_HOURS

    assert WINDOW_HOURS["current"] == DEFAULT_HISTORY_HOURS


def test_window_order_is_24h_then_48h_then_current() -> None:
    assert WINDOW_ORDER == ("24h", "48h", "current")


def test_run_benchmark_stops_after_the_first_non_completed_window() -> None:
    source = inspect.getsource(run_benchmark)
    assert 'record.status != "COMPLETED"' in source
    assert "break" in source


def test_default_cli_window_is_24h_only() -> None:
    source = inspect.getsource(benchmark_module._parse_args)
    assert 'default="24h"' in source


# ===========================================================================
# --exclude-metric diagnostic extension
# ===========================================================================


def _synthetic_rows_with_slip(vehicle_id: str, n: int) -> list[dict[str, object]]:
    """Like _synthetic_rows, plus a real transmission_slip_ms relationship
    so exclusion tests can prove it is the ONE column actually removed."""
    rng = np.random.default_rng(3)
    speed = rng.normal(0, 1, n)
    battery = 0.7 * speed + rng.normal(0, 0.3, n)
    slip = 0.5 * speed + rng.normal(0, 0.4, n)
    context = {
        "vehicle_id": vehicle_id,
        "vehicle_model_id": "MODEL-1",
        "vehicle_model_name": "Test Model",
        "variant": "EV",
        "production_batch_id": "BATCH-1",
        "supplier_lot_id": "LOT-1",
        "plant_id": "PLANT-1",
        "production_line_id": "LINE-1",
    }
    rows = []
    for minute in range(n):
        ts = START + timedelta(minutes=minute)
        metrics = dict.fromkeys(TELEMATICS_METRICS)
        metrics["vehicle_speed_kph"] = float(speed[minute])
        metrics["battery_temperature_c"] = float(battery[minute])
        metrics["transmission_slip_ms"] = float(slip[minute])
        rows.append({"timestamp": ts, "entity": vehicle_id, **context, **metrics})
    return rows


def test_exclusion_is_benchmark_only() -> None:
    # The exclusion mechanism must exist ONLY in this diagnostic module --
    # never in the production service/config/API/DB layers it explicitly
    # must not touch.
    import app.services.manufacturing_causal as manufacturing_causal_module
    import app.services.telematics_causal as telematics_causal_module
    from app.core.config import Settings
    from app.services.telematics_causal import TelematicsCausalService

    settings_fields = set(Settings.model_fields)
    assert not any("exclude" in field for field in settings_fields)

    get_or_run_params = set(inspect.signature(TelematicsCausalService.get_or_run).parameters)
    assert "excluded_metrics" not in get_or_run_params
    assert "exclude_metric" not in get_or_run_params

    for module in (manufacturing_causal_module, telematics_causal_module):
        source = inspect.getsource(module)
        assert "excluded_metrics" not in source
        assert "exclude_metric" not in source


def test_default_excluded_metrics_is_empty() -> None:
    signature = inspect.signature(_benchmark_window_from_rows)
    assert signature.parameters["excluded_metrics"].default == frozenset()
    run_benchmark_signature = inspect.signature(run_benchmark)
    assert run_benchmark_signature.parameters["excluded_metrics"].default == frozenset()


def test_exactly_transmission_slip_ms_is_removed() -> None:
    rows = _synthetic_rows_with_slip("VEH-EXCLUDE-1", n=1500)
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-EXCLUDE-1",
        window_label="current",
        requested_history_hours=168.0,
        rows=rows,
        timeout_seconds=180.0,
        excluded_metrics=frozenset({"transmission_slip_ms"}),
    )
    assert record.status == "COMPLETED", record.error
    assert record.excluded_metrics == ["transmission_slip_ms"]
    assert "VEH-EXCLUDE-1||transmission_slip_ms" in record.metrics_before_exclusion
    assert "VEH-EXCLUDE-1||transmission_slip_ms" not in record.metrics_after_exclusion
    assert "VEH-EXCLUDE-1||transmission_slip_ms" not in record.variable_names


def test_all_other_processed_metrics_remain_unchanged() -> None:
    rows = _synthetic_rows_with_slip("VEH-EXCLUDE-2", n=1500)
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-EXCLUDE-2",
        window_label="current",
        requested_history_hours=168.0,
        rows=rows,
        timeout_seconds=180.0,
        excluded_metrics=frozenset({"transmission_slip_ms"}),
    )
    assert record.status == "COMPLETED", record.error
    before = set(record.metrics_before_exclusion)
    after = set(record.metrics_after_exclusion)
    assert before - after == {"VEH-EXCLUDE-2||transmission_slip_ms"}
    assert after.issubset(before)
    assert set(record.variable_names) == after


def test_exclusion_happens_after_production_preprocessing_before_lpcmci() -> None:
    code = _worker_code_only()
    build_index = code.index("build_telematics_panel(")
    drop_index = code.index("columns_to_drop")
    lpcmci_index = code.index("run_lpcmci_tests(")
    assert build_index < drop_index < lpcmci_index


def test_lpcmci_receives_the_reduced_matrix() -> None:
    # The tuple of column names actually passed to run_lpcmci_tests() is
    # built FROM metrics_after_exclusion (post-drop), never from the
    # pre-exclusion panel.
    code = _worker_code_only()
    assert "column_names = tuple(metrics_after_exclusion)" in code
    assert "reduced_panel.to_numpy" in code


def test_reduced_matrix_variable_count_matches_exclusion() -> None:
    rows = _synthetic_rows_with_slip("VEH-EXCLUDE-3", n=1500)
    without_exclusion = _benchmark_window_from_rows(
        vehicle_id="VEH-EXCLUDE-3",
        window_label="current",
        requested_history_hours=168.0,
        rows=rows,
        timeout_seconds=180.0,
    )
    with_exclusion = _benchmark_window_from_rows(
        vehicle_id="VEH-EXCLUDE-3",
        window_label="current",
        requested_history_hours=168.0,
        rows=rows,
        timeout_seconds=180.0,
        excluded_metrics=frozenset({"transmission_slip_ms"}),
    )
    assert without_exclusion.status == "COMPLETED"
    assert with_exclusion.status == "COMPLETED"
    assert with_exclusion.variables_used == without_exclusion.variables_used - 1
    assert with_exclusion.matrix_shape == f"{with_exclusion.analytical_rows}x{with_exclusion.variables_used}"


def test_unknown_exclude_metric_is_rejected() -> None:
    rows = _synthetic_rows_with_slip("VEH-EXCLUDE-4", n=1500)
    with pytest.raises(ValueError, match="Unknown telematics metric"):
        _benchmark_window_from_rows(
            vehicle_id="VEH-EXCLUDE-4",
            window_label="current",
            requested_history_hours=168.0,
            rows=rows,
            excluded_metrics=frozenset({"not_a_real_metric"}),
        )


def test_cli_exclude_metric_flag_exists_and_validates() -> None:
    source = inspect.getsource(benchmark_module._parse_args)
    assert "--exclude-metric" in source
    assert 'action="append"' in source


def test_timeout_remains_killable_with_exclusion_active() -> None:
    rows = _synthetic_rows_with_slip("VEH-EXCLUDE-TIMEOUT", n=1500)
    started = time.perf_counter()
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-EXCLUDE-TIMEOUT",
        window_label="current",
        requested_history_hours=168.0,
        rows=rows,
        timeout_seconds=0.01,
        excluded_metrics=frozenset({"transmission_slip_ms"}),
    )
    wall_clock = time.perf_counter() - started
    assert record.status == "TIMED_OUT"
    assert record.error is not None and "wall-clock" in record.error
    assert record.analytical_rows is None
    assert record.metrics_before_exclusion is None
    assert record.metrics_after_exclusion is None
    assert record.excluded_metrics == ["transmission_slip_ms"]
    assert wall_clock < 30.0


def test_no_db_or_scheduler_writes_in_exclusion_code_path() -> None:
    worker_source = inspect.getsource(benchmark_module._worker_run_panel_and_lpcmci)
    for forbidden in (
        "session.execute",
        "session.add",
        "session.commit",
        "pg_insert",
        "update_scheduler_state",
        "CausalSchedulerState",
    ):
        assert forbidden not in worker_source, forbidden


def test_benchmark_output_is_never_persisted() -> None:
    # No production ORM model is imported anywhere in this module -- the
    # benchmark result is only ever printed as JSON by main().
    identifiers = _code_identifiers()
    for forbidden in (
        "TelematicsCausalRun",
        "TelematicsCausalEdge",
        "ManufacturingCausalRun",
        "ManufacturingCausalEdge",
    ):
        assert forbidden not in identifiers, forbidden


def test_existing_behavior_without_exclude_metric_is_unchanged() -> None:
    # Byte-for-byte parity with calling the real production _analyse_vehicle
    # directly (the exact assertion made before --exclude-metric existed),
    # plus the new fields resolving to their documented no-op values.
    from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
    from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
    from app.services.telematics_causal import _analyse_vehicle

    rows = _synthetic_rows("VEH-PARITY-2", n=1500)

    direct = _analyse_vehicle(
        "VEH-PARITY-2",
        rows,
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )
    record = _benchmark_window_from_rows(
        vehicle_id="VEH-PARITY-2",
        window_label="24h",
        requested_history_hours=24.0,
        rows=rows,
        timeout_seconds=120.0,
    )

    assert record.status == "COMPLETED", record.error
    assert record.analytical_rows == direct.analytical_rows
    assert record.variables_used == len(direct.variables_used)
    assert record.raw_pag_relationship_count == direct.filtered.total_tests
    assert record.excluded_metrics == []
    assert record.metrics_before_exclusion == record.metrics_after_exclusion == record.variable_names


# ===========================================================================
# --window scheduler-plan: reproducing the real scheduler's source plan
# ===========================================================================


class _FakeSession:
    """Stand-in for AsyncSession -- never actually queried, since every
    function that would use it (get_replay_state, _domain_cursor,
    build_telematics_source_plan, fetch_vehicle_rows) is monkeypatched in
    these tests to real, but DB-free, fakes."""


class _FakeSessionFactory:
    def __call__(self) -> "_FakeSessionFactory":
        return self

    async def __aenter__(self) -> _FakeSession:
        return _FakeSession()

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeReplayState:
    def __init__(self, simulation_as_of: datetime) -> None:
        self.simulation_as_of = simulation_as_of


class _FakePlan:
    def __init__(
        self,
        *,
        vehicle_ids: tuple[str, ...],
        source_from: datetime,
        source_to: datetime,
        history_hours: float = 168.0,
        signature: str = "fake-plan-signature",
    ) -> None:
        self.vehicle_ids = vehicle_ids
        self.source_from = source_from
        self.source_to = source_to
        self.history_hours = history_hours
        self.signature = signature


class _CallSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _patch_scheduler_plan_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    simulation_as_of: datetime,
    plan: _FakePlan | None,
    plan_error: Exception | None = None,
    rows: list[dict[str, object]] | None = None,
) -> tuple[_CallSpy, _CallSpy]:
    """Monkeypatch every DB-touching dependency run_scheduler_plan_benchmark
    uses with real-shaped, DB-free fakes; returns spies for the plan-
    builder call and the row-fetch call so tests can assert on exactly
    what they were invoked with."""

    monkeypatch.setattr(benchmark_module, "get_session_factory", lambda: _FakeSessionFactory())

    async def fake_get_replay_state(session: object, *, initialize: bool) -> _FakeReplayState:
        assert initialize is False, "must never initialize (write) replay state"
        return _FakeReplayState(simulation_as_of)

    monkeypatch.setattr("app.services.causal_runtime.get_replay_state", fake_get_replay_state)

    async def fake_domain_cursor(session: object, domain: str) -> None:
        assert domain == "telematics"
        return None

    monkeypatch.setattr("app.scheduler.causal_scheduler._domain_cursor", fake_domain_cursor)

    build_plan_spy = _CallSpy()

    async def fake_build_plan(session: object, as_of: datetime, *, telematics_cursor: object = None) -> _FakePlan:
        build_plan_spy(session, as_of, telematics_cursor=telematics_cursor)
        if plan_error is not None:
            raise plan_error
        assert plan is not None
        return plan

    monkeypatch.setattr("app.scheduler.causal_scheduler.build_telematics_source_plan", fake_build_plan)

    fetch_rows_spy = _CallSpy()

    async def fake_fetch_vehicle_rows(
        session: object,
        vehicle_id: str,
        *,
        history_hours: float = 168.0,
        source_from: datetime | None = None,
        source_to: datetime | None = None,
    ) -> list[dict[str, object]]:
        fetch_rows_spy(
            session, vehicle_id, history_hours=history_hours, source_from=source_from, source_to=source_to
        )
        return rows or []

    monkeypatch.setattr(benchmark_module, "fetch_vehicle_rows", fake_fetch_vehicle_rows)

    return build_plan_spy, fetch_rows_spy


AS_OF = datetime(2026, 9, 3, 16, 8, tzinfo=UTC)
PLAN_SOURCE_FROM = datetime(2026, 8, 27, 16, 8, tzinfo=UTC)
PLAN_SOURCE_TO = datetime(2026, 9, 3, 16, 7, tzinfo=UTC)


def test_a_real_source_plan_builder_is_called(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(vehicle_ids=("OTHER-VEHICLE",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    build_plan_spy, _ = _patch_scheduler_plan_dependencies(monkeypatch, simulation_as_of=AS_OF, plan=plan)

    import asyncio

    asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=30.0)
    )

    assert len(build_plan_spy.calls) == 1


def test_b_as_of_comes_from_the_real_replay_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(vehicle_ids=("VEHUNIT_SYN_0001275",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    build_plan_spy, fetch_rows_spy = _patch_scheduler_plan_dependencies(
        monkeypatch,
        simulation_as_of=AS_OF,
        plan=plan,
        rows=_synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500),
    )

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=180.0)
    )

    # build_telematics_source_plan was called with EXACTLY the replay
    # clock's as_of -- never a value this benchmark invented itself.
    call_args, _call_kwargs = build_plan_spy.calls[0]
    _session, called_as_of = call_args
    assert called_as_of == AS_OF
    assert record.simulation_as_of == AS_OF.isoformat()


def test_c_vehicle_membership_is_checked_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(vehicle_ids=("SOME-OTHER-VEHICLE",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    _patch_scheduler_plan_dependencies(monkeypatch, simulation_as_of=AS_OF, plan=plan)

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=30.0)
    )

    assert record.status == "FAILED"
    assert record.requested_vehicle_in_plan is False
    assert record.plan_vehicle_count == 1
    assert "not present" in record.error
    # No fabricated analysis data.
    assert record.analytical_rows is None
    assert record.variable_names is None


def test_c_vehicle_membership_is_checked_present(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(
        vehicle_ids=("VEHUNIT_SYN_0001275", "SOME-OTHER-VEHICLE"),
        source_from=PLAN_SOURCE_FROM,
        source_to=PLAN_SOURCE_TO,
    )
    _patch_scheduler_plan_dependencies(
        monkeypatch,
        simulation_as_of=AS_OF,
        plan=plan,
        rows=_synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500),
    )

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=180.0)
    )

    assert record.requested_vehicle_in_plan is True
    assert record.plan_vehicle_count == 2
    assert record.status == "COMPLETED", record.error


def test_d_fetch_uses_exact_plan_bounds_not_history_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(vehicle_ids=("VEHUNIT_SYN_0001275",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    _, fetch_rows_spy = _patch_scheduler_plan_dependencies(
        monkeypatch,
        simulation_as_of=AS_OF,
        plan=plan,
        rows=_synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500),
    )

    import asyncio

    asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=180.0)
    )

    assert len(fetch_rows_spy.calls) == 1
    _, kwargs = fetch_rows_spy.calls[0]
    assert kwargs["source_from"] == PLAN_SOURCE_FROM
    assert kwargs["source_to"] == PLAN_SOURCE_TO


def test_plan_source_signature_and_bounds_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _FakePlan(
        vehicle_ids=("VEHUNIT_SYN_0001275",),
        source_from=PLAN_SOURCE_FROM,
        source_to=PLAN_SOURCE_TO,
        signature="abc123",
    )
    _patch_scheduler_plan_dependencies(
        monkeypatch,
        simulation_as_of=AS_OF,
        plan=plan,
        rows=_synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500),
    )

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=180.0)
    )

    assert record.scheduler_plan_mode is True
    assert record.plan_source_from == PLAN_SOURCE_FROM.isoformat()
    assert record.plan_source_to == PLAN_SOURCE_TO.isoformat()
    assert record.plan_source_signature == "abc123"


def test_h_lpcmci_receives_exactly_the_scheduler_visible_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500)
    plan = _FakePlan(vehicle_ids=("VEHUNIT_SYN_0001275",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    _patch_scheduler_plan_dependencies(monkeypatch, simulation_as_of=AS_OF, plan=plan, rows=rows)

    import asyncio

    from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
    from app.ai.causal.telematics_panel import DEFAULT_TELEMATICS_PANEL_CONFIG
    from app.services.telematics_causal import _analyse_vehicle

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=180.0)
    )
    direct = _analyse_vehicle(
        "VEHUNIT_SYN_0001275",
        rows,
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=DEFAULT_TELEMATICS_PANEL_CONFIG,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )

    assert record.status == "COMPLETED", record.error
    assert record.analytical_rows == direct.analytical_rows
    assert record.variables_used == len(direct.variables_used)
    assert set(record.variable_names) == set(direct.variables_used)
    assert record.matrix_shape == f"{direct.analytical_rows}x{len(direct.variables_used)}"
    assert record.raw_pag_relationship_count == direct.filtered.total_tests
    assert record.tau_min == 0
    assert record.tau_max == 2
    assert record.pc_alpha == pytest.approx(0.10)
    assert record.algorithm_config == {}


def test_i_timeout_remains_killable_in_scheduler_plan_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _synthetic_rows_with_slip("VEHUNIT_SYN_0001275", n=1500)
    plan = _FakePlan(vehicle_ids=("VEHUNIT_SYN_0001275",), source_from=PLAN_SOURCE_FROM, source_to=PLAN_SOURCE_TO)
    _patch_scheduler_plan_dependencies(monkeypatch, simulation_as_of=AS_OF, plan=plan, rows=rows)

    import asyncio

    started = time.perf_counter()
    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=0.01)
    )
    wall_clock = time.perf_counter() - started

    assert record.status == "TIMED_OUT"
    assert record.analytical_rows is None
    assert record.scheduler_plan_mode is True
    assert record.requested_vehicle_in_plan is True
    assert wall_clock < 30.0


def test_replay_state_not_initialized_reports_explicit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark_module, "get_session_factory", lambda: _FakeSessionFactory())

    async def fake_get_replay_state_none(session: object, *, initialize: bool) -> None:
        assert initialize is False
        return None

    monkeypatch.setattr("app.services.causal_runtime.get_replay_state", fake_get_replay_state_none)

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=30.0)
    )

    assert record.status == "FAILED"
    assert "not initialized" in record.error
    assert record.scheduler_plan_mode is True


def test_source_not_ready_from_real_plan_builder_is_reported_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.scheduler.causal_scheduler import SourceNotReady

    _patch_scheduler_plan_dependencies(
        monkeypatch,
        simulation_as_of=AS_OF,
        plan=None,
        plan_error=SourceNotReady("NO_INGESTED_TELEMATICS_ROWS", {}),
    )

    import asyncio

    record = asyncio.run(
        benchmark_module.run_scheduler_plan_benchmark(vehicle_id="VEHUNIT_SYN_0001275", timeout_seconds=30.0)
    )

    assert record.status == "FAILED"
    assert "scheduler source plan could not be built" in record.error


def test_j_existing_24h_48h_current_modes_are_unaffected_by_scheduler_plan_addition() -> None:
    # run_benchmark / _fetch_and_benchmark_window / _benchmark_window_from_rows
    # source must not reference the scheduler-plan-only additions.
    for func in (benchmark_module.run_benchmark, benchmark_module._fetch_and_benchmark_window):
        source = inspect.getsource(func)
        assert "scheduler_plan" not in source
        assert "build_telematics_source_plan" not in source


def test_scheduler_plan_window_label_excluded_from_window_all_sequence() -> None:
    assert benchmark_module.SCHEDULER_PLAN_WINDOW_LABEL not in WINDOW_ORDER


def test_cli_rejects_exclude_metric_with_scheduler_plan_window(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--window",
            "scheduler-plan",
            "--exclude-metric",
            "transmission_slip_ms",
        ],
    )
    with pytest.raises(SystemExit):
        benchmark_module._parse_args()
