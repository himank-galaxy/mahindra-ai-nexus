"""Regression tests for LPCMCI runtime-profiling logs and the tau_min fix.

Context
-------
A single telematics vehicle stayed inside Tigramite's LPCMCI.run_lpcmci()
for 20+ minutes at ~300% CPU with no visibility into whether the time was
spent in preprocessing or inside Tigramite itself, and no per-asset
progress since the coarse causal_asset_started/completed events (added for
the earlier scheduler-cutover profiling pass) only bracket the WHOLE
per-machine/per-vehicle analysis, not the discovery call specifically.

This adds two finer-grained structured events inside _analyse_machine/
_analyse_vehicle, bracketing run_lpcmci_tests() itself:

    causal_lpcmci_input_ready        (after preprocessing, before Tigramite)
    causal_lpcmci_discovery_completed (after Tigramite returns, before filtering)

It also fixes a real correctness bug found along the way: the persisted
``tau_min`` configuration parameter was hardcoded to 1 regardless of
algorithm, which understates what LPCMCI with test_contemporaneous=True
actually tests (lag 0 in addition to lagged links) and meant two runs
testing genuinely different lag ranges could be mistaken for identical
configurations by the signature.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.ai.causal.manufacturing_filter import DEFAULT_MANUFACTURING_FILTER_CONFIG
from app.ai.causal.manufacturing_panel import ManufacturingPanelConfig
from app.ai.causal.telematics_filter import DEFAULT_TELEMATICS_FILTER_CONFIG
from app.ai.causal.telematics_loader import TELEMATICS_CONTEXT_FIELDS, TELEMATICS_METRICS
from app.ai.causal.telematics_panel import TelematicsPanelConfig
from app.services import manufacturing_causal, telematics_causal
from app.services.manufacturing_causal import (
    _analyse_machine,
    _analysis_parameters,
    _source_signature,
    effective_tau_min as manufacturing_effective_tau_min,
)
from app.services.telematics_causal import (
    _analyse_vehicle,
    _configuration_parameters,
    effective_tau_min as telematics_effective_tau_min,
)
from app.services.telematics_causal import _source_signature as telematics_source_signature

START = datetime(2026, 7, 25, tzinfo=UTC)


def _manufacturing_records(n: int = 200) -> list[dict[str, object]]:
    records = []
    for minute in range(n):
        ts = START + timedelta(minutes=minute)
        base = {
            "timestamp": ts,
            "entity": "MACHINE_1",
            "machine_id": "MACHINE_1",
            "plant_id": "PLANT_1",
            "production_line_id": "LINE_1",
            "line_type": "ASSEMBLY",
        }
        records.append({**base, "metric": "machine_load", "value": float(minute % 17)})
        records.append({**base, "metric": "power_kw", "value": float((minute * 3) % 23)})
    return records


def _manufacturing_panel_config() -> ManufacturingPanelConfig:
    return ManufacturingPanelConfig(
        analysis_frequency="15min",
        min_panel_observations=1,
        min_data_coverage=0.0,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        stationarity_differencing_enabled=False,
        normalize_data=True,
    )


def _telematics_rows(n: int = 400) -> list[dict[str, object]]:
    # A genuine contemporaneous relationship (not independent noise) so
    # LPCMCI reliably discovers at least one edge -- these tests are about
    # proving the logging is correct, not about discovery accuracy per se,
    # but _analyse_vehicle() raises if run_lpcmci_tests() finds nothing.
    rng = np.random.default_rng(3)
    speed = rng.normal(0, 1, n)
    battery_temp = 0.7 * speed + rng.normal(0, 0.3, n)

    context = {
        "vehicle_id": "VEH-1",
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
        metrics["battery_temperature_c"] = float(battery_temp[minute])
        rows.append({"timestamp": ts, "entity": "VEH-1", **context, **metrics})
    return rows


def _telematics_panel_config() -> TelematicsPanelConfig:
    return TelematicsPanelConfig(
        analysis_frequency="5min",
        min_panel_observations=1,
        min_data_coverage=0.0,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        stationarity_differencing_enabled=False,
        normalize_data=True,
    )


class _LogSpy:
    """Captures (event, kwargs) for every logger.info(...) call, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, event: str, **kwargs: object) -> None:
        self.calls.append((event, kwargs))

    def find(self, event: str) -> dict[str, object]:
        for logged_event, kwargs in self.calls:
            if logged_event == event:
                return kwargs
        raise AssertionError(f"{event!r} was not logged; got {[e for e, _ in self.calls]}")

    def index_of(self, event: str) -> int:
        for index, (logged_event, _) in enumerate(self.calls):
            if logged_event == event:
                return index
        raise AssertionError(f"{event!r} was not logged; got {[e for e, _ in self.calls]}")


