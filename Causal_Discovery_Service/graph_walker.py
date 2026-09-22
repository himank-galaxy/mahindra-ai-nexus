"""
Classifies every node in a CausalGraph as ROOT_CANDIDATE / UPSTREAM /
TARGET / DOWNSTREAM / UNCERTAIN / UNRELATED, relative to one chosen target
node - the piece docs/README_Predictive_Early_Warning_with_LPCMCI.md
describes in sections 19-24.

This is a NEW, additive module. It does not change graph_builder.py or any
other existing file in this service.

Direction handling (deliberately conservative): only edges with a fully
resolved edge mark ("-->" or "<--") are used to walk upstream/downstream.
Marks with any uncertainty ("<->", "o-o", "o->", "<-o", ...) are reported
as associated with the target but NOT placed at a specific hop distance,
per the README's own guidance (section 27) to preserve rather than
collapse that uncertainty - a "<->" edge may reflect a hidden common cause
rather than a direct one, so treating it as confidently upstream/downstream
would overstate what LPCMCI actually found.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from graph_builder import CausalGraph

FORWARD_MARK = "-->"  # source causes target
BACKWARD_MARK = "<--"  # target causes source (i.e. edge really points source <- target)


@dataclass
class NodeClassification:
    var_name: str
    role: str  # TARGET | ROOT_CANDIDATE | UPSTREAM | DOWNSTREAM | UNCERTAIN_LINK | UNRELATED
    hops: int | None  # None for TARGET, ROOT_CANDIDATE with no distance concept, and UNRELATED


def _bfs_hops(adjacency: dict[str, set[str]], start: str) -> dict[str, int]:
    """
    BFS from `start` following `adjacency` edges. Returns {node: hop_count}
    for every node reachable from start (start itself is not included).
    """

    hops: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    visited = {start}

    while queue:
        node, distance = queue.popleft()
        for neighbour in adjacency.get(node, ()):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            hops[neighbour] = distance + 1
            queue.append((neighbour, distance + 1))

    return hops


def classify_graph_around_target(
    graph: CausalGraph, target_var_name: str
) -> list[NodeClassification]:
    """
    Walk the graph's directed edges backward and forward from
    target_var_name, per IMPLEMENTATION_PLAN.md / the README's
    root-cause-candidate / upstream / target / downstream model.
    """

    causes: dict[str, set[str]] = defaultdict(set)  # causes[A] = {B, ...} means A -> B (confident)
    uncertain_partners: dict[str, set[str]] = defaultdict(set)

    for edge in graph.edges:
        if edge.source == edge.target:
            continue  # self-loops are not part of the cross-variable walk

        if edge.edge_mark == FORWARD_MARK:
            causes[edge.source].add(edge.target)
        elif edge.edge_mark == BACKWARD_MARK:
            causes[edge.target].add(edge.source)
        else:
            uncertain_partners[edge.source].add(edge.target)
            uncertain_partners[edge.target].add(edge.source)

    reverse_causes: dict[str, set[str]] = defaultdict(set)
    for source, targets in causes.items():
        for target in targets:
            reverse_causes[target].add(source)

    upstream_hops = _bfs_hops(reverse_causes, target_var_name)
    downstream_hops = _bfs_hops(causes, target_var_name)

    results: list[NodeClassification] = []
    classified: set[str] = set()

    for node in graph.nodes:
        var_name = node.var_name

        if var_name == target_var_name:
            results.append(NodeClassification(var_name, "TARGET", None))
            classified.add(var_name)
            continue

        if var_name in upstream_hops:
            has_incoming_confident_edge = bool(reverse_causes.get(var_name))
            role = "ROOT_CANDIDATE" if not has_incoming_confident_edge else "UPSTREAM"
            results.append(NodeClassification(var_name, role, upstream_hops[var_name]))
            classified.add(var_name)
            continue

        if var_name in downstream_hops:
            results.append(NodeClassification(var_name, "DOWNSTREAM", downstream_hops[var_name]))
            classified.add(var_name)
            continue

    # Anything only linked via an uncertain-direction edge to something
    # already on the upstream/downstream/target path is worth surfacing,
    # even though it can't be given a hop distance.
    for var_name, partners in uncertain_partners.items():
        if var_name in classified:
            continue
        if partners & classified:
            results.append(NodeClassification(var_name, "UNCERTAIN_LINK", None))
            classified.add(var_name)

    for node in graph.nodes:
        if node.var_name not in classified:
            results.append(NodeClassification(node.var_name, "UNRELATED", None))

    return results


def classification_to_dict(classifications: list[NodeClassification]) -> list[dict]:
    return [
        {"var_name": c.var_name, "role": c.role, "hops": c.hops} for c in classifications
    ]
