"""
Turns a warning record + its investigation result into a plain-English
"case file" text block - this, not raw JSON, is what actually goes into
the LLM prompt. See IMPLEMENTATION_PLAN.md section 3.

Every interpretive judgment (what "root cause candidate" means, whether an
edge's direction is confident, how a lag number translates to real time) is
made HERE, in plain Python, using the exact same source-of-truth fields
graph_walker.py and the investigate.html page already use - never left for
the LLM to infer from raw numbers. This is what keeps the Copilot's
explanations consistent with what the graph on screen actually shows.

The mirrored-edge merge below (the same A->B / B->A -> one line rule
already applied in ui/investigate.js) is deliberately duplicated here in
Python, so the case file describes the exact same simplified graph the
user is looking at, not the noisier raw edge list underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pews_config import CAUSAL_RESAMPLE_MINUTES

RESOLVED_MARKS = {"-->", "<--"}


@dataclass(frozen=True)
class ParsedInvestigation:
    """The same by-role/merged-edge breakdown build_case_file() computes
    inline, factored out so other consumers (explanation_builder.py) never
    have to re-derive it and risk drifting out of sync with what the
    Copilot and the graph on screen already agree on."""

    by_role: dict[str, list[dict[str, Any]]]
    target_var: str | None
    edges: list[dict[str, Any]]

    def edges_touching(self, var_name: str) -> list[dict[str, Any]]:
        return [e for e in self.edges if e["source"] == var_name or e["target"] == var_name]


def parse_investigation(investigation: dict[str, Any]) -> ParsedInvestigation:
    classifications = investigation["classifications"]
    by_role: dict[str, list[dict[str, Any]]] = {}
    for c in classifications:
        by_role.setdefault(c["role"], []).append(c)

    target_var = next((c["var_name"] for c in classifications if c["role"] == "TARGET"), None)
    edges = _merge_mirrored_edges(investigation["graph"]["edges"])

    return ParsedInvestigation(by_role=by_role, target_var=target_var, edges=edges)


def _split_var_name(var_name: str) -> tuple[str, str]:
    if "||" not in var_name:
        return var_name, var_name
    entity_id, metric = var_name.split("||", 1)
    return entity_id, metric


def _lag_to_text(lag: int) -> str:
    if lag == 0:
        return "at the same moment"
    minutes = lag * CAUSAL_RESAMPLE_MINUTES
    if minutes < 60:
        return f"{minutes} minutes earlier"
    hours = minutes / 60
    return f"{hours:g} hours earlier"


def _merge_mirrored_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same dedup rule as ui/investigate.js: one line per (pair, lag)."""

    merged: dict[str, dict[str, Any]] = {}
    for edge in edges:
        if edge["source"] == edge["target"]:
            continue
        key = "~~".join(sorted([edge["source"], edge["target"]])) + f"@lag{edge['lag']}"
        existing = merged.get(key)
        if existing is None or abs(edge["strength"]) > abs(existing["strength"]):
            merged[key] = edge
    return list(merged.values())


def _describe_edge(edge: dict[str, Any]) -> str:
    _, source_metric = _split_var_name(edge["source"])
    _, target_metric = _split_var_name(edge["target"])
    direction = "confidently directed" if edge["edge_mark"] in RESOLVED_MARKS else "direction UNCERTAIN"
    sign = "positive (they move together)" if edge["strength"] >= 0 else "negative (they move opposite ways)"

    return (
        f"- {source_metric} -> {target_metric} "
        f"(source measured {_lag_to_text(edge['lag'])}): "
        f"strength {edge['strength']:.2f}, {sign}, {direction} "
        f"[edge mark: {edge['edge_mark']}, p-value: {edge['p_value']:.2e}]"
    )


