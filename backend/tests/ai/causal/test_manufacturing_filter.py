"""Focused tests for manufacturing_filter.py's LPCMCI-mark handling.

Covers what test_manufacturing_minute_pipeline.py does not: min_lag gating,
edge-mark/orientation propagation, and cross-machine mark-agreement
behavior (reported, not gated, by default).
"""

from __future__ import annotations

from app.ai.causal.manufacturing_filter import (
    ManufacturingFilterConfig,
    aggregate_manufacturing_stability,
    filter_manufacturing_tests,
)
from app.ai.causal.pcmci_engine import CausalDiscoveryTest

SOURCE = "MACHINE_1||machine_load"
TARGET = "MACHINE_1||power_kw"

METADATA = {
    SOURCE: {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
    TARGET: {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
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
        filter_manufacturing_tests(tests, METADATA)
    except ValueError as exc:
        assert "lag" in str(exc)
    else:
        raise AssertionError("expected ValueError for lag=0 under default min_lag=1")


def test_min_lag_zero_admits_contemporaneous_tests() -> None:
    tests = [_test(0)]
    result = filter_manufacturing_tests(tests, METADATA, config=ManufacturingFilterConfig(min_lag=0))
    assert result.accepted_edges
    assert result.accepted_edges[0].lag == 0


def test_bidirected_and_ambiguous_marks_pass_through_filtering_unaffected() -> None:
    tests = [
        _test(0, mark="<->", orientation="BIDIRECTED"),
        _test(1, mark="o-o", orientation="AMBIGUOUS"),
    ]
    result = filter_manufacturing_tests(tests, METADATA, config=ManufacturingFilterConfig(min_lag=0))

    marks = {edge.lag: (edge.edge_mark, edge.edge_orientation) for edge in result.accepted_edges}
    assert marks[0] == ("<->", "BIDIRECTED")
    assert marks[1] == ("o-o", "AMBIGUOUS")


def test_stability_reports_consensus_mark_and_agreement() -> None:
    machine_1_source = "MACHINE_1||machine_load"
    machine_1_target = "MACHINE_1||power_kw"
    machine_2_source = "MACHINE_2||machine_load"
    machine_2_target = "MACHINE_2||power_kw"

    metadata = {
        machine_1_source: {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
        machine_1_target: {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
        machine_2_source: {"machine_id": "MACHINE_2", "line_type": "ASSEMBLY"},
        machine_2_target: {"machine_id": "MACHINE_2", "line_type": "ASSEMBLY"},
    }

    config = ManufacturingFilterConfig(
        min_recurrence_count=2,
        min_recurrence_fraction=0.5,
        min_sign_agreement=1.0,
        min_mark_agreement=0.0,
    )

    machine_1_tests = [
        CausalDiscoveryTest(
            source=machine_1_source,
            target=machine_1_target,
            lag=1,
            score=0.5,
            p_value=0.001,
            edge_mark="-->",
            edge_orientation="DIRECTED",
        )
    ]
    machine_2_tests = [
        CausalDiscoveryTest(
            source=machine_2_source,
            target=machine_2_target,
            lag=1,
            score=0.4,
            p_value=0.001,
            edge_mark="o-o",
            edge_orientation="AMBIGUOUS",
        )
    ]

    machine_1_result = filter_manufacturing_tests(machine_1_tests, metadata, config=config)
    machine_2_result = filter_manufacturing_tests(machine_2_tests, metadata, config=config)

    stability = aggregate_manufacturing_stability([machine_1_result, machine_2_result], config=config)

    assert len(stability.stable_edges) == 1
    stable_edge = stability.stable_edges[0]

    # Mark disagreement between machines does NOT block stability by default
    # (min_mark_agreement=0.0) -- sign agreement is the only gate.
    assert stable_edge.mark_agreement == 0.5
    assert stable_edge.consensus_edge_mark in ("-->", "o-o")
    assert stable_edge.consensus_edge_orientation in ("DIRECTED", "AMBIGUOUS")


def test_min_mark_agreement_gates_stability_when_raised() -> None:
    metadata = {
        "MACHINE_1||machine_load": {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
        "MACHINE_1||power_kw": {"machine_id": "MACHINE_1", "line_type": "ASSEMBLY"},
        "MACHINE_2||machine_load": {"machine_id": "MACHINE_2", "line_type": "ASSEMBLY"},
        "MACHINE_2||power_kw": {"machine_id": "MACHINE_2", "line_type": "ASSEMBLY"},
    }

    config = ManufacturingFilterConfig(
        min_recurrence_count=2,
        min_recurrence_fraction=0.5,
        min_sign_agreement=1.0,
        min_mark_agreement=1.0,
    )

    machine_1_tests = [
        CausalDiscoveryTest(
            source="MACHINE_1||machine_load",
            target="MACHINE_1||power_kw",
            lag=1,
            score=0.5,
            p_value=0.001,
            edge_mark="-->",
            edge_orientation="DIRECTED",
        )
    ]
    machine_2_tests = [
        CausalDiscoveryTest(
            source="MACHINE_2||machine_load",
            target="MACHINE_2||power_kw",
            lag=1,
            score=0.4,
            p_value=0.001,
            edge_mark="o-o",
            edge_orientation="AMBIGUOUS",
        )
    ]

    machine_1_result = filter_manufacturing_tests(machine_1_tests, metadata, config=config)
    machine_2_result = filter_manufacturing_tests(machine_2_tests, metadata, config=config)

    stability = aggregate_manufacturing_stability([machine_1_result, machine_2_result], config=config)

    # Unanimous mark agreement required and not met (one "-->", one "o-o") --
    # the pair must be excluded when min_mark_agreement=1.0.
    assert stability.stable_edges == ()
