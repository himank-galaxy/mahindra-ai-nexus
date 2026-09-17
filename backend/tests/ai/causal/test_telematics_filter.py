"""Focused tests for telematics_filter.py's LPCMCI-mark handling.

Mirrors test_manufacturing_filter.py's coverage for the telematics domain:
min_lag gating, edge-mark/orientation propagation, and cross-vehicle
mark-agreement behavior (reported, not gated, by default).
"""

from __future__ import annotations

from app.ai.causal.pcmci_engine import CausalDiscoveryTest
from app.ai.causal.telematics_filter import (
    TelematicsFilterConfig,
    aggregate_telematics_stability,
    filter_telematics_tests,
)

SOURCE = "VEH-1||vehicle_speed_kph"
TARGET = "VEH-1||battery_temperature_c"

METADATA = {
    SOURCE: {"vehicle_id": "VEH-1"},
    TARGET: {"vehicle_id": "VEH-1"},
}


def _test(lag: int, *, mark: str = "-->", orientation: str = "DIRECTED", score: float = 0.5) -> CausalDiscoveryTest:
    return CausalDiscoveryTest(
        source=SOURCE,
        target=TARGET,
        lag=lag,
        score=score,
        p_value=0.001,
        edge_mark=mark,
        edge_orientation=orientation,
    )


def test_default_min_lag_rejects_lag_zero() -> None:
    tests = [_test(0)]
    try:
        filter_telematics_tests(tests, METADATA)
    except ValueError as exc:
        assert "lag" in str(exc)
    else:
        raise AssertionError("expected ValueError for lag=0 under default min_lag=1")


def test_min_lag_zero_admits_contemporaneous_tests() -> None:
    tests = [_test(0)]
    result = filter_telematics_tests(tests, METADATA, config=TelematicsFilterConfig(min_lag=0))
    assert result.accepted_edges
    assert result.accepted_edges[0].lag == 0


def test_bidirected_and_ambiguous_marks_pass_through_filtering_unaffected() -> None:
    tests = [
        _test(0, mark="<->", orientation="BIDIRECTED"),
        _test(1, mark="o-o", orientation="AMBIGUOUS"),
    ]
    result = filter_telematics_tests(tests, METADATA, config=TelematicsFilterConfig(min_lag=0))

    marks = {edge.lag: (edge.edge_mark, edge.edge_orientation) for edge in result.accepted_edges}
    assert marks[0] == ("<->", "BIDIRECTED")
    assert marks[1] == ("o-o", "AMBIGUOUS")


def test_stability_reports_consensus_mark_without_gating_by_default() -> None:
    metadata_veh1 = {
        "VEH-1||vehicle_speed_kph": {"vehicle_id": "VEH-1"},
        "VEH-1||battery_temperature_c": {"vehicle_id": "VEH-1"},
    }
    metadata_veh2 = {
        "VEH-2||vehicle_speed_kph": {"vehicle_id": "VEH-2"},
        "VEH-2||battery_temperature_c": {"vehicle_id": "VEH-2"},
    }

    config = TelematicsFilterConfig(
        min_recurrence_count=2,
        min_recurrence_fraction=0.5,
        min_sign_agreement=1.0,
        min_mark_agreement=0.0,
    )

    veh1_tests = [
        CausalDiscoveryTest(
            source="VEH-1||vehicle_speed_kph",
            target="VEH-1||battery_temperature_c",
            lag=1,
            score=0.5,
            p_value=0.001,
            edge_mark="-->",
            edge_orientation="DIRECTED",
        )
    ]
    veh2_tests = [
        CausalDiscoveryTest(
            source="VEH-2||vehicle_speed_kph",
            target="VEH-2||battery_temperature_c",
            lag=1,
            score=0.4,
            p_value=0.001,
            edge_mark="o-o",
            edge_orientation="AMBIGUOUS",
        )
    ]

    veh1_result = filter_telematics_tests(veh1_tests, metadata_veh1, config=config)
    veh2_result = filter_telematics_tests(veh2_tests, metadata_veh2, config=config)

    stability = aggregate_telematics_stability([veh1_result, veh2_result], config=config)

    assert len(stability.stable_edges) == 1
    stable_edge = stability.stable_edges[0]
    assert stable_edge.mark_agreement == 0.5
    assert stable_edge.consensus_edge_mark in ("-->", "o-o")


def test_min_mark_agreement_gates_stability_when_raised() -> None:
    metadata_veh1 = {
        "VEH-1||vehicle_speed_kph": {"vehicle_id": "VEH-1"},
        "VEH-1||battery_temperature_c": {"vehicle_id": "VEH-1"},
    }
    metadata_veh2 = {
        "VEH-2||vehicle_speed_kph": {"vehicle_id": "VEH-2"},
        "VEH-2||battery_temperature_c": {"vehicle_id": "VEH-2"},
    }

    config = TelematicsFilterConfig(
        min_recurrence_count=2,
        min_recurrence_fraction=0.5,
        min_sign_agreement=1.0,
        min_mark_agreement=1.0,
    )

    veh1_tests = [
        CausalDiscoveryTest(
            source="VEH-1||vehicle_speed_kph",
            target="VEH-1||battery_temperature_c",
            lag=1,
            score=0.5,
            p_value=0.001,
            edge_mark="-->",
            edge_orientation="DIRECTED",
        )
    ]
    veh2_tests = [
        CausalDiscoveryTest(
            source="VEH-2||vehicle_speed_kph",
            target="VEH-2||battery_temperature_c",
            lag=1,
            score=0.4,
            p_value=0.001,
            edge_mark="o-o",
            edge_orientation="AMBIGUOUS",
        )
    ]

    veh1_result = filter_telematics_tests(veh1_tests, metadata_veh1, config=config)
    veh2_result = filter_telematics_tests(veh2_tests, metadata_veh2, config=config)

    stability = aggregate_telematics_stability([veh1_result, veh2_result], config=config)

    assert stability.stable_edges == ()
