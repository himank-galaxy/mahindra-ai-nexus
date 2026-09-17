"""Build copilot evidence from exactly the graph snapshot displayed by the browser."""

from __future__ import annotations

from collections.abc import Collection

from app.ai.causal.graph_builder import (
    collapse_parallel_edges,
    format_comparison_window,
    format_duration_minutes,
)
from app.ai.causal.mobility_features import display_value, trend_percent
from app.schemas.mobility import MobilityNodeDetailOut
from app.services.mobility_causal_cache import MobilityCausalState, snapshot_metadata


def visible_metric_keys(
    state: MobilityCausalState,
    requested_metrics: Collection[str] | None,
) -> set[str]:
    """Return validated keys for the current view; None means the full displayed graph."""

    if requested_metrics is not None:
        return set(requested_metrics) & set(state.metrics)
    return {key for edge in state.edges for key in (edge.source, edge.target)}


def _display_edges(state: MobilityCausalState, visible_metrics: set[str]):
    return collapse_parallel_edges(
        [
            edge
            for edge in state.edges
            if edge.source in visible_metrics and edge.target in visible_metrics
        ]
    )


def _role(metric: str, edges, selected_metric: str | None) -> str:
    if metric == selected_metric:
        return "selected target"
    incoming = any(edge.target == metric for edge in edges)
    outgoing = any(edge.source == metric for edge in edges)
    if not incoming:
        return "upstream driver"
    if outgoing:
        return "intermediate driver"
    return "downstream outcome"


def _trend_text(current: float, previous: float, comparison: str) -> str:
    change = trend_percent(current, previous)
    if change is None:
        return f"change versus {comparison} is unavailable because the earlier value was zero"
    if abs(change) < 0.05:
        return f"broadly unchanged versus {comparison}"
    direction = "up" if change > 0 else "down"
    return f"{direction} {abs(change):.1f}% versus {comparison}"


def _important_chain(edges, selected_metric: str | None) -> list[str]:
    if not edges:
        return []
    strongest = max(edges, key=lambda edge: abs(edge.score))
    selected = (
        selected_metric
        if selected_metric
        and any(selected_metric in (edge.source, edge.target) for edge in edges)
        else strongest.target
    )
    chain = [selected]
    seen = {selected}
    cursor = selected
    for _ in range(2):
        candidates = [edge for edge in edges if edge.target == cursor and edge.source not in seen]
        if not candidates:
            break
        edge = max(candidates, key=lambda item: abs(item.score))
        chain.insert(0, edge.source)
        seen.add(edge.source)
        cursor = edge.source
    cursor = selected
    for _ in range(2):
        candidates = [edge for edge in edges if edge.source == cursor and edge.target not in seen]
        if not candidates:
            break
        edge = max(candidates, key=lambda item: abs(item.score))
        chain.append(edge.target)
        seen.add(edge.target)
        cursor = edge.target
    return chain


