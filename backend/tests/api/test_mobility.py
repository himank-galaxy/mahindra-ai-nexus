"""Read API tests: Auto Mobility Causal Twin."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_graph_nodes_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/mobility-twin/graph")

    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == len(seed_data.CAUSAL_NODES)

    first, expected = body["nodes"][0], seed_data.CAUSAL_NODES[0]
    assert first["label"] == expected["label"]
    assert first["x"] == expected["x"]
    assert first["y"] == expected["y"]
    assert first["metric"] == expected["metric"]
    assert first["trend"] == expected["trend"]
    assert first["drivers"] == expected["drivers"]
    assert first["action"] == expected["action"]


async def test_graph_edges_are_label_pairs_matching_seed(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/mobility-twin/graph")).json()

    edges = [tuple(edge) for edge in body["edges"]]
    assert edges == seed_data.CAUSAL_EDGES


async def test_kpis_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/mobility-twin/kpis")

    assert response.status_code == 200
    assert response.json() == seed_data.MOBILITY_KPIS
