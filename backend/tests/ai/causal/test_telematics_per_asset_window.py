"""Regression tests for per-vehicle analytical-window resolution.

Context
-------
The telematics scheduler builds ONE domain-wide source plan
(``build_telematics_source_plan``) and hands every selected vehicle the
same ``source_from``/``source_to``. But an individual vehicle's own
telemetry can end earlier than the domain-wide ``source_to`` (the replay
cursor advances on the strength of OTHER vehicles' data), so fetching the
literal domain window for every vehicle silently truncates that vehicle's
usable history. For VEHUNIT_SYN_0001275 in production this collapsed an
intended 168h window down to ~82.8h (994 rows instead of ~2016 analytical
rows), which is what triggered LPCMCI's pathological (>20 minute) runtime.

The fix re-anchors each SELECTED vehicle individually:
``vehicle_visible_to = MAX(vehicle timestamp <= plan.source_to)``,
``vehicle_analysis_to = vehicle_visible_to``,
``vehicle_analysis_from = vehicle_analysis_to - history_hours`` -- see
``app.services.telematics_causal._resolve_vehicle_analysis_window`` and
``app.ai.causal.telematics_loader.get_vehicle_visible_latest_timestamp``.

This file proves the 13 enumerated requirements from that task:
(1) vehicle latest == plan.source_to preserves the existing effective
    window: [Test1]
(2) vehicle latest < plan.source_to shifts the window backward to
    preserve the requested history: [Test2]
(3) no observation > plan.source_to is ever fetched: [Test3]
(4) the exact VEHUNIT_SYN_0001275 Sep7/Sep3 scenario yields a window
    ending Sep3 and starting ~168h earlier: [Test4]
(5) full 168h 1-minute data still produces the expected raw row count
    (boundary behavior stays consistent with the existing loader): [Test5]
(6) different selected vehicles can get different per-vehicle bounds
    within the same scheduler-driven call: [Test6]
(7) the scheduler source/replay plan itself remains unchanged: verified
    by inspection, not re-derived here -- ``build_telematics_source_plan``
    and ``_run_telematics_job`` in app/scheduler/causal_scheduler.py were
    not modified by this change (see the git diff / final report).
(8) scheduler/service reuse remains safe when a vehicle's effective data
    changes: the persisted-run signature is content-based
    (``_row_digest`` hashes the actual fetched rows), so a corrected,
    wider per-vehicle window necessarily changes the signature: [Test8]
(9)/(10)/(11) LPCMCI orientation/PAG behavior, PCMCI rollback, and
    Mobility are untouched by this change -- pcmci_engine.py and the
    mobility pipeline were not modified; covered by the existing full
    causal suite remaining green.
(12) no future/replay-invisible data ever leaks into analysis: [Test3],
     [TestNoVisibleData]
(13) the existing causal suite remains green: verified by running the
     full suite alongside this file, not duplicated here.

Edge cases covered explicitly: a vehicle with no data at or before the
replay cutoff ([TestNoVisibleData]), a vehicle with less than the minimum
required history ([TestInsufficientHistory]), a vehicle whose latest
timestamp exactly equals plan.source_to ([Test1]), a vehicle with full
data through plan.source_to ([Test1], [Test5]), multiple vehicles with
different latest-visible timestamps ([Test6]), and a call with no domain
plan bounds at all -- proven to touch the database zero extra times and
behave exactly as before the fix ([TestNoDomainBounds]).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.ai.causal.telematics_filter import TelematicsFilterResult
from app.ai.causal.telematics_loader import TELEMATICS_METRICS, fetch_vehicle_rows
from app.database.runtime_schema import runtime_metadata, runtime_tables
from app.services import telematics_causal
from app.services.telematics_causal import (
    TelematicsCausalService,
    _resolve_vehicle_analysis_window,
    _row_digest,
    _source_signature,
    _VehicleAnalysis,
)
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

TELEMATICS_TABLE = runtime_tables["vehicle_telematics_timeseries"]
DELIVERIES_TABLE = runtime_tables["deliveries"]

TELEMATICS_HISTORY_HOURS = 168.0


def _delivery_row(vehicle_id: str, delivered_at: datetime) -> dict[str, Any]:
    return {
        "delivery_id": f"DLV-{vehicle_id}",
        "allocation_id": f"ALLOC-{vehicle_id}",
        "booking_id": f"BOOK-{vehicle_id}",
        "lead_id": f"LEAD-{vehicle_id}",
        "customer_id": f"CUST-{vehicle_id}",
        "vehicle_id": vehicle_id,
        "vehicle_model_id": "MODEL-1",
        "vehicle_model_name": "Test Model",
        "variant": "EV",
        "dealer_id": "DEALER-1",
        "dealer_name": "Dealer",
        "region_id": "REGION-1",
        "region_name": "Region",
        "city_id": "CITY-1",
        "city_name": "City",
        "production_batch_id": "BATCH-1",
        "plant_id": "PLANT-1",
        "plant_name": "Plant",
        "production_line_id": "LINE-1",
        "production_line_name": "Line",
        "representative_machine_id": "MACHINE-1",
        "representative_machine_name": "Machine",
        "primary_supplier_id": "SUPPLIER-1",
        "primary_supplier_name": "Supplier",
        "primary_supplier_lot_id": "LOT-1",
        "supplier_lot_quality_score": 1.0,
        "production_quality_score": 1.0,
        "booking_timestamp": delivered_at - timedelta(days=30),
        "allocation_date": delivered_at - timedelta(days=20),
        "promised_delivery_date": delivered_at,
        "dispatch_at": delivered_at - timedelta(days=2),
        "physical_ready_date": delivered_at - timedelta(days=5),
        "projected_delivery_date": delivered_at,
        "actual_delivery_date": delivered_at,
        "dispatch_delay_hours": 0.0,
        "base_transit_days": 1.0,
        "transport_disruption": False,
        "disruption_days": 0.0,
        "total_transit_days": 1.0,
        "regional_demand_index": 1.0,
        "allocation_priority": "NORMAL",
        "allocation_wait_hours": 0.0,
        "demand_pressure": False,
        "quality_hold": False,
        "normal_handover_delay": False,
        "delivery_variance_days": 0.0,
        "delay_days": 0.0,
        "early_days": 0.0,
        "delayed": False,
        "delay_reason": "NONE",
        "customer_handover_completed": True,
        "handover_score": 1.0,
        "delivery_status": "DELIVERED",
        "data_origin": "TEST",
        "generator_version": "1",
    }


def _telemetry_row(vehicle_id: str, timestamp: datetime, seed: float = 0.0) -> dict[str, Any]:
    row: dict[str, Any] = {
        "timestamp": timestamp,
        "vehicle_id": vehicle_id,
        "vehicle_model_id": "MODEL-1",
        "vehicle_model_name": "Test Model",
        "variant": "EV",
        "production_batch_id": "BATCH-1",
        "supplier_lot_id": "LOT-1",
        "plant_id": "PLANT-1",
        "production_line_id": "LINE-1",
        "odometer_km": 1000.0,
        "dtc_count": 0,
        "warning_flag": False,
        "data_origin": "TEST",
        "generator_version": "1",
    }
    for metric in TELEMATICS_METRICS:
        row[metric] = 1.0 + seed
    return row


async def _ensure_runtime_tables(session: AsyncSession) -> None:
    # This test environment's synthetic-data seed module is not present,
    # so the Core-mapped runtime schema (vehicle_telematics_timeseries,
    # deliveries) is never created against the in-memory test engine the
    # way ORM (Base.metadata) tables are. Create just the two tables this
    # file needs, idempotently, directly against the session's engine.
    def _create(sync_session: Any) -> None:
        runtime_metadata.create_all(
            sync_session.get_bind(), tables=[TELEMATICS_TABLE, DELIVERIES_TABLE], checkfirst=True
        )

    await session.run_sync(_create)


async def _seed_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    *,
    earliest: datetime,
    latest: datetime,
    step: timedelta = timedelta(hours=1),
    delivered_at: datetime | None = None,
) -> None:
    await _ensure_runtime_tables(session)
    await session.execute(insert(DELIVERIES_TABLE), [_delivery_row(vehicle_id, delivered_at or (earliest - timedelta(days=60)))])
    rows: list[dict[str, Any]] = []
    timestamp = earliest
    index = 0
    while timestamp <= latest:
        rows.append(_telemetry_row(vehicle_id, timestamp, seed=float(index)))
        timestamp += step
        index += 1
    await session.execute(insert(TELEMATICS_TABLE), rows)
    await session.commit()


# ---------------------------------------------------------------------------
# (1) vehicle latest == plan.source_to preserves the existing effective window
# ---------------------------------------------------------------------------


async def test_1_vehicle_latest_equals_plan_source_to_preserves_existing_window(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    await _seed_vehicle(db_session, "VEH_FULL", earliest=plan_source_from - timedelta(hours=2), latest=plan_source_to)

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_FULL",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )

    assert vehicle_visible_to == plan_source_to
    assert vehicle_source_to == plan_source_to
    assert vehicle_source_from == plan_source_from


# ---------------------------------------------------------------------------
# (2) vehicle latest < plan.source_to shifts the window backward
# ---------------------------------------------------------------------------


async def test_2_vehicle_latest_before_plan_source_to_shifts_window_backward(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    vehicle_latest = plan_source_to - timedelta(hours=4)
    await _seed_vehicle(db_session, "VEH_STALE", earliest=plan_source_from - timedelta(hours=10), latest=vehicle_latest)

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_STALE",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )

    assert vehicle_visible_to == vehicle_latest
    assert vehicle_source_to == vehicle_latest
    assert vehicle_source_from == vehicle_latest - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    # Requested history span is preserved exactly, just shifted backward.
    assert vehicle_source_to - vehicle_source_from == timedelta(hours=TELEMATICS_HISTORY_HOURS)


# ---------------------------------------------------------------------------
# (3) / (12) no observation later than plan.source_to is ever fetched
# ---------------------------------------------------------------------------


async def test_3_no_observation_after_plan_source_to_is_ever_fetched(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    # Telemetry extends 10h PAST the replay cutoff -- must never be used.
    await _seed_vehicle(
        db_session,
        "VEH_FUTURE_DATA",
        earliest=plan_source_from - timedelta(hours=2),
        latest=plan_source_to + timedelta(hours=10),
    )

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_FUTURE_DATA",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )
    assert vehicle_visible_to == plan_source_to
    assert vehicle_source_to == plan_source_to

    rows = await fetch_vehicle_rows(
        db_session,
        "VEH_FUTURE_DATA",
        history_hours=TELEMATICS_HISTORY_HOURS,
        source_from=vehicle_source_from,
        source_to=vehicle_source_to,
    )
    assert all(_as_utc(row["timestamp"]) <= plan_source_to for row in rows)


# ---------------------------------------------------------------------------
# (4) the exact VEHUNIT_SYN_0001275 Sep7/Sep3 production scenario
# ---------------------------------------------------------------------------


async def test_4_reproduces_the_sep7_sep3_production_scenario(db_session: AsyncSession) -> None:
    # Numbers match the production incident: domain plan ends Sep 7, this
    # vehicle's own telemetry actually ends Sep 3.
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    vehicle_latest = datetime(2026, 9, 3, 16, 7, tzinfo=UTC)
    await _seed_vehicle(
        db_session,
        "VEHUNIT_SYN_0001275",
        earliest=vehicle_latest - timedelta(hours=TELEMATICS_HISTORY_HOURS) - timedelta(hours=5),
        latest=vehicle_latest,
    )

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEHUNIT_SYN_0001275",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )

    assert vehicle_visible_to == vehicle_latest
    assert vehicle_source_to == vehicle_latest
    assert vehicle_source_from == vehicle_latest - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    # Before the fix this vehicle's effective window was truncated to
    # ~82.8h (Sep3 minus Sep7's 168h-anchored source_from). After the fix
    # it gets the full requested 168h, ending Sep 3 not Sep 7.
    assert (vehicle_source_to - vehicle_source_from) == timedelta(hours=TELEMATICS_HISTORY_HOURS)
    assert vehicle_source_to < plan_source_to


# ---------------------------------------------------------------------------
# (5) full 168h 1-minute data still yields the expected raw row count
# ---------------------------------------------------------------------------


async def test_5_full_168h_one_minute_data_yields_expected_raw_row_count(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    await _seed_vehicle(
        db_session,
        "VEH_DENSE",
        earliest=plan_source_from,
        latest=plan_source_to,
        step=timedelta(minutes=1),
    )

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_DENSE",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )
    assert vehicle_visible_to == plan_source_to

    rows = await fetch_vehicle_rows(
        db_session,
        "VEH_DENSE",
        history_hours=TELEMATICS_HISTORY_HOURS,
        source_from=vehicle_source_from,
        source_to=vehicle_source_to,
    )
    # 168h * 60 + 1 inclusive one-minute samples -- unchanged boundary
    # behavior from the existing loader (this fix never touches
    # fetch_vehicle_rows's own row-boundary math).
    assert len(rows) == int(TELEMATICS_HISTORY_HOURS * 60) + 1


# ---------------------------------------------------------------------------
# (6) different vehicles get different per-vehicle bounds in the same run
# ---------------------------------------------------------------------------


async def test_6_different_vehicles_get_different_bounds_in_the_same_run(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    await _seed_vehicle(db_session, "VEH_A", earliest=plan_source_from - timedelta(hours=1), latest=plan_source_to)
    await _seed_vehicle(
        db_session,
        "VEH_B",
        earliest=plan_source_from - timedelta(hours=30),
        latest=plan_source_to - timedelta(hours=20),
    )

    window_a = await _resolve_vehicle_analysis_window(
        db_session, "VEH_A", source_from=plan_source_from, source_to=plan_source_to, history_hours=TELEMATICS_HISTORY_HOURS
    )
    window_b = await _resolve_vehicle_analysis_window(
        db_session, "VEH_B", source_from=plan_source_from, source_to=plan_source_to, history_hours=TELEMATICS_HISTORY_HOURS
    )

    assert window_a != window_b
    assert window_a[1] == plan_source_to
    assert window_b[1] == plan_source_to - timedelta(hours=20)


# ---------------------------------------------------------------------------
# (8) signature changes when a vehicle's effective analytical data changes
# ---------------------------------------------------------------------------


def _parameters() -> dict[str, Any]:
    return {
        "pipeline": "vehicle_telematics",
        "algorithm": "lpcmci",
        "tau_max": 2,
        "pc_alpha": 0.10,
    }


def test_8_signature_changes_when_effective_vehicle_window_widens() -> None:
    truncated_rows = [
        {"timestamp": datetime(2026, 9, 3, hour, tzinfo=UTC), **{m: 1.0 for m in TELEMATICS_METRICS}}
        for hour in range(0, 24)
    ]
    full_window_rows = [
        {"timestamp": datetime(2026, 8, 31, hour, tzinfo=UTC), **{m: 1.0 for m in TELEMATICS_METRICS}}
        for hour in range(0, 24)
    ] + truncated_rows

    truncated_digest = {"VEHUNIT_SYN_0001275": _row_digest(truncated_rows)}
    full_digest = {"VEHUNIT_SYN_0001275": _row_digest(full_window_rows)}

    parameters = _parameters()
    signature_before_fix = _source_signature(truncated_digest, parameters)
    signature_after_fix = _source_signature(full_digest, parameters)

    # Same algorithm/config parameters, but the actually-fetched row
    # content differs (correctly widened window) -- the persisted-run
    # signature must not silently stay the same.
    assert signature_before_fix != signature_after_fix


# ---------------------------------------------------------------------------
# Edge cases: no visible data at all, and insufficient history
# ---------------------------------------------------------------------------


async def test_no_visible_data_at_or_before_cutoff_falls_through_and_fails_loudly(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    # All of this vehicle's telemetry is AFTER the replay cutoff.
    await _seed_vehicle(
        db_session,
        "VEH_ALL_FUTURE",
        earliest=plan_source_to + timedelta(hours=1),
        latest=plan_source_to + timedelta(hours=5),
    )

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_ALL_FUTURE",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )
    # No silent substitution: bounds pass through unchanged...
    assert vehicle_visible_to is None
    assert vehicle_source_from == plan_source_from
    assert vehicle_source_to == plan_source_to

    # ...so the existing loader fails loudly rather than fabricating data.
    with pytest.raises(ValueError, match="Unknown vehicle ID or no telemetry"):
        await fetch_vehicle_rows(
            db_session,
            "VEH_ALL_FUTURE",
            history_hours=TELEMATICS_HISTORY_HOURS,
            source_from=vehicle_source_from,
            source_to=vehicle_source_to,
        )


async def test_insufficient_history_still_fails_loudly_after_reanchoring(db_session: AsyncSession) -> None:
    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    # Exactly one observation, right at the cutoff -- reanchoring succeeds
    # (vehicle_visible_to is found) but there still isn't enough data.
    await _seed_vehicle(db_session, "VEH_ONE_ROW", earliest=plan_source_to, latest=plan_source_to)

    vehicle_source_from, vehicle_source_to, vehicle_visible_to = await _resolve_vehicle_analysis_window(
        db_session,
        "VEH_ONE_ROW",
        source_from=plan_source_from,
        source_to=plan_source_to,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )
    assert vehicle_visible_to == plan_source_to

    with pytest.raises(ValueError, match="Insufficient telemetry history"):
        await fetch_vehicle_rows(
            db_session,
            "VEH_ONE_ROW",
            history_hours=TELEMATICS_HISTORY_HOURS,
            source_from=vehicle_source_from,
            source_to=vehicle_source_to,
        )


# ---------------------------------------------------------------------------
# No domain plan bounds at all -> zero behavior change, zero extra queries
# ---------------------------------------------------------------------------


class _PoisonedSession:
    """Raises if touched -- proves no extra DB round-trip happens when the
    caller supplied no domain-level source_from/source_to at all."""

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not query the database when no domain bounds were supplied")


async def test_no_domain_bounds_skips_reanchoring_entirely() -> None:
    result = await _resolve_vehicle_analysis_window(
        _PoisonedSession(),
        "VEH_ANY",
        source_from=None,
        source_to=None,
        history_hours=TELEMATICS_HISTORY_HOURS,
    )
    assert result == (None, None, None)


# ---------------------------------------------------------------------------
# End-to-end through get_or_run(): per-vehicle windows differ, the new
# diagnostic log fires with the right fields, and the persisted run's
# domain-level source envelope reflects the corrected windows.
# ---------------------------------------------------------------------------


def _stub_analysis(vehicle_id: str, rows: list[Any], **_kwargs: object) -> _VehicleAnalysis:
    return _VehicleAnalysis(
        filtered=TelematicsFilterResult(
            vehicle_id=vehicle_id,
            total_tests=0,
            fdr_significant_tests=0,
            effect_size_significant_tests=0,
            accepted_edges=(),
        ),
        analytical_rows=max(len(rows) // 5, 1),
        variables_used=tuple(TELEMATICS_METRICS[:2]),
        dropped_metrics={},
        missing_intervals={},
        transformed_metrics=(),
        duplicate_records_removed=0,
        panel_runtime_seconds=0.001,
        pcmci_runtime_seconds=0.001,
    )


async def test_end_to_end_get_or_run_logs_and_persists_corrected_per_vehicle_windows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(telematics_causal, "_analyse_vehicle", _stub_analysis)

    plan_source_to = datetime(2026, 9, 7, 5, 19, tzinfo=UTC)
    plan_source_from = plan_source_to - timedelta(hours=TELEMATICS_HISTORY_HOURS)
    vehicle_b_latest = plan_source_to - timedelta(hours=20)
    await _seed_vehicle(db_session, "VEH_E2E_A", earliest=plan_source_from - timedelta(hours=1), latest=plan_source_to)
    await _seed_vehicle(
        db_session, "VEH_E2E_B", earliest=plan_source_from - timedelta(hours=30), latest=vehicle_b_latest
    )

    events: list[tuple[str, dict[str, object]]] = []

    def spy_logger_info(event: str, **kwargs: object) -> None:
        events.append((event, kwargs))

    monkeypatch.setattr(telematics_causal.logger, "info", spy_logger_info)

    result = await TelematicsCausalService(db_session).get_or_run(
        ["VEH_E2E_A", "VEH_E2E_B"],
        history_hours=TELEMATICS_HISTORY_HOURS,
        source_from=plan_source_from,
        source_to=plan_source_to,
        algorithm="lpcmci",
    )

    window_events = {
        kwargs["vehicle_id"]: kwargs for event, kwargs in events if event == "telematics_vehicle_analysis_window"
    }
    assert set(window_events) == {"VEH_E2E_A", "VEH_E2E_B"}

    a_fields = window_events["VEH_E2E_A"]
    assert a_fields["domain"] == "telematics"
    assert a_fields["domain_plan_source_from"] == plan_source_from.isoformat()
    assert a_fields["domain_plan_source_to"] == plan_source_to.isoformat()
    assert a_fields["vehicle_visible_to"] == plan_source_to.isoformat()
    assert a_fields["vehicle_analysis_to"] == plan_source_to.isoformat()
    assert a_fields["requested_history_hours"] == TELEMATICS_HISTORY_HOURS
    assert a_fields["raw_rows_loaded"] > 0

    b_fields = window_events["VEH_E2E_B"]
    assert b_fields["vehicle_visible_to"] == vehicle_b_latest.isoformat()
    assert b_fields["vehicle_analysis_to"] == vehicle_b_latest.isoformat()
    # The two vehicles legitimately got different analytical windows in the
    # same call.
    assert a_fields["vehicle_analysis_to"] != b_fields["vehicle_analysis_to"]

    # The persisted run's domain-level source envelope is the min/max
    # across the CORRECTED per-vehicle windows (unchanged field semantics:
    # it was always this envelope, never the literal plan bounds -- see
    # _source_window -- but it now correctly reflects vehicle B's earlier
    # true visibility instead of a truncated read of A's own history).
    assert result.source_to == plan_source_to
    assert result.source_from == vehicle_b_latest - timedelta(hours=TELEMATICS_HISTORY_HOURS)
