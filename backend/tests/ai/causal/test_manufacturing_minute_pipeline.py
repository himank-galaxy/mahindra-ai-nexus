"""Focused regression tests for minute-aware manufacturing causal analysis."""

from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.ai.causal import manufacturing_loader, manufacturing_panel
from app.ai.causal.manufacturing_filter import (
    DEFAULT_MANUFACTURING_FILTER_CONFIG,
)
from app.ai.causal.manufacturing_loader import (
    _duration_window_start,
    detect_raw_frequency_minutes,
)
from app.ai.causal.manufacturing_panel import (
    MANUFACTURING_METRIC_AGGREGATIONS,
    ManufacturingPanelConfig,
    build_manufacturing_panel,
)
from app.services import manufacturing_causal, warranty_quality_early_warning
from app.services.manufacturing_causal import (
    DEFAULT_TAU_MAX,
    _analysis_frequency_minutes,
    _analysis_parameters,
    _source_signature,
)

START = datetime(2026, 7, 25, tzinfo=UTC)


def _record(
    minute: int,
    metric: str,
    value: float,
    *,
    entity: str = "MACHINE_TEST_001",
) -> dict[str, object]:
    return {
        "timestamp": START + timedelta(minutes=minute),
        "entity": entity,
        "machine_id": entity,
        "metric": metric,
        "value": value,
        "plant_id": "PLANT_TEST_001",
        "production_line_id": "LINE_TEST_001",
        "line_type": "ASSEMBLY",
    }


def _test_panel_config(
    **changes: object,
) -> ManufacturingPanelConfig:
    config = ManufacturingPanelConfig(
        analysis_frequency="15min",
        min_panel_observations=1,
        min_data_coverage=0.0,
        ffill_limit=1,
        min_row_completeness=0.5,
        min_variance=-1.0,
        relative_std_threshold=-1.0,
        max_dominant_value_fraction=1.1,
        skew_transform_enabled=False,
        # Tests in this module assert on raw physical aggregation values
        # (means/sums/last-values), not on the discovery-time preprocessing
        # LPCMCI/PCMCI actually consume — normalization/collinearity removal
        # get their own dedicated coverage. Collinearity removal is disabled
        # here too: some fixtures deliberately feed two metrics linear ramps
        # of each other (to exercise different aggregation rules), which are
        # legitimately perfectly correlated post-resample.
        normalize_data=False,
        collinearity_threshold=1.1,
    )
    return replace(
        config,
        **changes,
    )


def test_minute_raw_data_detection() -> None:
    records = [
        _record(minute, metric, float(minute))
        for minute in range(5)
        for metric in (
            "machine_load",
            "quality_score",
        )
    ]

    assert detect_raw_frequency_minutes(records) == 1.0


def test_duration_based_source_window() -> None:
    latest = datetime(2026, 7, 31, 18, 29, tzinfo=UTC)

    assert _duration_window_start(
        latest,
        72.0,
    ) == datetime(
        2026,
        7,
        28,
        18,
        29,
        tzinfo=UTC,
    )


def test_semantic_analytical_resampling() -> None:
    records = []

    for minute in range(30):
        records.extend(
            (
                _record(
                    minute,
                    "machine_load",
                    float(minute),
                ),
                _record(
                    minute,
                    "hours_since_maintenance",
                    float(minute),
                ),
                _record(
                    minute,
                    "downtime_minutes",
                    0.1,
                ),
            )
        )

    result = build_manufacturing_panel(
        records,
        _test_panel_config(),
    )

    assert MANUFACTURING_METRIC_AGGREGATIONS[
        "machine_load"
    ] == "mean"
    assert MANUFACTURING_METRIC_AGGREGATIONS[
        "hours_since_maintenance"
    ] == "last"
    assert MANUFACTURING_METRIC_AGGREGATIONS[
        "downtime_minutes"
    ] == "sum"

    assert result.panel.iloc[0][
        "MACHINE_TEST_001||machine_load"
    ] == pytest.approx(7.0)
    assert result.panel.iloc[0][
        "MACHINE_TEST_001||hours_since_maintenance"
    ] == pytest.approx(14.0)
    assert result.panel.iloc[0][
        "MACHINE_TEST_001||downtime_minutes"
    ] == pytest.approx(1.5)


