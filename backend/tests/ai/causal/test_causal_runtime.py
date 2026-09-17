from datetime import UTC, datetime, timedelta

from app.services.causal_runtime import calculate_replay_advance, graph_delta, stable_source_signature


def stamp(hour: int) -> datetime:
    return datetime(2026, 8, 21, hour, 0, tzinfo=UTC)


def test_replay_clock_advances_from_persistent_elapsed_time() -> None:
    result = calculate_replay_advance(
        simulation_as_of=stamp(0),
        last_tick_at=stamp(1),
        now=stamp(1) + timedelta(minutes=2),
        replay_speed=60.0,
        paused=False,
        replay_end=stamp(12),
        tick_interval_seconds=60,
    )

    assert result.ticked is True
    assert result.simulation_as_of == stamp(2)
    assert result.last_tick_at == stamp(1) + timedelta(minutes=2)


def test_replay_clock_is_pause_safe_and_clamped() -> None:
    paused = calculate_replay_advance(
        simulation_as_of=stamp(0),
        last_tick_at=stamp(1),
        now=stamp(2),
        replay_speed=60.0,
        paused=True,
        replay_end=stamp(12),
    )
    assert paused.simulation_as_of == stamp(0)
    assert paused.ticked is False
    assert paused.last_tick_at == stamp(2)

    clamped = calculate_replay_advance(
        simulation_as_of=stamp(11),
        last_tick_at=stamp(1),
        now=stamp(2),
        replay_speed=60.0,
        paused=False,
        replay_end=stamp(12),
    )
    assert clamped.simulation_as_of == stamp(12)


def test_replay_clock_does_not_tick_before_configured_interval() -> None:
    result = calculate_replay_advance(
        simulation_as_of=stamp(0),
        last_tick_at=stamp(1),
        now=stamp(1) + timedelta(seconds=59),
        replay_speed=60.0,
        paused=False,
        replay_end=stamp(12),
        tick_interval_seconds=60,
    )
    assert result.ticked is False
    assert result.simulation_as_of == stamp(0)


def test_graph_delta_tracks_structural_and_strength_changes() -> None:
    previous = [
        {"source_metric": "a", "target_metric": "b", "scope": "machine", "consensus_sign": "+", "mean_abs_score": 0.2},
        {"source_metric": "c", "target_metric": "d", "scope": "machine", "consensus_sign": "+", "mean_abs_score": 0.5},
    ]
    current = [
        {"source_metric": "a", "target_metric": "b", "scope": "machine", "consensus_sign": "+", "mean_abs_score": 0.3},
        {"source_metric": "c", "target_metric": "d", "scope": "machine", "consensus_sign": "-", "mean_abs_score": 0.4},
        {"source_metric": "e", "target_metric": "f", "scope": "machine", "consensus_sign": "+", "mean_abs_score": 0.1},
    ]
    assert graph_delta(current, previous) == {
        "new_edges": 1,
        "removed_edges": 0,
        "unchanged_edges": 2,
        "strengthened_edges": 1,
        "weakened_edges": 1,
        "sign_changed_edges": 1,
        "mark_changed_edges": 0,
    }


def test_source_signature_is_order_independent() -> None:
    assert stable_source_signature({"vehicles": ["A", "B"], "to": "x"}) == stable_source_signature(
        {"to": "x", "vehicles": ["A", "B"]}
    )