def build_case_file(
    state: MobilityCausalState,
    prior_state: MobilityCausalState | None,
    selected_node: MobilityNodeDetailOut | None,
    *,
    requested_metrics: Collection[str] | None = None,
    domain_filter: str = "All Measures",
    chain_focus: bool = False,
) -> str:
    metadata = snapshot_metadata(state)
    visible = visible_metric_keys(state, requested_metrics)
    display_edges = _display_edges(state, visible)
    features = {feature.key: feature for feature in state.source.features}
    comparison = format_comparison_window(state.comparison_minutes)
    selected_metric = selected_node.metric if selected_node else None

    def describe(edge):
        relation = "positive / same-direction" if edge.score >= 0 else "negative / opposite-direction"
        return (
            f"{features[edge.source].label} → {features[edge.target].label}: "
            f"{relation}; strength {abs(edge.score):.3f}; "
            f"lag {format_duration_minutes(edge.lag * state.stride_hours * 60)}; "
            f"p={edge.p_value:.3g}, FDR-adjusted q={edge.q_value:.3g}"
        )

    public_warnings = [
        warning for warning in metadata.warnings if not any(term in warning.lower() for term in ("synthetic", "pcmci"))
    ]
    lines = [
        f"CURRENT DISPLAYED VIEW: {len(visible)} measures and {len(display_edges)} directed relationships.",
        f"View filter: {domain_filter}; active-chain focus: {chain_focus}.",
        f"Snapshot: {state.snapshot_id}. Computed: {state.computed_at.isoformat()}.",
        f"Data coverage: {metadata.data_start.isoformat()} to {metadata.data_end.isoformat()}.",
        f"{state.effective_observation_count} usable sampled observations across "
        f"{metadata.segment_count} continuous segment(s); sampling interval {state.stride_hours} hours.",
        f"Status: {metadata.status}. " + " ".join(public_warnings),
        "VISIBLE MEASURES:",
    ]
    for metric in sorted(visible, key=lambda key: features[key].label):
        feature = features[metric]
        current = float(state.latest[metric])
        previous = float(state.previous[metric])
        lines.append(
            f"{feature.label}: current value {display_value(feature, current)}; "
            f"{_trend_text(current, previous, comparison)}; role {_role(metric, display_edges, selected_metric)}; "
            f"{feature.aggregation}, unit {feature.unit}."
        )
    lines.append("VISIBLE RELATIONSHIPS:")
    lines.extend(describe(edge) for edge in display_edges)
    if not display_edges:
        lines.append("No relationship is displayed in the current view.")

    lines.append("CHANGES SINCE PREVIOUS COMPUTATION:")
    if prior_state is None or prior_state.snapshot_id == state.snapshot_id:
        lines.append("No earlier comparable snapshot is available.")
    else:
        old_edges = _display_edges(prior_state, visible_metric_keys(prior_state, visible))
        old = {(edge.source, edge.target): edge for edge in old_edges}
        new = {(edge.source, edge.target): edge for edge in display_edges}
        changes = []
        for key in sorted(new.keys() - old.keys()):
            changes.append("NEW: " + describe(new[key]))
        for key in sorted(old.keys() - new.keys()):
            edge = old[key]
            source_label = features[edge.source].label if edge.source in features else edge.source
            target_label = features[edge.target].label if edge.target in features else edge.target
            changes.append(
                f"NO LONGER DISPLAYED: {source_label} → {target_label}"
            )
        for key in sorted(new.keys() & old.keys()):
            before, after = old[key].score, new[key].score
            if before * after < 0:
                changes.append("DIRECTION OF MOVEMENT CHANGED: " + describe(new[key]))
            elif abs(after) > abs(before) * 1.1:
                changes.append("STRENGTHENED: " + describe(new[key]))
            elif abs(after) < abs(before) * 0.9:
                changes.append("WEAKENED: " + describe(new[key]))
        lines.extend(changes or ["No material change in the displayed relationships."])

    if selected_node and selected_node.metric in visible:
        trend = (
            f"{selected_node.trend_pct:+.1f}%"
            if selected_node.trend_pct is not None
            else "not available from a zero baseline"
        )
        lines.extend(
            [
                f"SELECTED TARGET: {selected_node.label}; value {selected_node.display_value}; "
                f"trend {trend} versus {selected_node.trend_label}.",
                f"Selected-target history statistics: {selected_node.stats.model_dump()}.",
                f"Evidence-backed investigation: {selected_node.recommended_action}",
            ]
        )
    else:
        lines.append("No visible target node is selected.")
    lines.append(
        "INTERPRETATION GUARDRAIL: Relationships are time-lagged statistical evidence, not proven "
        "intervention effects. Strength is signed association: positive means the measures tend to move "
        "in the same direction and negative means they tend to move in opposite directions."
    )
    return "\n".join(lines)


