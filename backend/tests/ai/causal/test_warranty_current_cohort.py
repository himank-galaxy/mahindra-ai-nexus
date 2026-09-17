"""Focused tests for production-aligned current-cohort warranty warnings."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from app.ai.causal.manufacturing_filter import (
    DEFAULT_MANUFACTURING_FILTER_CONFIG,
)
from app.ai.causal.manufacturing_loader import (
    LINEAGE_COLUMNS,
    MANUFACTURING_METRICS,
    _duration_window_start,
    fetch_raw_records,
)
from app.ai.causal.manufacturing_panel import ManufacturingPanelConfig
from app.services.manufacturing_causal import (
    ManufacturingCausalService,
    _analysis_parameters,
    _source_signature,
)
from app.services.warranty_quality_early_warning import (
    WarrantyQualityEarlyWarningService,
    _causal_paths_for_issue,
)


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _Rows:
        return self

    def mappings(self) -> _Rows:
        return self

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, results: list[list[Any]]) -> None:
        self._results = list(results)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Rows:
        self.statements.append(statement)
        return _Rows(self._results.pop(0))


def _service_row() -> dict[str, Any]:
    return {
        "issue_category": "CURRENT_ISSUE",
        "severity": "HIGH",
        "complaint_reported": True,
        "repair_required": True,
        "warranty_candidate": True,
        "representative_machine_id": "MACHINE_CURRENT",
        "vehicle_id": "VEHICLE_CURRENT",
        "production_batch_id": "BATCH_CURRENT",
        "primary_supplier_lot_id": "LOT_CURRENT",
        "vehicle_model_id": "MODEL_CURRENT",
        "city_id": "CITY_CURRENT",
    }


def _wide_row(timestamp: datetime) -> dict[str, Any]:
    row: dict[str, Any] = {
        "timestamp": timestamp,
        "plant_id": "PLANT_CURRENT",
        "plant_name": "Current Plant",
        "production_line_id": "LINE_CURRENT",
        "production_line_name": "Current Line",
        "line_type": "ASSEMBLY",
        "machine_id": "MACHINE_CURRENT",
        "machine_name": "Current Machine",
        "production_batch_id": "BATCH_CURRENT",
        "vehicle_model_id": "MODEL_CURRENT",
        "vehicle_model_name": "Current Model",
        "supplier_lot_id": "LOT_CURRENT",
    }
    assert set(LINEAGE_COLUMNS).issubset(row)
    row.update(
        {
            metric: float(index)
            for index, metric in enumerate(
                MANUFACTURING_METRICS,
                start=1,
            )
        }
    )
    return row


@pytest.mark.asyncio
async def test_current_telematics_cohort_is_loaded_dynamically() -> None:
    vehicle_ids = [
        f"VEHICLE_{index:02d}"
        for index in range(24)
    ]
    session = _Session([vehicle_ids])
    service = WarrantyQualityEarlyWarningService(session)  # type: ignore[arg-type]

    assert await service._load_current_vehicle_ids() == tuple(vehicle_ids)
    sql = str(session.statements[0])
    assert "vehicle_telematics_timeseries.vehicle_id" in sql
    assert "DISTINCT" in sql


@pytest.mark.asyncio
async def test_field_queries_exclude_historical_non_cohort_vehicles() -> None:
    session = _Session([[_service_row()], []])
    service = WarrantyQualityEarlyWarningService(session)  # type: ignore[arg-type]

    issues = await service._load_field_issues(
        ("MACHINE_CURRENT",),
        ("VEHICLE_CURRENT",),
    )

    assert set(issues) == {"CURRENT_ISSUE"}
    assert len(session.statements) == 2

    for statement in session.statements:
        sql = str(statement)
        params = statement.compile().params
        assert "representative_machine_id IN" in sql
        assert "vehicle_id IN" in sql
        assert "VEHICLE_CURRENT" in repr(params)
        assert "VEHICLE_HISTORICAL" not in repr(params)


@pytest.mark.asyncio
async def test_explicit_analysis_anchor_bounds_the_source_query() -> None:
    analysis_end = datetime(2026, 7, 27, 18, 29, tzinfo=UTC)
    session = _Session(
        [
            ["MACHINE_CURRENT"],
            [
                _wide_row(analysis_end - timedelta(minutes=1)),
                _wide_row(analysis_end),
            ],
        ]
    )

    records = await fetch_raw_records(
        session,  # type: ignore[arg-type]
        ("MACHINE_CURRENT",),
        history_hours=72.0,
        analysis_end=analysis_end,
    )

    source_statement = session.statements[1]
    assert "manufacturing_timeseries.timestamp <=" in str(source_statement)
    assert analysis_end in source_statement.compile().params.values()
    assert max(record["timestamp"] for record in records) == analysis_end


@pytest.mark.asyncio
async def test_analysis_anchor_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await fetch_raw_records(
            _Session([]),  # type: ignore[arg-type]
            ("MACHINE_CURRENT",),
            analysis_end=datetime(2026, 7, 27, 18, 29),
        )


def test_anchor_is_persisted_and_changes_the_source_signature() -> None:
    records = [
        {
            "timestamp": datetime(2026, 7, 25, tzinfo=UTC),
            "entity": "MACHINE_CURRENT",
            "machine_id": "MACHINE_CURRENT",
            "metric": "machine_load",
            "value": 1.0,
        }
    ]
    common = {
        "machine_ids": ("MACHINE_CURRENT",),
        "observations": None,
        "history_hours": 72.0,
        "raw_frequency_minutes": 1.0,
        "tau_max": 12,
        "pc_alpha": 0.05,
        "force_include_metrics": None,
        "panel_config": ManufacturingPanelConfig(),
        "filter_config": DEFAULT_MANUFACTURING_FILTER_CONFIG,
    }
    unanchored = _analysis_parameters(**common)
    anchored = _analysis_parameters(
        **common,
        analysis_end=datetime(2026, 7, 27, 18, 29, tzinfo=UTC),
    )

    assert unanchored["analysis_end"] is None
    assert anchored["analysis_end"] == "2026-07-27T18:29:00+00:00"
    assert _source_signature(records, parameters=unanchored) != (
        _source_signature(records, parameters=anchored)
    )


def test_exact_machine_batch_lot_tuple_remains_mandatory() -> None:
    issues = {
        "ISSUE": {
            "field_lineages": {
                ("MACHINE_CURRENT", "BATCH_CURRENT", "LOT_CURRENT")
            }
        }
    }

    WarrantyQualityEarlyWarningService._apply_exact_lineage(
        issues,
        {("MACHINE_OTHER", "BATCH_CURRENT", "LOT_CURRENT")},
    )
    assert issues["ISSUE"]["exact_window_lineages"] == set()

    WarrantyQualityEarlyWarningService._apply_exact_lineage(
        issues,
        {("MACHINE_CURRENT", "BATCH_CURRENT", "LOT_CURRENT")},
    )
    assert issues["ISSUE"]["exact_window_lineages"] == {
        ("MACHINE_CURRENT", "BATCH_CURRENT", "LOT_CURRENT")
    }


def test_representative_machine_must_support_a_persisted_edge() -> None:
    edge = SimpleNamespace(
        source_metric="machine_load",
        target_metric="power_kw",
        scope="ALL",
        consensus_sign="POSITIVE",
        recurring_machines=1,
        eligible_machines=1,
        recurrence_fraction=1.0,
        sign_agreement=1.0,
        mean_abs_score=0.5,
        median_abs_score=0.5,
        best_q_value=0.01,
        observed_lags=[1],
        machine_ids=["MACHINE_OTHER"],
        edge_orientation="DIRECTED",
        consensus_edge_mark="-->",
        mark_agreement=1.0,
    )
    lineage = {("MACHINE_CURRENT", "BATCH_CURRENT", "LOT_CURRENT")}

    assert _causal_paths_for_issue(lineage, [edge], limit=6) == ()

    edge.machine_ids = ["MACHINE_CURRENT"]
    assert len(_causal_paths_for_issue(lineage, [edge], limit=6)) == 1


def test_anchored_window_covers_cohort_production_timestamp() -> None:
    production_timestamp = datetime(2026, 7, 24, 18, 30, tzinfo=UTC)
    analysis_end = datetime(2026, 7, 27, 18, 29, tzinfo=UTC)

    assert _duration_window_start(analysis_end, 72.0) < production_timestamp
    assert production_timestamp <= analysis_end


def test_persistence_path_does_not_delete_historical_runs() -> None:
    source = inspect.getsource(ManufacturingCausalService.get_or_run)

    assert "delete(" not in source
    assert "on_conflict_do_nothing" in source
