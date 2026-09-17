"""Dynamic mobility feature selection, continuous sampling, discovery and cache behavior."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import numpy as np
import pytest
from app.ai.causal.data_loader import CausalInput, assemble_panel
from app.ai.causal.graph_builder import NODE_HEIGHT, NODE_WIDTH, collapse_parallel_edges, layout_nodes
from app.ai.causal.mobility_engine import MobilityEdge, adjusted_pvalues, discover_edges
from app.ai.causal.mobility_features import aggregate_feature, discover_features, feature_metadata, trend_tone
from app.services import mobility_causal_cache as cache
from sqlalchemy import Column, Float, Integer, MetaData, String, Table


def test_feature_discovery_follows_schema_and_excludes_identifiers():
    table = Table(
        "source",
        MetaData(),
        Column("region_id", Integer, primary_key=True),
        Column("lead_count", Integer),
        Column("new_service_measure", Float),
        Column("vehicle_id", Integer),
        Column("data_origin", String),
        Column("true_cause", Float),
    )
    features = discover_features(table)
    assert {feature.key for feature in features} == {"lead_count", "new_service_measure"}
    assert next(feature for feature in features if feature.key == "new_service_measure").polarity == "neutral"
    new_column = Column("repair_duration_hours", Float)
    table.append_column(new_column)
    assert "repair_duration_hours" in {feature.key for feature in discover_features(table)}


def test_aggregation_and_business_direction():
    feature = feature_metadata("avg_delivery_delay_days", {"avg_delivery_delay_days", "delayed_delivery_count"})
    rows = [
        {"avg_delivery_delay_days": 2, "delayed_delivery_count": 3},
        {"avg_delivery_delay_days": 6, "delayed_delivery_count": 1},
    ]
    assert aggregate_feature(feature, rows) == 3
    assert trend_tone(feature, 3, 2) == "danger"
    assert trend_tone(feature, 2, 3) == "success"
    assert feature_metadata("booking_value_inr", set()).label == "Booking Value"


def sample_rows():
    start = datetime(2026, 7, 1, 11, 59, tzinfo=UTC)
    keys = ("lead_count", "new_service_measure", "constant_count", "missing_count")
    rows = [
        {
            "window_start": start + timedelta(hours=12 * index),
            "region_id": region,
            "lead_count": index + 1,
            "new_service_measure": index * index + 1,
            "constant_count": 5,
            "missing_count": None if index == 4 else 2,
            "data_origin": "SYNTHETIC",
        }
        for index in range(30)
        if index != 15
        for region in ("east", "west")
    ]
    return rows, tuple(feature_metadata(key, set(keys)) for key in keys)


def test_missing_periods_split_panels_and_constant_features_are_explained():
    rows, features = sample_rows()
    panel = assemble_panel(
        rows,
        features,
        stride_hours=12,
        tau_max=2,
        min_observations=20,
        source_latest_at=rows[-1]["window_start"],
        expected_regions={"east", "west"},
    )
    assert panel.segments == ((0, 15), (15, 29))
    assert panel.metrics == ("lead_count", "new_service_measure")
    assert set(panel.excluded) == {"constant_count", "missing_count"}
    assert any("gaps" in warning for warning in panel.warnings)
    assert panel.dates[15] - panel.dates[14] == timedelta(hours=24)
    for start, end in panel.segments:
        assert all(
            b - a == timedelta(hours=12)
            for a, b in zip(panel.dates[start : end - 1], panel.dates[start + 1 : end], strict=True)
        )


def test_partial_regions_and_short_history_are_not_silently_used():
    rows, features = sample_rows()
    rows = [row for row in rows if row["region_id"] == "east"]
    with pytest.raises(ValueError, match="found 0"):
        assemble_panel(
            rows,
            features,
            stride_hours=12,
            tau_max=2,
            min_observations=20,
            source_latest_at=None,
            expected_regions={"east", "west"},
        )


def test_fdr_uses_complete_hypothesis_family():
    np.testing.assert_allclose(adjusted_pvalues(np.array([0.01, 0.04, 0.03, 0.9])), [0.04, 0.05333333, 0.05333333, 0.9])


def test_parallel_lags_collapse_to_best_adjusted_evidence():
    edges = [
        MobilityEdge("lead_count", "followup_completed_count", 1, 0.58, 0.001, 0.02),
        MobilityEdge("lead_count", "followup_completed_count", 2, 0.70, 0.002, 0.04),
        MobilityEdge("followup_completed_count", "lead_count", 1, -0.4, 0.005, 0.03),
    ]
    collapsed = collapse_parallel_edges(edges)
    assert {(edge.source, edge.target, edge.lag) for edge in collapsed} == {
        ("lead_count", "followup_completed_count", 1),
        ("followup_completed_count", "lead_count", 1),
    }


def causal_panel():
    rng = np.random.default_rng(41)
    x = rng.normal(size=500)
    y = np.roll(x, 1) * -0.9 + rng.normal(scale=0.2, size=500)
    values = np.column_stack((x, y, rng.normal(size=500)))
    keys = ("new_warranty_measure", "lead_count", "independent_service_measure")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    dates = tuple(start + timedelta(hours=12 * index + (120 if index >= 250 else 0)) for index in range(500))
    return CausalInput(
        dates,
        keys,
        values,
        tuple(feature_metadata(key, set(keys)) for key in keys),
        ((0, 250), (250, 500)),
        {},
        (),
        dates[-1],
        ("SYNTHETIC",),
        dates,
    )


def test_real_pcmci_finds_unrestricted_direction_across_separate_segments():
    edges = discover_edges(causal_panel(), tau_max=2, alpha=0.05)
    edge = next(
        edge
        for edge in edges
        if edge.source == "new_warranty_measure" and edge.target == "lead_count" and edge.lag == 1
    )
    assert edge.score < -0.8
    assert edge.q_value <= 0.05
    assert all(edge.source != edge.target and edge.lag > 0 for edge in edges)


def test_layout_supports_cycles_disconnected_nodes_and_new_names():
    keys = ["new_a", "new_b", "new_c", "isolated"]
    edges = [
        MobilityEdge("new_a", "new_b", 1, 0.8, 0.001, 0.01),
        MobilityEdge("new_b", "new_a", 1, 0.7, 0.001, 0.01),
        MobilityEdge("new_b", "new_c", 1, 0.6, 0.001, 0.01),
    ]
    positions = layout_nodes(keys, edges)
    assert set(positions) == {"new_a", "new_b", "new_c"}
    assert positions["new_c"][0] > positions["new_a"][0]
    for a in positions:
        for b in positions:
            if a != b:
                ax, ay = positions[a]
                bx, by = positions[b]
                assert abs(ax - bx) >= NODE_WIDTH or abs(ay - by) >= NODE_HEIGHT
    assert layout_nodes(keys, edges) == positions
    assert layout_nodes(keys, []) == {}


async def test_cache_recomputes_for_changed_data_not_wall_clock(monkeypatch):
    source = causal_panel()
    loader = AsyncMock(return_value=source)
    monkeypatch.setattr(cache, "load_daily_causal_input", loader)
    session = AsyncMock()
    monkeypatch.setattr(cache, "get_session_factory", lambda: lambda: session)
    calls = []

    def discovery(*args, **kwargs):
        calls.append(1)
        return ()

    monkeypatch.setattr(cache, "discover_edges", discovery)
    monkeypatch.setattr(cache, "_current", None)
    monkeypatch.setattr(cache, "_prior", None)
    monkeypatch.setattr(cache, "_refresh_lock", asyncio.Lock())
    first, duplicate = await asyncio.gather(cache.refresh(), cache.refresh())
    assert first is duplicate
    assert len(calls) == 1
    assert cache._prior is None
    # Live minute arrivals do not alter a closed sampled panel.
    loader.return_value = replace(source, source_latest_at=source.source_latest_at + timedelta(minutes=1))
    assert await cache.refresh() is first
    assert len(calls) == 1
    values = source.values.copy()
    values[-1, 0] += 10
    loader.return_value = replace(source, values=values)
    second = await cache.refresh()
    assert second.snapshot_id != first.snapshot_id
    assert cache._prior is first
    assert len(calls) == 2
    loader.side_effect = ValueError("Not enough complete periods")
    with pytest.raises(Exception, match="Not enough complete periods"):
        await cache.refresh()
    assert await cache.get_or_refresh() is second
    assert cache.snapshot_metadata(second).status == "stale"
