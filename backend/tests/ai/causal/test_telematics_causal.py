"""Focused contract tests for the independent vehicle-telematics pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from app.ai.causal.pcmci_engine import PcmciTest, pcmci_tests_as_causal_discovery_tests
from app.ai.causal.telematics_filter import (
    TelematicsFilterConfig,
    aggregate_telematics_stability,
    filter_telematics_tests,
)
from app.ai.causal.telematics_loader import (
    TELEMATICS_CONTEXT_FIELDS,
    TELEMATICS_EXCLUDED_FIELDS,
    TELEMATICS_METRICS,
    detect_raw_frequency_minutes,
)
from app.ai.causal.telematics_panel import (
    TelematicsPanelConfig,
    build_telematics_panel,
)
from app.services.telematics_causal import _source_signature


def _records(vehicle_id: str = "VEH-1", rows: int = 12) -> list[dict[str, object]]:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    output: list[dict[str, object]] = []
    for index in range(rows):
        timestamp = start + timedelta(minutes=index)
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
        for metric, value in (
            ("vehicle_speed_kph", float(index + 1)),
            ("battery_temperature_c", 30.0 + index * 0.1),
            ("impact_g_force", 0.1 if index < rows - 1 else 2.0),
        ):
            output.append(
                {
                    "timestamp": timestamp,
                    "entity": vehicle_id,
                    "metric": metric,
                    "value": value,
                    **context,
                }
            )
    return output


def _panel_config() -> TelematicsPanelConfig:
    return TelematicsPanelConfig(
        analysis_frequency="5min",
        min_panel_observations=2,
        min_data_coverage=0.5,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        # Tests in this module assert on raw physical aggregation values —
        # normalization/collinearity removal get their own dedicated
        # coverage.
        normalize_data=False,
    )


def test_telematics_variable_contract_excludes_context_downstream_and_provenance() -> None:
    assert len(TELEMATICS_METRICS) == 17
    assert set(TELEMATICS_CONTEXT_FIELDS).isdisjoint(TELEMATICS_METRICS)
    assert set(TELEMATICS_EXCLUDED_FIELDS).isdisjoint(TELEMATICS_METRICS)
    assert {"odometer_km", "dtc_count", "warning_flag"}.issubset(TELEMATICS_EXCLUDED_FIELDS)


def test_panel_resamples_with_physical_aggregation_and_preserves_lineage_as_metadata() -> None:
    records = _records(rows=15)
    records.append({**records[0], "value": 99.0})
    records.extend(
        {
            **records[1],
            "metric": excluded,
            "value": 1.0,
        }
        for excluded in ("odometer_km", "warning_flag", "data_origin")
    )
    result = build_telematics_panel(records, _panel_config())
    assert result.panel.index[1] - result.panel.index[0] == timedelta(minutes=5)
    assert set(result.panel.columns) == {
        "VEH-1||battery_temperature_c",
        "VEH-1||impact_g_force",
        "VEH-1||vehicle_speed_kph",
    }
    assert result.duplicate_records_removed == 1
    assert result.panel["VEH-1||impact_g_force"].max() == pytest.approx(2.0)
    assert result.metadata["VEH-1||vehicle_speed_kph"]["vehicle_model_id"] == "MODEL-1"
    assert all("odometer" not in column and "warning" not in column for column in result.panel.columns)


def test_panel_rejects_cross_vehicle_concatenation_and_drops_low_information() -> None:
    with pytest.raises(ValueError, match="exactly one vehicle"):
        build_telematics_panel(_records("VEH-1") + _records("VEH-2"), _panel_config())
    records = _records(rows=15)
    records.extend({**record, "metric": "battery_voltage_v", "value": 401.0} for record in records[:15])
    result = build_telematics_panel(records, _panel_config())
    assert "VEH-1||battery_voltage_v" in result.dropped_metrics


def test_loader_cadence_is_inferred_per_vehicle() -> None:
    rows = [
        {"vehicle_id": "VEH-1", "timestamp": datetime(2026, 8, 1, tzinfo=UTC) + timedelta(minutes=index)}
        for index in range(4)
    ]
    assert detect_raw_frequency_minutes(rows) == pytest.approx(1.0)


def test_telematics_filter_applies_complete_family_fdr_and_stability() -> None:
    results = []
    for vehicle_id in ("VEH-1", "VEH-2", "VEH-3"):
        source = f"{vehicle_id}||vehicle_speed_kph"
        target = f"{vehicle_id}||battery_temperature_c"
        metadata = {
            source: {"vehicle_id": vehicle_id},
            target: {"vehicle_id": vehicle_id},
        }
        tests = pcmci_tests_as_causal_discovery_tests(
            [
                PcmciTest(source, target, 2, 0.5, 0.001),
                PcmciTest(target, source, 1, -0.4, 0.002),
            ]
        )
        results.append(
            filter_telematics_tests(
                tests,
                metadata,
                TelematicsFilterConfig(
                    min_abs_score=0.1,
                    min_recurrence_count=2,
                    min_recurrence_fraction=0.5,
                    min_sign_agreement=1.0,
                ),
            )
        )
    stability = aggregate_telematics_stability(
        results,
        analysis_frequency_minutes=5,
        config=TelematicsFilterConfig(
            min_abs_score=0.1,
            min_recurrence_count=2,
            min_recurrence_fraction=0.5,
            min_sign_agreement=1.0,
        ),
    )
    assert stability.vehicles_evaluated == 3
    assert len(stability.stable_edges) == 2
    speed_edge = next(edge for edge in stability.stable_edges if edge.source_metric == "vehicle_speed_kph")
    assert speed_edge.observed_lags == (2,)
    assert speed_edge.observed_lag_minutes == (10,)
    assert speed_edge.vehicle_ids == ("VEH-1", "VEH-2", "VEH-3")
    assert speed_edge.min_p_value == pytest.approx(0.001)
    assert speed_edge.consensus_sign == "+"


def test_signature_is_order_independent_and_does_not_use_truth() -> None:
    parameters = {"vehicle_ids": ["VEH-1"], "tau_max": 12}
    first = _source_signature({"VEH-1": "abc"}, parameters)
    second = _source_signature({"VEH-1": "abc"}, {"tau_max": 12, "vehicle_ids": ["VEH-1"]})
    assert first == second
    service_source = Path(__file__).parents[3] / "app" / "services" / "telematics_causal.py"
    text = service_source.read_text(encoding="utf-8")
    assert "ground_truth" not in text
    assert "synthetic" not in text


def test_panel_rejects_insufficient_window_and_nonfinite_values() -> None:
    config = TelematicsPanelConfig(min_panel_observations=4)
    with pytest.raises(ValueError, match="analytical rows"):
        build_telematics_panel(_records(rows=5), config)
    records = _records(rows=15)
    records[0]["value"] = np.inf
    result = build_telematics_panel(records, _panel_config())
    assert result.duplicate_records_removed == 0


def _telematics_stationarity_records(rng: np.random.Generator) -> list[dict[str, object]]:
    """30 five-minute buckets: a trending column and a stationary one."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
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
    records: list[dict[str, object]] = []
    for bucket in range(30):
        trend_value = float(bucket * 5.0 + rng.normal(0, 2))
        stationary_value = float(30.0 + rng.normal(0, 3))
        for offset in range(5):
            minute = bucket * 5 + offset
            timestamp = start + timedelta(minutes=minute)
            records.append(
                {
                    "timestamp": timestamp,
                    "entity": "VEH-1",
                    "metric": "vehicle_speed_kph",
                    "value": trend_value,
                    **context,
                }
            )
            records.append(
                {
                    "timestamp": timestamp,
                    "entity": "VEH-1",
                    "metric": "battery_temperature_c",
                    "value": stationary_value,
                    **context,
                }
            )
    return records