def build_default_explanation(
    state: MobilityCausalState,
    selected_node: MobilityNodeDetailOut | None,
    *,
    requested_metrics: Collection[str] | None = None,
) -> str:
    """Create a data-derived explanation when no external language model is configured."""

    visible = visible_metric_keys(state, requested_metrics)
    edges = list(_display_edges(state, visible))
    features = {feature.key: feature for feature in state.source.features}
    labels = {key: feature.label for key, feature in features.items()}
    selected_metric = selected_node.metric if selected_node and selected_node.metric in visible else None
    chain = _important_chain(edges, selected_metric)
    strongest = max(edges, key=lambda edge: abs(edge.score)) if edges else None
    incoming = sorted(
        [edge for edge in edges if edge.target == selected_metric],
        key=lambda edge: -abs(edge.score),
    )
    outgoing = sorted(
        [edge for edge in edges if edge.source == selected_metric],
        key=lambda edge: -abs(edge.score),
    )

    if selected_node and selected_metric:
        trend = (
            f"{'up' if selected_node.trend_pct >= 0 else 'down'} {abs(selected_node.trend_pct):.1f}% "
            f"versus {selected_node.trend_label}"
            if selected_node.trend_pct is not None
            else f"with no percentage comparison available versus {selected_node.trend_label}"
        )
        happening = (
            f"{selected_node.label} is currently {selected_node.display_value}, {trend}. "
            f"The displayed graph connects it to {len(incoming)} incoming driver(s) and "
            f"{len(outgoing)} downstream relationship(s)."
        )
        if incoming:
            happening += (
                f" The strongest direct driver shown is {labels[incoming[0].source]} "
                f"(strength {abs(incoming[0].score):.2f})."
            )
    elif strongest:
        happening = (
            f"The current view contains {len(visible)} connected measures and {len(edges)} relationships. "
            f"The strongest displayed relationship is {labels[strongest.source]} influencing "
            f"{labels[strongest.target]} with strength {abs(strongest.score):.2f}."
        )
    else:
        happening = "The current view does not contain a retained relationship to explain."

    chain_lines = []
    if chain:
        chain_lines.append(" → ".join(labels[key] for key in chain))
        edge_lookup = {(edge.source, edge.target): edge for edge in edges}
        for source, target in zip(chain, chain[1:], strict=False):
            edge = edge_lookup[(source, target)]
            movement = "same direction" if edge.score >= 0 else "opposite directions"
            chain_lines.append(
                f"{labels[source]} influences {labels[target]} with strength "
                f"{abs(edge.score):.2f}; they tend to move in the {movement}, and the relationship "
                f"appears after about {format_duration_minutes(edge.lag * state.stride_hours * 60)}."
            )
    else:
        chain_lines.append("No cause-effect chain is visible under the current filter.")

    node_lines = []
    selected_index = chain.index(selected_metric) if selected_metric in chain else -1
    for index, metric in enumerate(chain, start=1):
        if metric == selected_metric:
            role = "🎯 Target Metric"
        elif selected_index >= 0 and index - 1 > selected_index:
            role = "⚠️ Downstream Impact"
        elif index == 1:
            role = "🔵 Driver"
        else:
            role = "🔵 Contributing Factor"
        feature = features[metric]
        current = display_value(feature, float(state.latest[metric]))
        node_lines.append(
            f"**Node {index} | {role} | {feature.label}**\n"
            f"What this means: This is a {feature.aggregation} measure reported in {feature.unit}; "
            f"its current value is {current}. Its role is based only on the arrows visible in this view."
        )
    if not node_lines:
        node_lines.append("No connected node is visible in the current view.")

    driver_lines = []
    for index, edge in enumerate(incoming[:5], start=1):
        relationship = "same-direction" if edge.score >= 0 else "opposite-direction"
        driver_lines.append(
            f"{index}. {labels[edge.source]} — strength {abs(edge.score):.2f}, {relationship}, "
            f"lag about {format_duration_minutes(edge.lag * state.stride_hours * 60)}."
        )
    if not driver_lines:
        target = selected_node.label if selected_node and selected_metric else "the selected target"
        driver_lines.append(f"No incoming driver for {target} is displayed in the current view.")

    impact_lines = []
    if selected_node and selected_metric and outgoing:
        for edge in outgoing[:3]:
            if selected_node.trend_pct is None or abs(selected_node.trend_pct) < 0.05:
                movement = "in the same direction" if edge.score >= 0 else "in the opposite direction"
            else:
                rises = (selected_node.trend_pct > 0) == (edge.score > 0)
                movement = "higher" if rises else "lower"
            impact_lines.append(
                f"If the current movement in {selected_node.label} continues, {labels[edge.target]} may move "
                f"{movement} after about {format_duration_minutes(edge.lag * state.stride_hours * 60)}. "
                "This is a graph-supported possibility, not a forecast."
            )
    else:
        impact_lines.append("No downstream impact from the selected target is shown in the current view.")

    action_lines = []
    if selected_node and selected_metric:
        action_lines.append(f"1. {selected_node.recommended_action}")
        if incoming:
            edge = incoming[0]
            action_lines.append(
                f"2. Review {labels[edge.source]} first and compare {selected_node.label} after the "
                f"{format_duration_minutes(edge.lag * state.stride_hours * 60)} lag shown by the graph."
            )
        if outgoing:
            action_lines.append(
                f"{len(action_lines) + 1}. Monitor {labels[outgoing[0].target]} while investigating "
                f"{selected_node.label} because it is the strongest displayed downstream relationship."
            )
    elif strongest:
        action_lines.append(
            f"1. Investigate the records behind {labels[strongest.source]} and {labels[strongest.target]}, "
            "the strongest relationship in the current view."
        )
    else:
        action_lines.append("1. Clear the current filter or wait for a graph with retained relationships.")
    action_lines.append(
        f"{len(action_lines) + 1}. Validate the relationship in business records before changing operations."
    )

    return "\n\n".join(
        [
            "### 🔍 What's Happening\n" + happening,
            "### 🔗 Cause-Effect Chain\n" + "\n".join(chain_lines),
            "### Each Important Node Explained\n" + "\n\n".join(node_lines),
            "### 🔎 Key Drivers\n" + "\n".join(driver_lines),
            "### ⚠️ What Could Happen\n" + "\n".join(impact_lines),
            "### 🛠️ Recommended Actions\n" + "\n".join(action_lines),
            "### 📊 How to Read This Graph\n"
            "Arrows show the direction of observed influence. Strength describes how closely two measures "
            "move after accounting for the other included measures; lag is the typical delay before the "
            "relationship appears. Positive relationships move together, while negative relationships move "
            "in opposite directions. The graph is statistical evidence and does not prove an intervention "
            "will cause the same result.",
        ]
    )