def test_lag_steps_convert_to_real_minutes() -> None:
    parameters = _analysis_parameters(
        machine_ids=("MACHINE_TEST_001",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=DEFAULT_TAU_MAX,
        pc_alpha=0.05,
        force_include_metrics=None,
        panel_config=ManufacturingPanelConfig(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    assert _analysis_frequency_minutes("15min") == 15
    assert DEFAULT_TAU_MAX == 12
    # Defaults here are algorithm="lpcmci", test_contemporaneous=True (see
    # _analysis_parameters' own defaults) -- the correct tau_min for that
    # combination is 0 (contemporaneous links are tested), not the
    # previously-hardcoded 1. See effective_tau_min for the full contract.
    assert parameters["tau_min"] == 0
    assert parameters["maximum_lag_minutes"] == 180


def test_identifier_columns_never_enter_pcmci_panel() -> None:
    records = [
        _record(
            minute,
            "machine_load",
            float(minute),
        )
        for minute in range(30)
    ]
    records.extend(
        _record(
            minute,
            "machine_id",
            float(minute),
        )
        for minute in range(30)
    )

    result = build_manufacturing_panel(
        records,
        _test_panel_config(),
    )

    assert all(
        not column.endswith(
            "||machine_id"
        )
        for column in result.panel.columns
    )
    assert result.dropped_metrics[
        "MACHINE_TEST_001||machine_id"
    ] == "not_a_manufacturing_causal_metric"


def test_source_signature_is_deterministic_and_configuration_sensitive() -> None:
    records = [
        _record(
            minute,
            "machine_load",
            float(minute),
        )
        for minute in range(4)
    ]
    config = ManufacturingPanelConfig()

    parameters = _analysis_parameters(
        machine_ids=("MACHINE_TEST_001",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=12,
        pc_alpha=0.05,
        force_include_metrics=None,
        panel_config=config,
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    signature = _source_signature(
        records,
        parameters=parameters,
    )

    assert signature == _source_signature(
        list(reversed(records)),
        parameters=parameters,
    )

    changed_parameters = _analysis_parameters(
        machine_ids=("MACHINE_TEST_001",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=6,
        pc_alpha=0.05,
        force_include_metrics=None,
        panel_config=replace(
            config,
            analysis_frequency="30min",
        ),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    assert signature != _source_signature(
        records,
        parameters=changed_parameters,
    )

    changed_records = [
        *records[:-1],
        {
            **records[-1],
            "value": 999.0,
        },
    ]

    assert signature != _source_signature(
        changed_records,
        parameters=parameters,
    )


def test_panel_is_chronological_and_reports_missing_intervals() -> None:
    records = [
        _record(
            minute,
            "machine_load",
            float(minute),
        )
        for minute in (
            45,
            0,
            30,
        )
    ]

    result = build_manufacturing_panel(
        records,
        _test_panel_config(),
    )

    assert result.panel.index.is_monotonic_increasing
    assert not result.panel.index.has_duplicates
    assert result.missing_intervals[
        "MACHINE_TEST_001||machine_load"
    ] == 1


def test_exact_duplicate_timestamp_records_are_removed() -> None:
    records = [
        _record(
            minute,
            "machine_load",
            float(minute),
        )
        for minute in range(30)
    ]
    duplicate = dict(
        records[4]
    )

    baseline = build_manufacturing_panel(
        records,
        _test_panel_config(),
    )
    duplicated = build_manufacturing_panel(
        [
            *records,
            duplicate,
        ],
        _test_panel_config(),
    )

    assert duplicated.duplicate_records_removed == 1
    assert duplicated.panel.equals(
        baseline.panel
    )


def test_runtime_pipeline_has_no_hidden_truth_file_access() -> None:
    forbidden_calls = {
        "open",
        "read_csv",
        "read_parquet",
    }

    for module in (
        manufacturing_loader,
        manufacturing_panel,
        manufacturing_causal,
        warranty_quality_early_warning,
    ):
        tree = ast.parse(
            inspect.getsource(
                module
            )
        )

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(
                node,
                ast.ImportFrom,
            )
        }

        assert not any(
            imported
            and (
                "ground_truth"
                in imported
                or "data.generators"
                in imported
            )
            for imported in imported_modules
        )

        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
        } | {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Attribute,
            )
        }

        assert forbidden_calls.isdisjoint(
            called_names
        )


def test_collinearity_removal_drops_near_duplicate_column() -> None:
    # power_kw is an exact linear transform of machine_load across every
    # analytical bucket -- correlation 1.0, must be dropped.
    records = []
    for minute in range(30):
        records.append(_record(minute, "machine_load", float(minute)))
        records.append(_record(minute, "power_kw", float(minute) * 2.0 + 5.0))
        records.append(_record(minute, "quality_score", 0.5))

    config = _test_panel_config(
        collinearity_threshold=0.999,
        normalize_data=False,
        max_dominant_value_fraction=1.1,
    )
    result = build_manufacturing_panel(records, config)

    columns = set(result.panel.columns)
    assert "MACHINE_TEST_001||machine_load" in columns
    assert "MACHINE_TEST_001||power_kw" not in columns
    assert any(
        reason.startswith("collinear_with:")
        for column, reason in result.dropped_metrics.items()
        if column == "MACHINE_TEST_001||power_kw"
    )


def test_variable_budget_cap_uses_pre_normalization_variance() -> None:
    # Three metrics with deliberately distinct pre-normalization variance
    # (power_kw >> machine_load >> quality_score) and NOT collinear with
    # each other. max_variables=2 should keep the two most informative
    # columns by their ORIGINAL variance -- if the budget cap incorrectly
    # ran on already-normalized (var~=1 for everyone) data instead, this
    # would become an arbitrary/tie-broken selection instead.
    records = []
    bucket_values = {
        "machine_load": [10.0, 20.0, 30.0],
        "power_kw": [5.0, 5.0, 50.0],
        "quality_score": [0.50, 0.51, 0.49],
    }
    for bucket_index, bucket_start_minute in enumerate((0, 15, 30)):
        for metric, values in bucket_values.items():
            for offset in range(15):
                records.append(
                    _record(
                        bucket_start_minute + offset,
                        metric,
                        values[bucket_index],
                    )
                )

    config = _test_panel_config(
        collinearity_threshold=0.999,
        normalize_data=True,
        max_variables=2,
        max_dominant_value_fraction=1.1,
    )
    result = build_manufacturing_panel(records, config)

    columns = set(result.panel.columns)
    assert columns == {
        "MACHINE_TEST_001||machine_load",
        "MACHINE_TEST_001||power_kw",
    }
    assert result.dropped_metrics["MACHINE_TEST_001||quality_score"] == "variable_budget"

    # Surviving columns are genuinely z-scored (normalize_data=True took
    # effect after the budget cap used pre-normalization variance).
    for column in result.panel.columns:
        assert result.panel[column].mean() == pytest.approx(0.0, abs=1e-9)


def test_algorithm_choice_participates_in_source_signature() -> None:
    # Switching algorithm must always produce a fresh run rather than
    # reusing a persisted run computed under a different engine.
    records = [
        _record(0, "machine_load", 1.0),
        _record(1, "machine_load", 2.0),
    ]

    common_kwargs = dict(
        machine_ids=("MACHINE_TEST_001",),
        observations=None,
        history_hours=72.0,
        raw_frequency_minutes=1.0,
        tau_max=DEFAULT_TAU_MAX,
        pc_alpha=0.05,
        force_include_metrics=None,
        panel_config=ManufacturingPanelConfig(),
        filter_config=DEFAULT_MANUFACTURING_FILTER_CONFIG,
    )

    lpcmci_parameters = _analysis_parameters(**common_kwargs, algorithm="lpcmci")
    pcmci_parameters = _analysis_parameters(**common_kwargs, algorithm="pcmci")

    assert lpcmci_parameters["algorithm"] == "lpcmci"
    assert pcmci_parameters["algorithm"] == "pcmci"

    lpcmci_signature = _source_signature(records, parameters=lpcmci_parameters)
    pcmci_signature = _source_signature(records, parameters=pcmci_parameters)

    assert lpcmci_signature != pcmci_signature

    # Identical algorithm + identical source -> identical signature (the
    # reuse path still works after the algorithm knob was added).
    assert lpcmci_signature == _source_signature(
        records, parameters=_analysis_parameters(**common_kwargs, algorithm="lpcmci")
    )


def _stationarity_records(rng: np.random.Generator) -> list[dict[str, object]]:
    """30 fifteen-minute buckets: a trending column and a stationary one."""
    records = []
    for bucket in range(30):
        trend_value = float(bucket * 15.0 + rng.normal(0, 2))
        stationary_value = float(50.0 + rng.normal(0, 3))
        for offset in range(15):
            minute = bucket * 15 + offset
            records.append(_record(minute, "machine_load", trend_value))
            records.append(_record(minute, "power_kw", stationary_value))
    return records


def test_production_defaults_apply_normalization() -> None:
    # Proves ManufacturingPanelConfig()'s production default
    # (normalize_data=True) actually normalizes. Stationarity differencing
    # is explicitly disabled here ONLY to isolate this assertion from a
    # different feature's statistical randomness (KPSS has a real ~5%
    # false-positive rate per column even on pure white noise, which would
    # otherwise occasionally shift a column's post-differencing mean away
    # from 0 and make this test flaky for reasons unrelated to what it's
    # testing) -- stationarity differencing itself is independently proven
    # under FULL, un-overridden production defaults by
    # test_production_defaults_apply_stationarity_differencing below.
    rng = np.random.default_rng(0)
    records = []
    for bucket in range(30):
        machine_load_value = float(40.0 + rng.normal(0, 3))
        power_kw_value = float(50.0 + rng.normal(0, 3))
        for offset in range(15):
            minute = bucket * 15 + offset
            records.append(_record(minute, "machine_load", machine_load_value))
            records.append(_record(minute, "power_kw", power_kw_value))

    config = replace(
        ManufacturingPanelConfig(),
        stationarity_differencing_enabled=False,
    )
    result = build_manufacturing_panel(records, config)

    assert not result.panel.empty
    assert result.differenced_metrics == []
    for column in result.panel.columns:
        assert result.panel[column].mean() == pytest.approx(0.0, abs=1e-6)
        assert result.panel[column].std() == pytest.approx(1.0, abs=0.5)


def test_production_defaults_apply_stationarity_differencing() -> None:
    # A clearly trending column must be flagged non-stationary and
    # differenced; a clearly stationary column must be left alone.
    # Verified empirically against real statsmodels ADF/KPSS output at
    # seed=0 before being pinned as a regression test.
    rng = np.random.default_rng(0)
    records = _stationarity_records(rng)

    result = build_manufacturing_panel(records, ManufacturingPanelConfig())

    assert "MACHINE_TEST_001||machine_load" in result.differenced_metrics
    assert "MACHINE_TEST_001||power_kw" not in result.differenced_metrics


def test_production_defaults_apply_collinearity_removal() -> None:
    # power_kw is an exact linear transform of machine_load -- must be
    # dropped under PRODUCTION DEFAULTS (no config override). machine_load
    # carries genuine noise (not a perfectly deterministic ramp) so that
    # stationarity differencing -- which also runs under production
    # defaults and precedes collinearity removal -- doesn't degenerate
    # both columns into exact constants (a perfectly linear, noiseless
    # ramp's diff is a constant, which breaks correlation entirely and
    # would trivially defeat this test for reasons unrelated to what it's
    # testing). power_kw is an EXACT transform of the already-noisy
    # machine_load (not independently noised), so the two stay perfectly
    # collinear before and after differencing either way.
    rng = np.random.default_rng(5)
    records = []
    for minute in range(200):
        machine_load_value = float(minute) + float(rng.normal(0, 0.3))
        records.append(_record(minute, "machine_load", machine_load_value))
        records.append(_record(minute, "power_kw", machine_load_value * 3.0 - 7.0))

    result = build_manufacturing_panel(records, ManufacturingPanelConfig())

    columns = set(result.panel.columns)
    assert "MACHINE_TEST_001||machine_load" in columns
    assert "MACHINE_TEST_001||power_kw" not in columns
    assert result.dropped_metrics["MACHINE_TEST_001||power_kw"].startswith(
        "collinear_with:"
    )


def test_production_defaults_discover_lag0_and_preserve_each_orientation_bucket() -> None:
    # End-to-end: production-default panel -> production-default (LPCMCI,
    # apply_fdr_correction=False) filtering -> lag-0 tests survive and every
    # orientation bucket that appears is one of the four valid values.
    from app.ai.causal.manufacturing_filter import (
        ManufacturingFilterConfig,
        filter_manufacturing_tests,
    )
    from app.ai.causal.pcmci_engine import run_lpcmci_tests

    rng = np.random.default_rng(3)
    n = 250
    a = rng.normal(0, 1, n)
    b = 0.7 * a + rng.normal(0, 0.3, n)  # contemporaneous (lag-0) relationship
    records = []
    for minute in range(n):
        records.append(_record(minute, "machine_load", float(a[minute])))
        records.append(_record(minute, "power_kw", float(b[minute])))

    panel_config = ManufacturingPanelConfig(
        analysis_frequency="1min",
        min_data_coverage=0.0,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        stationarity_differencing_enabled=False,
        normalize_data=True,
    )
    result = build_manufacturing_panel(records, panel_config)
    assert result.panel.shape[1] == 2

    tests = run_lpcmci_tests(
        result.panel.to_numpy(dtype=float),
        tuple(result.panel.columns),
        tau_max=1,
        pc_alpha=0.1,
        test_contemporaneous=True,
    )
    assert any(test.lag == 0 for test in tests), "expected a discovered lag-0 (contemporaneous) test"

    filtered = filter_manufacturing_tests(
        tests,
        result.metadata,
        config=ManufacturingFilterConfig(min_lag=0, apply_fdr_correction=False),
    )
    assert filtered.accepted_edges
    for edge in filtered.accepted_edges:
        assert edge.edge_orientation in (
            "DIRECTED",
            "BIDIRECTED",
            "PARTIALLY_ORIENTED",
            "AMBIGUOUS",
        )
        assert edge.edge_mark