def test_production_defaults_apply_normalization() -> None:
    # Proves TelematicsPanelConfig()'s production default
    # (normalize_data=True) actually normalizes. Stationarity differencing
    # is isolated out here (see the manufacturing-panel test of the same
    # name for the full rationale: KPSS's real false-positive rate on pure
    # noise would otherwise make this flaky for reasons unrelated to what
    # it tests); differencing itself is proven separately below.
    rng = np.random.default_rng(0)
    start = datetime(2026, 8, 1, tzinfo=UTC)
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
    records: list[dict[str, object]] = []
    for bucket in range(30):
        speed_value = float(40.0 + rng.normal(0, 3))
        battery_value = float(30.0 + rng.normal(0, 3))
        for offset in range(5):
            minute = bucket * 5 + offset
            timestamp = start + timedelta(minutes=minute)
            records.append(
                {"timestamp": timestamp, "entity": "VEH-1", "metric": "vehicle_speed_kph", "value": speed_value, **context}
            )
            records.append(
                {
                    "timestamp": timestamp,
                    "entity": "VEH-1",
                    "metric": "battery_temperature_c",
                    "value": battery_value,
                    **context,
                }
            )

    config = TelematicsPanelConfig(min_panel_observations=10, stationarity_differencing_enabled=False)
    result = build_telematics_panel(records, config)

    assert not result.panel.empty
    assert result.differenced_metrics == []
    for column in result.panel.columns:
        assert result.panel[column].mean() == pytest.approx(0.0, abs=1e-6)
        assert result.panel[column].std() == pytest.approx(1.0, abs=0.5)


