"""
Builds the deterministic parts of the auto-generated "AI Explanation"
report for one warning's investigation - everything except the "What To
Do Next" section (see explanation_service.py for that).

Deliberately NOT an LLM call. Every fact here (which node is root cause,
what an edge's strength/lag is, which nodes are downstream) comes
straight from the same parsed investigation context_builder.py already
uses for the Copilot - filled into fixed templates, never generated
free-form. This guarantees the report can never state a node's role,
an edge's strength, or a lag incorrectly: there is nothing for an LLM to
get wrong here, because there is no LLM in this part of the pipeline.

See docs (chat-only plan, not yet a file) for the full design reasoning:
the report structure mirrors a reference IT-ops "AI explanation" example,
adapted to this project's warning/vehicle domain and to LPCMCI's explicit
uncertain-direction concept (which the reference example's engine did not
need to represent).
"""

from __future__ import annotations

from typing import Any

from context_builder import ParsedInvestigation, _split_var_name, parse_investigation

ROLE_ICON = {
    "ROOT_CANDIDATE": "🔴",
    "UPSTREAM": "🔵",
    "TARGET": "🎯",
    "DOWNSTREAM": "⚠️",
    "UNCERTAIN_LINK": "❓",
}

ROLE_LABEL = {
    "ROOT_CANDIDATE": "Root Cause",
    "UPSTREAM": "Contributing Factor",
    "TARGET": "Main Alert",
    "DOWNSTREAM": "Affected / At Risk",
    "UNCERTAIN_LINK": "Uncertain Link",
}

WARNING_TYPE_READABLE = {
    "BATTERY_OVERHEATING": "a battery overheating risk",
    "LOW_BATTERY_VOLTAGE": "a low battery voltage risk",
    "BATTERY_DEGRADATION": "a battery degradation risk",
}


def _node_explanation(role: str, metric: str, is_target: bool = False) -> str:
    if role == "ROOT_CANDIDATE":
        return (
            f"Tracks {metric} on this vehicle. This has been identified as a root-cause "
            "candidate - no confidently-directed cause was found for it within this analysis."
        )
    if role == "UPSTREAM":
        return (
            f"Tracks {metric} on this vehicle. This is an intermediate step the warning is "
            "statistically linked to on its way through the chain."
        )
    if role == "TARGET":
        return f"Tracks {metric} on this vehicle - this is the metric the warning is actually about."
    if role == "DOWNSTREAM":
        return (
            f"Tracks {metric} on this vehicle. This represents a downstream metric that may be "
            "affected if the current condition continues."
        )
    if role == "UNCERTAIN_LINK":
        return (
            f"Tracks {metric} on this vehicle. This has a real statistical link to the warning, "
            "but the direction of cause-and-effect could not be confidently resolved."
        )
    return f"Tracks {metric} on this vehicle."


def _chain_nodes(parsed: ParsedInvestigation) -> list[dict[str, Any]]:
    """One entry per node actually placed in the graph (root/upstream/
    target/downstream/uncertain), ordered root -> ... -> target -> ... ->
    furthest downstream, matching the reference example's "Node 1, Node 2,
    ..." presentation. Uncertain-direction nodes are appended last - they
    have no resolved position in the chain to sort into."""

    def sort_key_backward(c: dict[str, Any]) -> int:
        # Root/upstream: farthest from target (highest hop count) first,
        # so the chain reads as "origin -> ... -> target".
        return -(c.get("hops") or 0)

    def sort_key_forward(c: dict[str, Any]) -> int:
        # Downstream: nearest to target first, furthest effect last.
        return c.get("hops") or 0

    ordered: list[dict[str, Any]] = []
    backward = sorted(
        parsed.by_role.get("ROOT_CANDIDATE", []) + parsed.by_role.get("UPSTREAM", []),
        key=sort_key_backward,
    )
    ordered.extend(backward)
    ordered.extend(parsed.by_role.get("TARGET", []))
    ordered.extend(sorted(parsed.by_role.get("DOWNSTREAM", []), key=sort_key_forward))

    nodes: list[dict[str, Any]] = []
    for c in ordered:
        entity_id, metric = _split_var_name(c["var_name"])
        nodes.append(
            {
                "var_name": c["var_name"],
                "entity_id": entity_id,
                "metric": metric,
                "role": c["role"],
                "role_label": ROLE_LABEL[c["role"]],
                "role_icon": ROLE_ICON[c["role"]],
                "hops": c.get("hops"),
                "explanation": _node_explanation(c["role"], metric),
            }
        )

    for c in parsed.by_role.get("UNCERTAIN_LINK", []):
        entity_id, metric = _split_var_name(c["var_name"])
        nodes.append(
            {
                "var_name": c["var_name"],
                "entity_id": entity_id,
                "metric": metric,
                "role": "UNCERTAIN_LINK",
                "role_label": ROLE_LABEL["UNCERTAIN_LINK"],
                "role_icon": ROLE_ICON["UNCERTAIN_LINK"],
                "hops": c.get("hops"),
                "explanation": _node_explanation("UNCERTAIN_LINK", metric),
            }
        )

    return nodes