# ---------------------------------------------------------------------------
# Ordering: causal_lpcmci_input_ready before run_lpcmci_tests, and
# causal_lpcmci_discovery_completed after it returns.
# ---------------------------------------------------------------------------


def test_manufacturing_input_ready_logged_before_run_lpcmci_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _LogSpy()
    monkeypatch.setattr(manufacturing_causal.logger, "info", spy)

    call_order: list[str] = []
    original_run_lpcmci_tests = manufacturing_causal.run_lpcmci_tests

    def spy_run_lpcmci_tests(*args: object, **kwargs: object) -> object:
        call_order.append("run_lpcmci_tests")
        return original_run_lpcmci_tests(*args, **kwargs)

    monkeypatch.setattr(manufacturing_causal, "run_lpcmci_tests", spy_run_lpcmci_tests)

    _analyse_machine(
        "MACHINE_1",
        _manufacturing_records(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    input_ready_index = spy.index_of("causal_lpcmci_input_ready")
    completed_index = spy.index_of("causal_lpcmci_discovery_completed")
    assert call_order == ["run_lpcmci_tests"], "run_lpcmci_tests must be called exactly once"
    assert input_ready_index < completed_index
    # Strict interleaving with the actual run_lpcmci_tests() call (not just
    # relative order of the two log events) is verified by the shared-
    # timeline test below.


def test_manufacturing_input_ready_and_discovery_bracket_the_real_call(monkeypatch: pytest.MonkeyPatch) -> None:
    # A single shared timeline proves strict interleaving:
    # input_ready -> run_lpcmci_tests -> discovery_completed.
    timeline: list[str] = []

    def spy_logger_info(event: str, **kwargs: object) -> None:
        timeline.append(f"log:{event}")

    original_run_lpcmci_tests = manufacturing_causal.run_lpcmci_tests

    def spy_run_lpcmci_tests(*args: object, **kwargs: object) -> object:
        timeline.append("call:run_lpcmci_tests")
        return original_run_lpcmci_tests(*args, **kwargs)

    monkeypatch.setattr(manufacturing_causal.logger, "info", spy_logger_info)
    monkeypatch.setattr(manufacturing_causal, "run_lpcmci_tests", spy_run_lpcmci_tests)

    _analyse_machine(
        "MACHINE_1",
        _manufacturing_records(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    assert (
        timeline.index("log:causal_lpcmci_input_ready")
        < timeline.index("call:run_lpcmci_tests")
        < timeline.index("log:causal_lpcmci_discovery_completed")
    )


def test_telematics_input_ready_and_discovery_bracket_the_real_call(monkeypatch: pytest.MonkeyPatch) -> None:
    timeline: list[str] = []

    def spy_logger_info(event: str, **kwargs: object) -> None:
        timeline.append(f"log:{event}")

    original_run_lpcmci_tests = telematics_causal.run_lpcmci_tests

    def spy_run_lpcmci_tests(*args: object, **kwargs: object) -> object:
        timeline.append("call:run_lpcmci_tests")
        return original_run_lpcmci_tests(*args, **kwargs)

    monkeypatch.setattr(telematics_causal.logger, "info", spy_logger_info)
    monkeypatch.setattr(telematics_causal, "run_lpcmci_tests", spy_run_lpcmci_tests)

    _analyse_vehicle(
        "VEH-1",
        _telematics_rows(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_telematics_panel_config(),
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )

    assert (
        timeline.index("log:causal_lpcmci_input_ready")
        < timeline.index("call:run_lpcmci_tests")
        < timeline.index("log:causal_lpcmci_discovery_completed")
    )


# ---------------------------------------------------------------------------
# Correct matrix dimensions logged, and no raw values logged.
# ---------------------------------------------------------------------------


def test_manufacturing_logs_correct_matrix_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _LogSpy()
    monkeypatch.setattr(manufacturing_causal.logger, "info", spy)

    result = _analyse_machine(
        "MACHINE_1",
        _manufacturing_records(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    ready = spy.find("causal_lpcmci_input_ready")
    assert ready["domain"] == "manufacturing"
    assert ready["asset_id"] == "MACHINE_1"
    assert ready["analytical_rows"] == result.analytical_rows
    assert ready["variables_used"] == len(result.variables_used)
    assert set(ready["variable_names"]) == set(result.variables_used)
    assert ready["tau_min"] == 0
    assert ready["tau_max"] == 2
    assert ready["pc_alpha"] == pytest.approx(0.10)
    assert ready["test_contemporaneous"] is True
    assert ready["effective_algorithm_config"] == {}
    assert ready["matrix_shape"] == f"{result.analytical_rows}x{len(result.variables_used)}"

    completed = spy.find("causal_lpcmci_discovery_completed")
    assert completed["domain"] == "manufacturing"
    assert completed["asset_id"] == "MACHINE_1"
    assert completed["analytical_rows"] == result.analytical_rows
    assert completed["variables_used"] == len(result.variables_used)
    assert isinstance(completed["discovery_runtime_seconds"], float)
    assert completed["discovery_runtime_seconds"] >= 0.0
    assert completed["raw_pag_relationship_count"] == len(result.filtered.accepted_edges) or (
        completed["raw_pag_relationship_count"] >= len(result.filtered.accepted_edges)
    )


def test_telematics_logs_correct_matrix_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _LogSpy()
    monkeypatch.setattr(telematics_causal.logger, "info", spy)

    result = _analyse_vehicle(
        "VEH-1",
        _telematics_rows(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_telematics_panel_config(),
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )

    ready = spy.find("causal_lpcmci_input_ready")
    assert ready["domain"] == "telematics"
    assert ready["asset_id"] == "VEH-1"
    assert ready["vehicle_id"] == "VEH-1"
    assert ready["analytical_rows"] == result.analytical_rows
    assert ready["variables_used"] == len(result.variables_used)
    assert set(ready["variable_names"]) == set(result.variables_used)
    assert ready["tau_min"] == 0
    assert ready["matrix_shape"] == f"{result.analytical_rows}x{len(result.variables_used)}"

    completed = spy.find("causal_lpcmci_discovery_completed")
    assert completed["analytical_rows"] == result.analytical_rows
    assert completed["variables_used"] == len(result.variables_used)


def test_no_raw_panel_values_are_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    # variable_names (metric identifiers) are explicitly requested and
    # approved -- "raw values" means measurement/panel DATA, not schema
    # names. Assert every logged field is one of the specifically-approved
    # keys, with no field capable of carrying raw numeric panel contents
    # (e.g. no "panel", "values", "matrix", "data", "records", "rows" key).
    spy = _LogSpy()
    monkeypatch.setattr(manufacturing_causal.logger, "info", spy)

    _analyse_machine(
        "MACHINE_1",
        _manufacturing_records(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    # NOTE: "panel_runtime_seconds" is an approved, explicitly-requested
    # field -- fragment checks below must not flag "panel" alone, only
    # fragments that would indicate raw data content leaking through.
    forbidden_key_fragments = ("matrix_data", "raw_records", "rows_data", "raw_rows", "raw_values")
    allowed_ready_keys = {
        "domain",
        "asset_id",
        "analytical_rows",
        "variables_used",
        "variable_names",
        "tau_min",
        "tau_max",
        "pc_alpha",
        "test_contemporaneous",
        "effective_algorithm_config",
        "panel_runtime_seconds",
        "matrix_shape",
    }
    allowed_completed_keys = {
        "domain",
        "asset_id",
        "analytical_rows",
        "variables_used",
        "discovery_runtime_seconds",
        "raw_pag_relationship_count",
    }

    ready = spy.find("causal_lpcmci_input_ready")
    completed = spy.find("causal_lpcmci_discovery_completed")

    assert set(ready.keys()) == allowed_ready_keys
    assert set(completed.keys()) == allowed_completed_keys
    for key in (*ready.keys(), *completed.keys()):
        assert not any(fragment in key for fragment in forbidden_key_fragments), key
    # matrix_shape is a small descriptive string ("<rows>x<vars>"), never a
    # literal array/matrix.
    assert isinstance(ready["matrix_shape"], str)
    assert "\n" not in ready["matrix_shape"]


# ---------------------------------------------------------------------------
# tau_min correctness: persisted value per algorithm/test_contemporaneous.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("algorithm", "test_contemporaneous", "expected_tau_min"),
    [
        ("lpcmci", True, 0),
        ("lpcmci", False, 1),
        ("pcmci", True, 1),
        ("pcmci", False, 1),
    ],
)
def test_manufacturing_persists_correct_tau_min(
    algorithm: str, test_contemporaneous: bool, expected_tau_min: int
) -> None:
    assert manufacturing_effective_tau_min(algorithm, test_contemporaneous) == expected_tau_min

    parameters = _analysis_parameters(
        machine_ids=("MACHINE_1",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=2,
        pc_alpha=0.10,
        force_include_metrics=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
        algorithm=algorithm,
        test_contemporaneous=test_contemporaneous,
    )
    assert parameters["tau_min"] == expected_tau_min


@pytest.mark.parametrize(
    ("algorithm", "test_contemporaneous", "expected_tau_min"),
    [
        ("lpcmci", True, 0),
        ("lpcmci", False, 1),
        ("pcmci", True, 1),
        ("pcmci", False, 1),
    ],
)
def test_telematics_persists_correct_tau_min(
    algorithm: str, test_contemporaneous: bool, expected_tau_min: int
) -> None:
    assert telematics_effective_tau_min(algorithm, test_contemporaneous) == expected_tau_min

    parameters = _configuration_parameters(
        ("VEH-1",),
        history_hours=168.0,
        source_from=None,
        source_to=None,
        raw_frequency_minutes=1.0,
        panel_config=_telematics_panel_config(),
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
        tau_max=2,
        pc_alpha=0.10,
        analysis_frequency_minutes=5,
        algorithm=algorithm,
        test_contemporaneous=test_contemporaneous,
    )
    assert parameters["tau_min"] == expected_tau_min


# ---------------------------------------------------------------------------
# tau_min participates in the run signature (isolated from
# test_contemporaneous's own, separate participation).
# ---------------------------------------------------------------------------


def test_manufacturing_signature_is_sensitive_to_tau_min_alone() -> None:
    records = [
        {"timestamp": "2026-01-01T00:00:00+00:00", "entity": "MACHINE_1", "metric": "machine_load", "value": 1.0}
    ]
    base_parameters = _analysis_parameters(
        machine_ids=("MACHINE_1",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=2,
        pc_alpha=0.10,
        force_include_metrics=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
        algorithm="lpcmci",
        test_contemporaneous=True,
    )
    assert base_parameters["tau_min"] == 0

    mutated_parameters = {**base_parameters, "tau_min": 1}

    baseline_signature = _source_signature(records, parameters=base_parameters)
    mutated_signature = _source_signature(records, parameters=mutated_parameters)
    assert baseline_signature != mutated_signature


def test_telematics_signature_is_sensitive_to_tau_min_alone() -> None:
    row_digests = {"VEH-1": "digest-1"}
    base_parameters = _configuration_parameters(
        ("VEH-1",),
        history_hours=168.0,
        source_from=None,
        source_to=None,
        raw_frequency_minutes=1.0,
        panel_config=_telematics_panel_config(),
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
        tau_max=2,
        pc_alpha=0.10,
        analysis_frequency_minutes=5,
        algorithm="lpcmci",
        test_contemporaneous=True,
    )
    assert base_parameters["tau_min"] == 0

    mutated_parameters = {**base_parameters, "tau_min": 1}

    baseline_signature = telematics_source_signature(row_digests, base_parameters)
    mutated_signature = telematics_source_signature(row_digests, mutated_parameters)
    assert baseline_signature != mutated_signature


# ---------------------------------------------------------------------------
# Logging does not alter analysis results.
# ---------------------------------------------------------------------------


def test_manufacturing_logging_does_not_alter_analysis_results(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _manufacturing_records()
    panel_config = _manufacturing_panel_config()
    kwargs = dict(
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=panel_config,
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    without_logging = _analyse_machine("MACHINE_1", records, **kwargs)

    spy = _LogSpy()
    monkeypatch.setattr(manufacturing_causal.logger, "info", spy)
    with_logging = _analyse_machine("MACHINE_1", records, **kwargs)

    assert spy.calls, "expected logging to actually fire in this run"
    assert without_logging.analytical_rows == with_logging.analytical_rows
    assert without_logging.variables_used == with_logging.variables_used
    assert [e.score for e in without_logging.filtered.accepted_edges] == [
        e.score for e in with_logging.filtered.accepted_edges
    ]
    assert [e.edge_mark for e in without_logging.filtered.accepted_edges] == [
        e.edge_mark for e in with_logging.filtered.accepted_edges
    ]


def test_telematics_logging_does_not_alter_analysis_results(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = _telematics_rows()
    panel_config = _telematics_panel_config()
    kwargs = dict(
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=panel_config,
        filter_config=DEFAULT_TELEMATICS_FILTER_CONFIG,
    )

    without_logging = _analyse_vehicle("VEH-1", rows, **kwargs)

    spy = _LogSpy()
    monkeypatch.setattr(telematics_causal.logger, "info", spy)
    with_logging = _analyse_vehicle("VEH-1", rows, **kwargs)

    assert spy.calls
    assert without_logging.analytical_rows == with_logging.analytical_rows
    assert without_logging.variables_used == with_logging.variables_used
    assert [e.score for e in without_logging.filtered.accepted_edges] == [
        e.score for e in with_logging.filtered.accepted_edges
    ]


# ---------------------------------------------------------------------------
# algorithm_config is untouched -- still {} / None, never populated with
# max_p_global/max_p_non_ancestral/max_q_global/max_pds_set overrides.
# ---------------------------------------------------------------------------


def test_algorithm_config_defaults_remain_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _LogSpy()
    monkeypatch.setattr(manufacturing_causal.logger, "info", spy)

    _analyse_machine(
        "MACHINE_1",
        _manufacturing_records(),
        algorithm="lpcmci",
        tau_max=2,
        pc_alpha=0.10,
        test_contemporaneous=True,
        algorithm_config=None,
        panel_config=_manufacturing_panel_config(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    ready = spy.find("causal_lpcmci_input_ready")
    assert ready["effective_algorithm_config"] == {}


# ---------------------------------------------------------------------------
# Mobility remains unchanged.
# ---------------------------------------------------------------------------


def test_mobility_pcmci_defaults_still_unmodified() -> None:
    import inspect

    from app.ai.causal import pcmci_engine

    signature = inspect.signature(pcmci_engine.run_pcmci)
    assert signature.parameters["tau_max"].default == 3
    assert signature.parameters["alpha"].default == 0.05
    # Mobility never touches manufacturing/telematics' logger or tau_min
    # resolvers -- it has no dependency on either module.
    mobility_source = inspect.getsource(pcmci_engine)
    assert "manufacturing_causal" not in mobility_source
    assert "telematics_causal" not in mobility_source
