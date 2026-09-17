"""Build and lay out a graph from the discovered features and relationships."""

from collections import Counter, defaultdict

from app.ai.causal.mobility_features import MobilityFeature, display_value, trend_percent, trend_tone
from app.ai.causal.pcmci_engine import PcmciEdge
from app.schemas.mobility import CausalNodeOut

NODE_WIDTH, NODE_HEIGHT = 240, 72


def format_duration_minutes(minutes: int) -> str:
    for divisor, unit in ((1440, "day"), (60, "hour"), (1, "minute")):
        if minutes >= divisor and minutes % divisor == 0:
            value = minutes // divisor
            return f"{value} {unit}{'s' if value != 1 else ''}"
    return "0 minutes"


def format_comparison_window(minutes: int) -> str:
    return f"prior {format_duration_minutes(minutes)}"


def collapse_parallel_edges(edges: list[PcmciEdge]) -> tuple[PcmciEdge, ...]:
    """Keep one representative lag for each directed node pair.

    PCMCI can retain several statistically significant lags for the same pair.
    The raw tests remain in the immutable snapshot, but the decision graph
    shows one arrow per direction so a relationship is not visually counted
    twice. The representative is the lag with the strongest adjusted evidence,
    then the strongest effect, with the shortest lag as a stable tie-breaker.
    """
    selected: dict[tuple[str, str], PcmciEdge] = {}
    for edge in edges:
        key = (edge.source, edge.target)
        current = selected.get(key)
        candidate_rank = (getattr(edge, "q_value", edge.p_value), -abs(edge.score), edge.lag)
        current_rank = (
            (getattr(current, "q_value", current.p_value), -abs(current.score), current.lag)
            if current
            else None
        )
        if current is None or candidate_rank < current_rank:
            selected[key] = edge
    return tuple(sorted(selected.values(), key=lambda edge: (-abs(edge.score), edge.source, edge.target, edge.lag)))


def layout_nodes(metrics: list[str], edges: list[PcmciEdge]) -> dict[str, tuple[float, float]]:
    """Condense cycles into components, then lay out the resulting DAG in layers.

    Feedback links remain visible: no direction is changed to obtain a layout.
    Only variables that participate in at least one retained edge are laid out.
    """
    adjacency = {key: set() for key in metrics}
    connected: set[str] = set()
    for edge in edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].add(edge.target)
            connected.update((edge.source, edge.target))
    indices, low, stack, active, components = {}, {}, [], set(), []

    def visit(key: str) -> None:
        indices[key] = low[key] = len(indices)
        stack.append(key)
        active.add(key)
        for target in sorted(adjacency[key]):
            if target not in indices:
                visit(target)
                low[key] = min(low[key], low[target])
            elif target in active:
                low[key] = min(low[key], indices[target])
        if low[key] == indices[key]:
            component = []
            while True:
                target = stack.pop()
                active.remove(target)
                component.append(target)
                if target == key:
                    break
            components.append(sorted(component))

    for key in sorted(connected):
        if key not in indices:
            visit(key)
    owner = {key: index for index, group in enumerate(components) for key in group}
    parents: dict[int, set[int]] = defaultdict(set)
    for source in connected:
        for target in adjacency[source]:
            if owner[source] != owner[target]:
                parents[owner[target]].add(owner[source])
    ranks: dict[int, int] = {}

    def rank(index: int) -> int:
        if index not in ranks:
            ranks[index] = max((rank(parent) + 1 for parent in parents[index]), default=0)
        return ranks[index]

    layers: dict[int, list[str]] = defaultdict(list)
    for index, group in enumerate(components):
        layers[rank(index)].extend(group)
    positions = {
        key: (40 + layer * 340, 40 + row * 120)
        for layer, group in sorted(layers.items())
        for row, key in enumerate(sorted(group))
    }
    return positions


def build_nodes(
    latest: dict[str, float],
    previous: dict[str, float],
    edges: list[PcmciEdge],
    comparison_minutes: int,
    features: tuple[MobilityFeature, ...],
) -> list[CausalNodeOut]:
    connected = {key for edge in edges for key in (edge.source, edge.target)}
    positions = layout_nodes(sorted(connected), edges)
    degree = Counter(key for edge in edges for key in (edge.source, edge.target))
    nodes = []
    for feature in features:
        key = feature.key
        if key not in connected:
            continue
        value, old = latest[key], previous[key]
        change = trend_percent(value, old)
        change_text = f"{change:+.1f}%" if change is not None else "Change from zero baseline"
        x, y = positions[key]
        nodes.append(
            CausalNodeOut(
                label=feature.label,
                x=x,
                y=y,
                metric_key=key,
                metric=display_value(feature, value),
                trend=f"{change_text} vs {format_comparison_window(comparison_minutes)}",
                trend_pct=change,
                trend_tone=trend_tone(feature, value, old),
                unit=feature.unit,
                aggregation=feature.aggregation,
                connection_count=degree[key],
                drivers=[],
                action="Select this measure to inspect its evidence.",
            )
        )
    return nodes


def build_edges(edges: list[PcmciEdge], features: tuple[MobilityFeature, ...]) -> list[tuple[str, str]]:
    labels = {feature.key: feature.label for feature in features}
    return sorted({(labels[edge.source], labels[edge.target]) for edge in edges})