def test_production_defaults_apply_stationarity_differencing() -> None:
    rng = np.random.default_rng(0)
    records = _telematics_stationarity_records(rng)

    config = TelematicsPanelConfig(min_panel_observations=10)
    result = build_telematics_panel(records, config)

    assert "VEH-1||vehicle_speed_kph" in result.differenced_metrics
    assert "VEH-1||battery_temperature_c" not in result.differenced_metrics


def test_production_defaults_apply_collinearity_removal() -> None:
    # battery_temperature_c is an exact linear transform of
    # vehicle_speed_kph -- must be dropped under PRODUCTION DEFAULTS.
    # vehicle_speed_kph carries genuine noise (see the equivalent
    # manufacturing-panel test for why a perfectly noiseless ramp would
    # degenerate post-differencing and defeat this test for unrelated
    # reasons); battery_temperature_c is an EXACT transform of the
    # already-noisy speed value, so both stay perfectly collinear whether
    # or not differencing fires.
    rng = np.random.default_rng(5)
    start = datetime(2026, 8, 1, tzinfo=UTC)
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
    records: list[dict[str, object]] = []
    for minute in range(200):
        timestamp = start + timedelta(minutes=minute)
        speed_value = float(minute) + float(rng.normal(0, 0.3))
        records.append(
            {"timestamp": timestamp, "entity": "VEH-1", "metric": "vehicle_speed_kph", "value": speed_value, **context}
        )
        records.append(
            {
                "timestamp": timestamp,
                "entity": "VEH-1",
                "metric": "battery_temperature_c",
                "value": speed_value * 3.0 - 7.0,
                **context,
            }
        )

    config = TelematicsPanelConfig(min_panel_observations=10)
    result = build_telematics_panel(records, config)

    # Deterministic alphabetical tie-break keeps the earlier column name:
    # "battery_temperature_c" < "vehicle_speed_kph".
    columns = set(result.panel.columns)
    assert "VEH-1||battery_temperature_c" in columns
    assert "VEH-1||vehicle_speed_kph" not in columns
    assert result.dropped_metrics["VEH-1||vehicle_speed_kph"].startswith("collinear_with:")


def test_production_defaults_discover_lag0_and_preserve_each_orientation_bucket() -> None:
    # End-to-end: production-default panel -> production-default (LPCMCI,
    # apply_fdr_correction=False) filtering -> lag-0 tests survive and every
    # orientation bucket that appears is one of the four valid values.
    rng = np.random.default_rng(3)
    n = 250
    a = rng.normal(0, 1, n)
    b = 0.7 * a + rng.normal(0, 0.3, n)  # contemporaneous (lag-0) relationship
    start = datetime(2026, 8, 1, tzinfo=UTC)
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
    records: list[dict[str, object]] = []
    for minute in range(n):
        timestamp = start + timedelta(minutes=minute)
        records.append(
            {"timestamp": timestamp, "entity": "VEH-1", "metric": "vehicle_speed_kph", "value": float(a[minute]), **context}
        )
        records.append(
            {
                "timestamp": timestamp,
                "entity": "VEH-1",
                "metric": "battery_temperature_c",
                "value": float(b[minute]),
                **context,
            }
        )

    panel_config = TelematicsPanelConfig(
        analysis_frequency="1min",
        min_panel_observations=10,
        min_data_coverage=0.0,
        min_row_completeness=0.5,
        skew_transform_enabled=False,
        stationarity_differencing_enabled=False,
        normalize_data=True,
    )
    result = build_telematics_panel(records, panel_config)
    assert result.panel.shape[1] == 2

    from app.ai.causal.pcmci_engine import run_lpcmci_tests

    tests = run_lpcmci_tests(
        result.panel.to_numpy(dtype=float),
        tuple(result.panel.columns),
        tau_max=1,
        pc_alpha=0.1,
        test_contemporaneous=True,
    )
    assert any(test.lag == 0 for test in tests), "expected a discovered lag-0 (contemporaneous) test"

    filtered = filter_telematics_tests(
        tests,
        result.metadata,
        config=TelematicsFilterConfig(min_lag=0, apply_fdr_correction=False),
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
