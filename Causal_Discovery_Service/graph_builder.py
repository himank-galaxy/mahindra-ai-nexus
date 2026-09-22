"""
Converts LPCMCI's output matrices into a JSON-friendly graph of nodes and
edges, per IMPLEMENTATION_PLAN.md section 11.

Verified against the installed tigramite package's actual LPCMCI
implementation (tigramite.lpcmci.LPCMCI._dict2graph):

    graph      : numpy array, shape (N, N, tau_max + 1), dtype 'U3'
                 (3-character edge-mark strings, e.g. "-->", "<->", "o-o",
                 or "" for no edge)
    val_matrix : numpy array, shape (N, N, tau_max + 1), float
    p_matrix   : numpy array, shape (N, N, tau_max + 1), float

This module has nothing to convert until lpcmci_runner.run_lpcmci() is
actually invoked (not in this phase) - it is implemented and unit-testable
against synthetic matrices in the meantime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    var_name: str
    entity_id: str
    metric: str
    domain: str


@dataclass
class GraphEdge:
    source: str
    target: str
    lag: int
    edge_mark: str
    strength: float
    p_value: float


@dataclass
class CausalGraph:
    domain: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


def _split_var_name(var_name: str) -> tuple[str, str]:
    """
    "MACHINE_SYN_014||machine_temperature_c" -> ("MACHINE_SYN_014", "machine_temperature_c")
    """

    if "||" not in var_name:
        return var_name, var_name
    entity_id, metric = var_name.split("||", 1)
    return entity_id, metric


def build_causal_graph(
    domain: str,
    var_names: list[str],
    graph: Any,
    val_matrix: Any,
    p_matrix: Any,
) -> CausalGraph:
    """
    Walk the (N, N, tau_max+1) matrices and emit one GraphEdge per non-empty
    edge mark, plus one GraphNode per variable - mirrors
    docs/README_LPCMCI_Causal_Discovery.md sections 15-16 and 24.
    """

    nodes = [
        GraphNode(
            var_name=var_name,
            entity_id=_split_var_name(var_name)[0],
            metric=_split_var_name(var_name)[1],
            domain=domain,
        )
        for var_name in var_names
    ]

    edges: list[GraphEdge] = []
    n_vars = len(var_names)
    n_lags = graph.shape[2] if hasattr(graph, "shape") else 0

    for source_index in range(n_vars):
        for target_index in range(n_vars):
            for lag in range(n_lags):
                edge_mark = graph[source_index, target_index, lag]
                if not edge_mark:
                    continue

                edges.append(
                    GraphEdge(
                        source=var_names[source_index],
                        target=var_names[target_index],
                        lag=lag,
                        edge_mark=str(edge_mark),
                        strength=float(
                            val_matrix[source_index, target_index, lag]
                        ),
                        p_value=float(
                            p_matrix[source_index, target_index, lag]
                        ),
                    )
                )

    return CausalGraph(domain=domain, nodes=nodes, edges=edges)


def causal_graph_to_dict(graph: CausalGraph) -> dict:
    """JSON-serializable representation, matching the shape suggested in
    docs/README_LPCMCI_Causal_Discovery.md section 24."""

    return {
        "domain": graph.domain,
        "nodes": [
            {
                "var_name": node.var_name,
                "entity_id": node.entity_id,
                "metric": node.metric,
                "domain": node.domain,
            }
            for node in graph.nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "lag": edge.lag,
                "edge_mark": edge.edge_mark,
                "strength": edge.strength,
                "p_value": edge.p_value,
            }
            for edge in graph.edges
        ],
    }
