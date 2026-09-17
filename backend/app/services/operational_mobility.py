"""Shape one immutable mobility snapshot into graph, KPI, and node responses."""

from app.ai.causal.graph_builder import (
    NODE_HEIGHT,
    NODE_WIDTH,
    build_edges,
    build_nodes,
    collapse_parallel_edges,
    format_comparison_window,
)
from app.ai.causal.mobility_features import display_value, trend_percent, trend_tone
from app.core.errors import NotFoundError
from app.schemas.mobility import (
    MobilityEdgeOut,
    MobilityGraphOut,
    MobilityKpiOut,
    MobilityNodeDetailOut,
    MobilityNodeHistoryPointOut,
    MobilityNodeRelationshipOut,
    MobilityNodeStatsOut,
)
from app.services.base import BaseService
from app.services.mobility_causal_cache import MobilityCausalState, get_or_refresh, snapshot_metadata
from app.services.mobility_recommendations import DriverSummary, recommend_action


class OperationalMobilityService(BaseService):
    async def get_graph(self) -> MobilityGraphOut:
        state = await get_or_refresh()
        display_edges = collapse_parallel_edges(list(state.edges))
        nodes = build_nodes(
            state.latest, state.previous, list(display_edges), state.comparison_minutes, state.source.features
        )
        for node in nodes:
            index = state.metrics.index(node.metric_key)
            node.recent_values = state.values[-20:, index].tolist()
        # Health cards follow the graph's most connected measures, with stable ties.
        highlights = sorted(nodes, key=lambda node: (-node.connection_count, node.metric_key))[:5]
        return MobilityGraphOut(
            nodes=nodes,
            edges=build_edges(list(display_edges), state.source.features),
            edge_details=[
                MobilityEdgeOut(
                    source=edge.source,
                    target=edge.target,
                    score=edge.score,
                    p_value=edge.p_value,
                    q_value=edge.q_value,
                    lag_minutes=edge.lag * state.stride_hours * 60,
                )
                for edge in display_edges
            ],
            kpis=[
                MobilityKpiOut(
                    label=node.label,
                    value=node.metric,
                    trend=node.trend,
                    metric_key=node.metric_key,
                    trend_tone=node.trend_tone,
                )
                for node in highlights
            ],
            metadata=snapshot_metadata(state),
            width=max((node.x + NODE_WIDTH + 40 for node in nodes), default=600),
            height=max((node.y + NODE_HEIGHT + 40 for node in nodes), default=400),
            node_width=NODE_WIDTH,
            node_height=NODE_HEIGHT,
        )

    async def list_kpis(self) -> list[MobilityKpiOut]:
        return (await self.get_graph()).kpis

    async def get_node_detail(
        self,
        metric: str,
        snapshot_id: str | None = None,
        *,
        state: MobilityCausalState | None = None,
    ) -> MobilityNodeDetailOut:
        state = state or await get_or_refresh(snapshot_id)
        features = {feature.key: feature for feature in state.source.features}
        if metric not in features:
            raise NotFoundError(f"Unknown or excluded mobility measure '{metric}'.", code="mobility_metric_not_found")
        feature = features[metric]
        column = state.values[:, state.metrics.index(metric)]
        current, previous = float(column[-1]), float(column[-2])
        relationships = []
        for edge in collapse_parallel_edges(list(state.edges)):
            if metric not in (edge.source, edge.target):
                continue
            incoming = edge.target == metric
            other = edge.source if incoming else edge.target
            relationships.append(
                MobilityNodeRelationshipOut(
                    metric=other,
                    label=features[other].label,
                    direction="into" if incoming else "out_of",
                    score=edge.score,
                    lag_minutes=edge.lag * state.stride_hours * 60,
                    p_value=edge.p_value,
                    q_value=edge.q_value,
                )
            )
        relationships.sort(key=lambda item: (-abs(item.score), item.metric, item.lag_minutes))
        drivers = [item for item in relationships if item.direction == "into"]
        trend = trend_percent(current, previous)
        comparison = format_comparison_window(state.comparison_minutes)
        recommendation = await recommend_action(
            None,
            metric=metric,
            label=feature.label,
            current_value=current,
            trend_pct=trend,
            trend_label=comparison,
            drivers=[
                DriverSummary(item.label, item.score, "+" if item.score >= 0 else "-", item.lag_minutes)
                for item in drivers
            ],
        )
        return MobilityNodeDetailOut(
            metric=metric,
            label=feature.label,
            current_value=current,
            display_value=display_value(feature, current),
            trend_pct=trend,
            trend_label=comparison,
            snapshot_id=state.snapshot_id,
            trend_tone=trend_tone(feature, current, previous),
            aggregation=feature.aggregation,
            unit=feature.unit,
            stats=MobilityNodeStatsOut(
                mean=float(column.mean()), min=float(column.min()), max=float(column.max()), std=float(column.std())
            ),
            history=[
                MobilityNodeHistoryPointOut(timestamp=date, value=float(value))
                for date, value in zip(state.source.source_dates[-60:], column[-60:], strict=True)
            ],
            relationships=relationships,
            top_drivers=drivers,
            recommended_action=recommendation,
        )