def build_case_file(warning: dict[str, Any], investigation: dict[str, Any] | None) -> str:
    """
    warning: a Warning record's __dict__ (see warnings_store.py)
    investigation: the persisted/in-memory investigation result dict
                   (graph + classifications + window info), or None if no
                   investigation has been run for this warning yet.
    """

    lines: list[str] = []

    lines.append("WARNING SUMMARY")
    lines.append(f"- Warning type: {warning['warning_type']}")
    lines.append(f"- Vehicle: {warning['vehicle_id']}")
    lines.append(f"- Target metric: {warning['target_metric']}")
    lines.append(f"- Predicted risk: {round(warning['prediction_probability'] * 100)}%")
    lines.append(
        f"- Likely to occur between {warning.get('forecast_gap_hours', 0)}h and "
        f"{warning['forecast_horizon_hours']}h from when this was first detected"
    )
    lines.append(f"- Severity: {warning['severity']}")
    lines.append(f"- Status: {warning['status']}")
    lines.append(f"- First detected: {warning['warning_timestamp']}")

    if investigation is None:
        lines.append("")
        lines.append(
            "NO CAUSAL INVESTIGATION HAS BEEN RUN YET for this warning. "
            "You only know the prediction summary above - you do NOT have a "
            "causal graph to explain. If asked about root cause, upstream, "
            "downstream, or the graph, tell the user to click 'Run "
            "Investigation' first."
        )
        return "\n".join(lines)

    lines.append("")
    lines.append("CAUSAL ANALYSIS WINDOW")
    lines.append(
        f"- Analyzed this vehicle's OWN telemetry only, from "
        f"{investigation['window_start']} to {investigation['window_end']}"
    )
    lines.append(
        f"- Panel size: {investigation['panel_shape'][0]} time-steps x "
        f"{investigation['panel_shape'][1]} variables"
    )

    parsed = parse_investigation(investigation)
    by_role = parsed.by_role
    target_var = parsed.target_var
    edges_touching = parsed.edges_touching

    lines.append("")
    lines.append("TARGET NODE")
    if target_var:
        _, metric = _split_var_name(target_var)
        lines.append(
            f"- {metric}: this is the metric the warning is about. "
            "Everything else below is included only because it relates to this node."
        )

    lines.append("")
    lines.append("ROOT-CAUSE CANDIDATE(S)")
    root_candidates = by_role.get("ROOT_CANDIDATE", [])
    if not root_candidates:
        lines.append(
            "- None found. No variable in this graph had a confidently-directed "
            "path into the target with no confident cause of its own."
        )
    else:
        for c in root_candidates:
            _, metric = _split_var_name(c["var_name"])
            lines.append(f"- {metric} ({c['hops']} hop(s) from target):")
            for edge in edges_touching(c["var_name"]):
                lines.append(f"  {_describe_edge(edge)}")
            lines.append(
                "  This is called a 'root-cause candidate' because nothing else "
                "in THIS graph has a confidently-directed influence on it - not "
                "proof it has no cause in the real world, just that this "
                "analysis found none."
            )

    lines.append("")
    lines.append("UPSTREAM NODES (between root cause and target, confidently directed)")
    upstream = [c for c in by_role.get("UPSTREAM", [])]
    if not upstream:
        lines.append("- None in this run.")
    else:
        for c in sorted(upstream, key=lambda x: x["hops"]):
            _, metric = _split_var_name(c["var_name"])
            lines.append(f"- {metric} ({c['hops']} hop(s) from target)")

    lines.append("")
    lines.append("DOWNSTREAM NODES (affected if the target condition continues)")
    downstream = by_role.get("DOWNSTREAM", [])
    if not downstream:
        lines.append("- None in this run.")
    else:
        for c in sorted(downstream, key=lambda x: x["hops"]):
            _, metric = _split_var_name(c["var_name"])
            lines.append(f"- {metric} ({c['hops']} hop(s) from target)")

    lines.append("")
    lines.append("UNCERTAIN-DIRECTION RELATIONSHIPS (real statistical link, direction unclear)")
    uncertain = by_role.get("UNCERTAIN_LINK", [])
    if not uncertain:
        lines.append("- None.")
    else:
        for c in uncertain:
            _, metric = _split_var_name(c["var_name"])
            lines.append(f"- {metric}:")
            for edge in edges_touching(c["var_name"]):
                lines.append(f"  {_describe_edge(edge)}")

    lines.append("")
    lines.append("IMPORTANT INTERPRETATION NOTES (always keep these in mind)")
    lines.append(
        "- 'Root-cause candidate' means no confidently-directed cause was found "
        "for it WITHIN THIS GRAPH - not proof it has no cause in the real world."
    )
    lines.append("- Edge strength ranges from -1 to 1; closer to +-1 is a stronger relationship.")
    lines.append("- Every edge shown already passed a p-value < 0.05 significance test.")
    lines.append(
        "- This is statistical evidence from ONE vehicle's own history, not a "
        "guaranteed physical explanation."
    )

    return "\n".join(lines)