def generated_explanation_is_grounded(
    reply: str,
    state: MobilityCausalState,
    selected_node: MobilityNodeDetailOut | None,
    *,
    requested_metrics: Collection[str] | None = None,
) -> bool:
    """Reject incomplete or visibly ungrounded prose in favor of the deterministic explanation."""

    required_headings = (
        "What's Happening",
        "Cause-Effect Chain",
        "Each Important Node Explained",
        "Key Drivers",
        "What Could Happen",
        "Recommended Actions",
        "How to Read This Graph",
    )
    lower_reply = reply.lower()
    if not reply.strip() or any(heading not in reply for heading in required_headings):
        return False
    if any(term in lower_reply for term in ("synthetic", "pcmci", "lpcmci")):
        return False

    visible = visible_metric_keys(state, requested_metrics)
    features = {feature.key: feature for feature in state.source.features}
    if any(metric.lower() in lower_reply for metric in state.metrics):
        return False
    if any(
        feature.label.lower() in lower_reply
        for metric, feature in features.items()
        if metric not in visible
    ):
        return False

    edges = list(_display_edges(state, visible))
    selected_metric = selected_node.metric if selected_node and selected_node.metric in visible else None
    required_metrics = set(_important_chain(edges, selected_metric))
    if selected_metric:
        required_metrics.add(selected_metric)
        incoming = sorted(
            [edge for edge in edges if edge.target == selected_metric],
            key=lambda edge: -abs(edge.score),
        )
        required_metrics.update(edge.source for edge in incoming[:3])
        outgoing = sorted(
            [edge for edge in edges if edge.source == selected_metric],
            key=lambda edge: -abs(edge.score),
        )
        if outgoing:
            required_metrics.add(outgoing[0].target)
    return all(features[metric].label.lower() in lower_reply for metric in required_metrics)
