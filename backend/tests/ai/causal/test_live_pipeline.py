"""Regression tests for per-domain replay ingestion and cohort planning.

These cover the behaviours the live Warranty & Quality pipeline depends on and
that are easy to regress silently:

* each domain advances its own watermark against its own immutable source;
* a cursor that reaches the source maximum is a fact, not an error;
* the telematics cohort admits field-relevant vehicles on eligibility rather
  than on recency, and reports a factual reason for every exclusion;
* the manufacturing window contains the implicated production lineage;
* warning evaluation identity ignores the clock so unchanged evidence cannot
  mint duplicate evaluations.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest
from app.scheduler import causal_scheduler
from app.services import live_ingestion
from app.services.live_ingestion import (
    FIELD_CLOCK_DOMAINS,
    INGESTION_SOURCES,
    TIMESERIES_DOMAINS,
    _target_cursor,
)
from app.services.warranty_quality_early_warning import (
    ISSUE_TELEMATICS_FAMILIES,
    _telematics_eligibility_diagnostics,
)
from app.services.warranty_quality_evaluation import evaluation_signature

START = datetime(2026, 7, 27, 18, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Per-domain cursor advance
# ---------------------------------------------------------------------------


def test_cursor_advances_by_replayed_simulated_minutes() -> None:
    target = _target_cursor(
        previous_cursor=START,
        elapsed_seconds=60.0,
        replay_speed=60.0,
        source_to=START + timedelta(days=30),
    )
    assert target == START + timedelta(minutes=60)


def test_cursor_clamps_to_the_domain_source_maximum() -> None:
    source_to = START + timedelta(minutes=10)
    target = _target_cursor(
        previous_cursor=START,
        elapsed_seconds=600.0,
        replay_speed=60.0,
        source_to=source_to,
    )
    assert target == source_to, "a domain must never replay past its own source"


def test_cursor_does_not_move_when_no_time_elapsed() -> None:
    target = _target_cursor(
        previous_cursor=START,
        elapsed_seconds=0.0,
        replay_speed=60.0,
        source_to=START + timedelta(days=1),
    )
    assert target == START


def test_manufacturing_is_not_a_field_clock_domain() -> None:
    # Production observations precede field telemetry, so manufacturing must
    # never drag the shared business clock back into the production past.
    assert "manufacturing" not in FIELD_CLOCK_DOMAINS
    assert set(FIELD_CLOCK_DOMAINS) == {"telematics", "service", "warranty"}


def test_every_ingestion_source_is_declared_with_its_time_column() -> None:
    for domain, source in INGESTION_SOURCES.items():
        assert source["source_table"], domain
        assert source["time_column"], domain
    assert set(INGESTION_SOURCES) >= TIMESERIES_DOMAINS


def test_inserts_are_conflict_tolerant_so_a_replayed_minute_is_a_no_op() -> None:
    body = inspect.getsource(live_ingestion._insert_due_rows)
    assert "ON CONFLICT DO NOTHING" in body


def test_a_failed_domain_tick_does_not_advance_its_checkpoint() -> None:
    body = inspect.getsource(live_ingestion.ingest_domain_tick)
    failure_handler = body[body.index("except Exception") :]
    # The failure path may record status and the error, but must never move
    # the watermark: a rolled-back minute has to be replayed in full.
    assert "state.replay_cursor" not in failure_handler
    assert "rows_ingested_total" not in failure_handler
    assert "await session.rollback()" in failure_handler
    assert body.count("state.replay_cursor = target_cursor") == 1


# ---------------------------------------------------------------------------
# Telematics cohort eligibility
# ---------------------------------------------------------------------------


class _Run:
    def __init__(self, vehicle_ids: list[str]) -> None:
        self.vehicle_ids = vehicle_ids


class _Edge:
    def __init__(self, source: str, target: str, vehicles: list[str]) -> None:
        self.source_metric = source
        self.target_metric = target
        self.vehicle_ids = vehicles


def test_cohort_planning_is_eligibility_based_not_recency_based() -> None:
    source = inspect.getsource(causal_scheduler.build_telematics_source_plan)
    # The old planner required telemetry within the last ten minutes, which
    # silently excluded every warning vehicle that had stopped reporting.
    assert "minutes=10" not in source
    for reason in (
        "not_delivered",
        "insufficient_raw_history",
        "insufficient_analytical_rows",
        "outside_source_window",
    ):
        assert reason in source, f"missing factual exclusion reason: {reason}"


def test_field_relevant_vehicles_are_derived_not_hard_coded() -> None:
    source = inspect.getsource(causal_scheduler._field_relevant_vehicles)
    assert "VEHUNIT_SYN" not in source, "warning vehicle ids must never be hard-coded"
    assert "issue_category" in source


def test_diagnostics_report_the_planner_reason_for_an_excluded_vehicle() -> None:
    diagnostics = _telematics_eligibility_diagnostics(
        "TYRE_VIBRATION",
        {"VEHUNIT_A"},
        _Run(["VEHUNIT_B"]),
        [_Edge("vehicle_vibration_mm_s", "steering_torque_nm", ["VEHUNIT_B"])],
        {"VEHUNIT_A": "insufficient_raw_history"},
    )
    assert diagnostics["ineligibility_reasons"] == {"VEHUNIT_A": "insufficient_raw_history"}
    assert diagnostics["warning_vehicles_in_completed_causal_cohort"] == []


def test_diagnostics_distinguish_an_unsupported_metric_family() -> None:
    diagnostics = _telematics_eligibility_diagnostics(
        "INTERIOR_RATTLE",
        {"VEHUNIT_A"},
        _Run(["VEHUNIT_A"]),
        [_Edge("vehicle_vibration_mm_s", "steering_torque_nm", ["VEHUNIT_A"])],
        {},
    )
    # The vehicle IS in the cohort; the issue simply has no telematics family.
    assert diagnostics["ineligibility_reasons"] == {"VEHUNIT_A": "no_supported_metric_family"}
    assert ISSUE_TELEMATICS_FAMILIES["INTERIOR_RATTLE"] == frozenset()


def test_a_supported_vehicle_produces_no_ineligibility_reason() -> None:
    diagnostics = _telematics_eligibility_diagnostics(
        "TYRE_VIBRATION",
        {"VEHUNIT_A"},
        _Run(["VEHUNIT_A"]),
        [_Edge("vehicle_vibration_mm_s", "steering_torque_nm", ["VEHUNIT_A"])],
        {},
    )
    assert diagnostics["ineligibility_reasons"] == {}
    assert diagnostics["vehicles_with_supported_metric_intersection"] == ["VEHUNIT_A"]


# ---------------------------------------------------------------------------
# Manufacturing lineage anchoring
# ---------------------------------------------------------------------------


def test_manufacturing_window_contains_the_implicated_production() -> None:
    source = inspect.getsource(causal_scheduler.build_manufacturing_source_plan)
    # The window starts where the implicated batches were built and spans the
    # validated rolling history, rather than tracking the replay clock.
    assert "lineage_from + timedelta(hours=MANUFACTURING_HISTORY_HOURS)" in source
    assert "analysis_end = max(analysis_end, lineage_to)" in source


def test_manufacturing_rolling_history_matches_the_validated_contract() -> None:
    assert causal_scheduler.MANUFACTURING_HISTORY_HOURS == 72.0
    assert causal_scheduler.MANUFACTURING_ANALYSIS_MINUTES == 15


def test_telematics_rolling_history_matches_the_validated_contract() -> None:
    assert causal_scheduler.TELEMATICS_HISTORY_HOURS == 168.0
    assert causal_scheduler.TELEMATICS_ANALYSIS_MINUTES == 5


def test_domains_are_serviced_independently() -> None:
    source = inspect.getsource(causal_scheduler.run_scheduler_once)
    # A previous revision reassigned the loop variable, which silently skipped
    # telematics whenever the scheduler was asked for every domain.
    assert "requested = [name for name in DOMAIN_RUNNERS" in source
    assert set(causal_scheduler.DOMAIN_RUNNERS) == {"manufacturing", "telematics"}


def test_a_busy_domain_records_one_coalesced_target_rather_than_a_queue() -> None:
    source = inspect.getsource(causal_scheduler._service_domain)
    assert "pending_state.pending_refresh = True" in source
    assert "causal_run_coalesced" in source
    assert "causal_run_coalesced_followup" in source


# ---------------------------------------------------------------------------
# Warning evaluation identity
# ---------------------------------------------------------------------------


def test_evaluation_identity_ignores_the_clock() -> None:
    first = evaluation_signature(
        manufacturing_signature="mfg",
        telematics_signature="tel",
        field_evidence_signature="field",
    )
    second = evaluation_signature(
        manufacturing_signature="mfg",
        telematics_signature="tel",
        field_evidence_signature="field",
    )
    assert first == second, "identical evidence must not mint a second evaluation"


@pytest.mark.parametrize(
    "changed",
    [
        {"manufacturing_signature": "mfg-2"},
        {"telematics_signature": "tel-2"},
        {"field_evidence_signature": "field-2"},
    ],
)
def test_evaluation_identity_moves_when_evidence_moves(changed: dict[str, str]) -> None:
    baseline = {
        "manufacturing_signature": "mfg",
        "telematics_signature": "tel",
        "field_evidence_signature": "field",
    }
    assert evaluation_signature(**baseline) != evaluation_signature(**{**baseline, **changed})
