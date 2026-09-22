"""Mobility API regression tests using computed evidence, never presentation seeds."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.ai.causal.data_loader import CausalInput
from app.ai.causal.mobility_engine import MobilityEdge
from app.ai.causal.mobility_features import feature_metadata
from app.ai.llm.provider import RuleBasedProvider
from app.api.deps import get_db
from app.api.v1.mobility import router
from app.core.errors import register_exception_handlers
from app.services import mobility_causal_cache as cache
from app.services import mobility_copilot as copilot
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def make_state(version="first"):
    keys = ("lead_count", "avg_delivery_delay_days", "new_service_measure")
    values = np.column_stack((np.arange(100) + 10, np.arange(100) / 10 + 1, np.arange(100) * 2 + 1))
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    dates = tuple(end - timedelta(hours=12 * (99 - index)) for index in range(100))
    source = CausalInput(
        dates,
        keys,
        values,
        tuple(feature_metadata(key, set(keys)) for key in keys),
        ((0, 100),),
        {},
        ("Synthetic dataset",),
        end,
        ("SYNTHETIC",),
        dates,
    )
    return cache.MobilityCausalState(
        (
            MobilityEdge("new_service_measure", "lead_count", 1, -0.8, 0.001, 0.01),
            MobilityEdge("new_service_measure", "lead_count", 2, -0.6, 0.002, 0.02),
        ),
        source,
        end,
        version,
        12,
        2,
        0.05,
    )


@pytest.fixture
async def mobility_client(monkeypatch):
    monkeypatch.setattr(cache, "_current", make_state())
    monkeypatch.setattr(cache, "_prior", None)
    monkeypatch.setattr(cache, "_last_error", None)
    monkeypatch.setattr(cache, "_checked_at", None)
    monkeypatch.setattr(cache, "_source_latest_at", None)
    monkeypatch.setattr(copilot, "get_llm_provider", lambda _settings: RuleBasedProvider())
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/mobility-twin")
    register_exception_handlers(app)

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_dynamic_graph_keeps_connected_features_and_lag_evidence(mobility_client):
    response = await mobility_client.get("/api/v1/mobility-twin/graph")
    assert response.status_code == 200
    graph = response.json()
    assert {node["metric_key"] for node in graph["nodes"]} == {"lead_count", "new_service_measure"}
    assert graph["metadata"]["connected_measure_count"] == 2
    assert graph["metadata"]["hidden_isolated_measure_count"] == 1
    assert graph["metadata"]["snapshot_id"] == "first"
    assert len(graph["edges"]) == 1  # compatibility pairs are deduplicated
    assert len(graph["edge_details"]) == 1  # parallel lags collapse to one displayed arrow
    assert {edge["lag_minutes"] for edge in graph["edge_details"]} == {720}
    assert all(edge["source"] == "new_service_measure" for edge in graph["edge_details"])
    assert graph["kpis"] == (await mobility_client.get("/api/v1/mobility-twin/kpis")).json()
    assert "avg_delivery_delay_days" not in {node["metric_key"] for node in graph["nodes"]}
    assert graph["width"] > max(node["x"] for node in graph["nodes"])


async def test_detail_is_pinned_to_displayed_snapshot(mobility_client, monkeypatch):
    old = cache._current
    newer_values = old.values.copy()
    newer_values[-1, 0] = 999
    monkeypatch.setattr(cache, "_prior", old)
    monkeypatch.setattr(
        cache, "_current", replace(old, snapshot_id="second", source=replace(old.source, values=newer_values))
    )
    response = await mobility_client.get("/api/v1/mobility-twin/nodes/lead_count?snapshot_id=first")
    detail = response.json()
    assert response.status_code == 200
    assert detail["snapshot_id"] == "first"
    assert detail["current_value"] == 109
    assert len(detail["top_drivers"]) == 1
    assert "New Service Measure" in detail["recommended_action"]
    assert detail["top_drivers"][0]["q_value"] == 0.01
    assert (await mobility_client.get("/api/v1/mobility-twin/nodes/lead_count?snapshot_id=expired")).status_code == 409
    assert (await mobility_client.get("/api/v1/mobility-twin/nodes/missing?snapshot_id=second")).status_code == 404


async def test_failures_expose_staleness_and_initial_unavailability(mobility_client, monkeypatch):
    monkeypatch.setattr(cache, "_last_error", "Waiting for complete history")
    graph = (await mobility_client.get("/api/v1/mobility-twin/graph")).json()
    assert graph["metadata"]["status"] == "stale"
    assert graph["metadata"]["last_error"] == "Waiting for complete history"
    monkeypatch.setattr(cache, "_current", None)

    async def fail_refresh():
        from app.core.errors import AppError

        raise AppError("Need more usable observations", code="mobility_analysis_unavailable", status_code=503)

    monkeypatch.setattr(cache, "refresh", fail_refresh)
    response = await mobility_client.get("/api/v1/mobility-twin/graph")
    assert response.status_code == 503
    assert response.json()["detail"] == "Need more usable observations"


async def test_zero_baseline_is_not_reported_as_zero_change(mobility_client, monkeypatch):
    state = cache._current
    values = state.values.copy()
    values[-2, 0] = 0
    monkeypatch.setattr(cache, "_current", replace(state, source=replace(state.source, values=values)))
    detail = (await mobility_client.get("/api/v1/mobility-twin/nodes/lead_count")).json()
    assert detail["trend_pct"] is None


async def test_copilot_explains_only_the_current_visible_graph(mobility_client):
    response = await mobility_client.post(
        "/api/v1/mobility-twin/copilot/explain",
        json={
            "snapshot_id": "first",
            "selected_metric": "lead_count",
            "view_context": {
                "domain": "All Measures",
                "focus": True,
                "visible_metrics": ["new_service_measure", "lead_count"],
            },
        },
    )
    assert response.status_code == 200
    explanation = response.json()["reply"]
    assert "### 🔍 What's Happening" in explanation
    assert "### 🔗 Cause-Effect Chain" in explanation
    assert "### Each Important Node Explained" in explanation
    assert "### 🔎 Key Drivers" in explanation
    assert "### ⚠️ What Could Happen" in explanation
    assert "### 🛠️ Recommended Actions" in explanation
    assert "### 📊 How to Read This Graph" in explanation
    assert "New Service Measure → Lead Count" in explanation
    assert "strength 0.80" in explanation
    assert "12 hours" in explanation
    assert "Lead Count is currently 109" in explanation
    assert "Average Delivery Delay" not in explanation
    assert "new_service_measure" not in explanation
    assert "synthetic" not in explanation.lower()
    assert "pcmci" not in explanation.lower()


async def test_copilot_overview_covers_every_disconnected_group_and_selection_focuses_one(mobility_client, monkeypatch):
    state = make_state()
    extra = ("finance_application_count", "finance_approved_count")
    keys = state.source.metrics + extra
    values = np.column_stack((state.values, np.arange(100) + 2, np.arange(100) + 1))
    source = replace(
        state.source,
        metrics=keys,
        values=values,
        features=tuple(feature_metadata(key, set(keys)) for key in keys),
    )
    second_edge = MobilityEdge(extra[0], extra[1], 1, 0.7, 0.001, 0.01)
    monkeypatch.setattr(cache, "_current", replace(state, source=source, edges=state.edges + (second_edge,)))

    view = {
        "domain": "All Measures",
        "focus": False,
        "visible_metrics": [
            "new_service_measure",
            "lead_count",
            *extra,
        ],
    }
    overview = (
        await mobility_client.post(
            "/api/v1/mobility-twin/copilot/explain",
            json={"snapshot_id": "first", "view_context": view},
        )
    ).json()["reply"]
    assert "2 connected group(s)" in overview
    assert "No discovered relationship joins these groups" in overview
    assert "New Service Measure → Lead Count" in overview
    assert "Finance Application Count → Finance Approved Count" in overview
    assert "Roots (no incoming arrows)" in overview
    assert "Terminal outcomes (no outgoing arrows)" in overview
    assert "No measure is selected" in overview
    assert "selected target" not in overview.lower()
    assert "Average Delivery Delay" not in overview

    focused = (
        await mobility_client.post(
            "/api/v1/mobility-twin/copilot/explain",
            json={"snapshot_id": "first", "selected_metric": "lead_count", "view_context": view},
        )
    ).json()["reply"]
    assert "Lead Count is currently" in focused
    assert "other group(s) have no discovered link" in focused
    assert "Finance Application Count" not in focused


async def test_copilot_rejects_an_ungrounded_generated_explanation(mobility_client, monkeypatch):
    class UngroundedProvider:
        async def complete(self, _prompt):
            return (
                "### 🔍 What's Happening\nInvented Inventory Pressure is driving everything.\n"
                "### 🔗 Cause-Effect Chain\nInvented Inventory Pressure → Lead Count\n"
                "### Each Important Node Explained\nInvented Inventory Pressure\n"
                "### 🔎 Key Drivers\nInvented Inventory Pressure\n"
                "### ⚠️ What Could Happen\nRevenue will fall.\n"
                "### 🛠️ Recommended Actions\nChange inventory immediately.\n"
                "### 📊 How to Read This Graph\nFollow the arrows."
            )

    monkeypatch.setattr(copilot, "get_llm_provider", lambda _settings: UngroundedProvider())
    response = await mobility_client.post(
        "/api/v1/mobility-twin/copilot/explain",
        json={
            "snapshot_id": "first",
            "selected_metric": "lead_count",
            "view_context": {
                "domain": "All Measures",
                "focus": True,
                "visible_metrics": ["new_service_measure", "lead_count"],
            },
        },
    )
    assert response.status_code == 200
    explanation = response.json()["reply"]
    assert "Invented Inventory Pressure" not in explanation
    assert "New Service Measure → Lead Count" in explanation