def _chain_narrative(parsed: ParsedInvestigation, chain_nodes: list[dict[str, Any]]) -> str:
    """The "How the chain unfolds" prose sentence, built from real edges
    only - groups nodes at the same hop-distance together with "and"
    rather than forcing a false single-file chain when the graph has
    parallel branches."""

    resolved = [n for n in chain_nodes if n["role"] != "UNCERTAIN_LINK"]
    if not resolved:
        return "No confidently-directed relationships were found in this graph."

    # Group consecutive nodes sharing the same role+hops into one "level"
    # so siblings are joined with "and" instead of implying a false order
    # between them.
    levels: list[list[dict[str, Any]]] = []
    for node in resolved:
        if levels and levels[-1][0]["role"] == node["role"] and levels[-1][0]["hops"] == node["hops"]:
            levels[-1].append(node)
        else:
            levels.append([node])

    def level_text(level: list[dict[str, Any]]) -> str:
        names = [n["metric"] for n in level]
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + f" and {names[-1]}"

    def edge_annotation(source_var: str, target_var: str) -> str:
        for edge in parsed.edges:
            if {edge["source"], edge["target"]} == {source_var, target_var}:
                sign = "+" if edge["strength"] >= 0 else "-"
                return f" (strength {sign}{abs(edge['strength']):.2f})"
        return ""

    parts = [level_text(levels[0])]
    for previous, current in zip(levels, levels[1:], strict=False):
        annotation = ""
        if len(previous) == 1 and len(current) == 1:
            annotation = edge_annotation(previous[0]["var_name"], current[0]["var_name"])
        if current[0]["role"] == "TARGET":
            # Name the target, THEN clarify it's the warning's own metric -
            # not the other way round, which read backward ("X, which is
            # the metric this warning is about - Y").
            parts.append(
                f", which in turn leads to {level_text(current)}{annotation} "
                "(the metric this warning is about)"
            )
        else:
            parts.append(f", which in turn leads to {level_text(current)}{annotation}")

    return "".join(parts) + "."


def build_explanation_context(warning: dict[str, Any], investigation: dict[str, Any]) -> dict[str, Any]:
    """
    Returns the fully deterministic (non-LLM) portion of the explanation:
    whats_happening, chain_narrative, chain_nodes, root_cause_summary,
    what_could_go_wrong - plus the data the next-steps LLM call needs
    (root_cause_metrics, downstream_metrics) so explanation_service.py
    doesn't have to re-derive them.
    """

    parsed = parse_investigation(investigation)
    chain_nodes = _chain_nodes(parsed)
    chain_narrative = _chain_narrative(parsed, chain_nodes)

    warning_type_readable = WARNING_TYPE_READABLE.get(
        warning["warning_type"], warning["warning_type"].replace("_", " ").lower()
    )
    probability_pct = round(warning["prediction_probability"] * 100)
    whats_happening = (
        f"Vehicle {warning['vehicle_id']} is showing {warning_type_readable}. The system detected a "
        f"predicted risk of {probability_pct}%, likely within {warning.get('forecast_gap_hours', 0)}-"
        f"{warning['forecast_horizon_hours']} hours from when this was first detected, and traced the "
        "cause-and-effect chain below to help identify what triggered it and what else could be affected."
    )

    root_candidates = parsed.by_role.get("ROOT_CANDIDATE", [])
    root_metrics = [_split_var_name(c["var_name"])[1] for c in root_candidates]
    if root_metrics:
        root_cause_summary = (
            f"The analysis points to {', '.join(root_metrics)} as the most likely starting "
            "point of the problem - this is where the issue originates before spreading to "
            "other parts of the system, based on this graph."
        )
    else:
        root_cause_summary = (
            "No confidently-directed root cause was found in this analysis - either nothing "
            "in this graph statistically precedes the warning, or the direction could not be "
            "resolved (see any uncertain-direction relationships below)."
        )

    downstream = parsed.by_role.get("DOWNSTREAM", [])
    downstream_metrics = [_split_var_name(c["var_name"])[1] for c in downstream]
    if downstream_metrics:
        what_could_go_wrong = (
            f"If this issue is not addressed, it could affect: {', '.join(downstream_metrics)}. "
            "This could lead to reduced vehicle performance, additional wear on related "
            "components, or an unplanned service visit."
        )
    else:
        what_could_go_wrong = "No downstream effects were found in this analysis."

    return {
        "whats_happening": whats_happening,
        "chain_narrative": chain_narrative,
        "chain_nodes": chain_nodes,
        "root_cause_summary": root_cause_summary,
        "what_could_go_wrong": what_could_go_wrong,
        "root_cause_metrics": root_metrics,
        "downstream_metrics": downstream_metrics,
    }
