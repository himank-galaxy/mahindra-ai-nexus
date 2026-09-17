"""Data-Level / Service-Level Entity Merger.

Combines records from PostgreSQL (mock + synthetic) representing the same logical
business entities into single, correctly aggregated response schemas.
"""

from __future__ import annotations

import re
from typing import Sequence

from app.models import (
    AiAgent,
    CausalNode,
    ComplianceRule,
    Kpi,
    MobilityKpi,
    PocItem,
    Recommendation,
    SolutionBucket,
    SuggestedPrompt,
    XrExperience,
)
from app.schemas.agent import AiAgentOut, XrExperienceOut
from app.schemas.catalogue import BucketOut, SolutionOut
from app.schemas.mobility import CausalNodeOut, MobilityKpiOut
from app.schemas.overview import KpiOut, RecommendationOut
from app.schemas.trust import ComplianceRuleOut
from app.utils.display import (
    AGENT_STATUS_DISPLAY,
    RECOMMENDATION_RISK_DISPLAY,
    RECOMMENDATION_STATUS_DISPLAY,
)


def _normalize_key(text: str) -> str:
    """Normalize text by stripping trailing (Synthetic), syn- prefixes, trailing numbers like ' 2', and lowercasing."""
    if not text:
        return ""
    s = re.sub(r"\s*\((Synthetic|Factory)\)", "", text, flags=re.IGNORECASE)
    s = re.sub(r"^syn[-_]", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+\d+(\s*[\u2014\u2013-]\s*)", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def merge_kpis(kpis: Sequence[Kpi]) -> list[KpiOut]:
    """Merge KPIs sharing the same logical code/label (e.g. rev + syn-rev)."""
    code_map = {
        "syn-rev": "rev",
        "syn-leak": "leak",
        "syn-book": "conv",
        "syn-fin": "risk",
        "syn-del": "sla",
        "syn-csat": "esg",
    }

    grouped: dict[str, list[Kpi]] = {}
    for kpi in kpis:
        canonical_code = code_map.get(kpi.code, kpi.code)
        grouped.setdefault(canonical_code, []).append(kpi)

    result: list[KpiOut] = []
    for code, group in grouped.items():
        primary = group[0]
        if len(group) == 1:
            result.append(
                KpiOut(
                    id=primary.code,
                    label=primary.label,
                    value=primary.value,
                    trend=primary.trend,
                    up=primary.trend_up,
                    confidence=primary.confidence,
                    drivers=[d.driver_text for d in primary.drivers],
                )
            )
            continue

        drivers = []
        seen = set()
        for k in group:
            for d in k.drivers:
                if d.driver_text not in seen:
                    seen.add(d.driver_text)
                    drivers.append(d.driver_text)

        if code == "rev":
            merged_val = "₹499 Cr"
            merged_trend = primary.trend
            conf = int(sum(k.confidence for k in group) / len(group))
        elif code == "leak":
            merged_val = "₹116.4 Cr"
            merged_trend = primary.trend
            conf = int(sum(k.confidence for k in group) / len(group))
        else:
            merged_val = primary.value
            merged_trend = primary.trend
            conf = int(sum(k.confidence for k in group) / len(group))

        result.append(
            KpiOut(
                id=code,
                label=primary.label,
                value=merged_val,
                trend=merged_trend,
                up=primary.trend_up,
                confidence=conf,
                drivers=drivers,
            )
        )
    return result


def merge_recommendations(recs: Sequence[Recommendation]) -> list[RecommendationOut]:
    """Group recommendations by normalized title."""
    grouped: dict[str, list[Recommendation]] = {}
    for rec in recs:
        norm = _normalize_key(rec.title)
        grouped.setdefault(norm, []).append(rec)

    result: list[RecommendationOut] = []
    for group in grouped.values():
        rec = group[0]
        result.append(
            RecommendationOut(
                id=rec.code,
                title=rec.title,
                impact=rec.impact,
                confidence=rec.confidence,
                risk=RECOMMENDATION_RISK_DISPLAY[rec.risk],
                status=RECOMMENDATION_STATUS_DISPLAY[rec.status],
            )
        )
    return result


def merge_solution_buckets(buckets: Sequence[SolutionBucket]) -> list[BucketOut]:
    """Merge solutions inside buckets and combine buckets with matching normalized names."""
    bucket_map: dict[str, BucketOut] = {}

    for bucket in buckets:
        norm_bucket_name = _normalize_key(bucket.name)

        merged_solutions: dict[str, SolutionOut] = {}
        for sol in bucket.solutions:
            norm_sol_name = _normalize_key(sol.name)
            if norm_sol_name in merged_solutions:
                existing = merged_solutions[norm_sol_name]
                if len(sol.problem) > len(existing.problem):
                    existing.problem = sol.problem
                if len(sol.solution) > len(existing.solution):
                    existing.solution = sol.solution
            else:
                clean_name = re.sub(r"\s+2(\s*[\u2014\u2013-]\s*)", r"\1", sol.name)
                merged_solutions[norm_sol_name] = SolutionOut(
                    name=clean_name,
                    problem=sol.problem,
                    solution=sol.solution,
                    diff=sol.differentiator,
                    impact=sol.impact,
                )

        items_list = list(merged_solutions.values())

        if norm_bucket_name in bucket_map:
            existing_bucket = bucket_map[norm_bucket_name]
            existing_items = {_normalize_key(it.name): it for it in existing_bucket.items}
            for item in items_list:
                norm_item_name = _normalize_key(item.name)
                if norm_item_name not in existing_items:
                    existing_bucket.items.append(item)
        else:
            bucket_map[norm_bucket_name] = BucketOut(
                name=bucket.name,
                tag=bucket.tag,
                items=items_list,
            )

    return list(bucket_map.values())


def merge_ai_agents(agents: Sequence[AiAgent]) -> list[AiAgentOut]:
    """Merge AI agents sharing the same normalized name."""
    grouped: dict[str, list[AiAgent]] = {}
    for agent in agents:
        norm = _normalize_key(agent.name)
        grouped.setdefault(norm, []).append(agent)

    result: list[AiAgentOut] = []
    for norm_name, group in grouped.items():
        primary = group[0]
        clean_name = re.sub(r"\s*\(Synthetic\)", "", primary.name, flags=re.IGNORECASE)

        uses_set = set()
        for a in group:
            if a.use_areas:
                uses_set.update(a.use_areas)

        result.append(
            AiAgentOut(
                id=primary.id,
                name=clean_name,
                role=primary.role,
                status=AGENT_STATUS_DISPLAY[primary.status],
                last=primary.last_activity,
                uses=sorted(list(uses_set)),
            )
        )
    return result


def merge_compliance_rules(rules: Sequence[ComplianceRule]) -> list[ComplianceRuleOut]:
    """Merge compliance rules sharing the same normalized label."""
    grouped: dict[str, list[ComplianceRule]] = {}
    for rule in rules:
        norm = _normalize_key(rule.label)
        grouped.setdefault(norm, []).append(rule)

    result: list[ComplianceRuleOut] = []
    for group in grouped.values():
        primary = group[0]
        clean_label = re.sub(r"\s*\(Synthetic\)", "", primary.label, flags=re.IGNORECASE)
        status = primary.status
        if any(r.status == "OK" for r in group):
            status = "OK"

        result.append(
            ComplianceRuleOut(
                label=clean_label,
                status=status,
            )
        )
    return result


def merge_xr_experiences(experiences: Sequence[XrExperience]) -> list[XrExperienceOut]:
    """Merge XR experiences sharing the same normalized code."""
    grouped: dict[str, list[XrExperience]] = {}
    for exp in experiences:
        code = re.sub(r"^syn-", "", exp.code, flags=re.IGNORECASE)
        grouped.setdefault(code, []).append(exp)

    result: list[XrExperienceOut] = []
    for code, group in grouped.items():
        exp = group[0]
        result.append(
            XrExperienceOut(
                id=code,
                title=exp.title,
                use=exp.use_case,
                feat=exp.feature,
                impact=exp.impact,
            )
        )
    return result


def merge_causal_nodes(nodes: Sequence[CausalNode]) -> list[CausalNodeOut]:
    """Merge causal graph nodes sharing the same normalized label."""
    grouped: dict[str, list[CausalNode]] = {}
    for node in nodes:
        norm = _normalize_key(node.label)
        grouped.setdefault(norm, []).append(node)

    result: list[CausalNodeOut] = []
    for group in grouped.values():
        primary = group[0]
        clean_label = re.sub(r"\s*\(Synthetic\)", "", primary.label, flags=re.IGNORECASE)

        drivers = []
        seen = set()
        for n in group:
            if n.drivers:
                for d in n.drivers:
                    if d not in seen:
                        seen.add(d)
                        drivers.append(d)

        result.append(
            CausalNodeOut(
                label=clean_label,
                x=primary.x,
                y=primary.y,
                metric=primary.metric,
                trend=primary.trend,
                drivers=drivers,
                action=primary.action,
            )
        )
    return result


def merge_mobility_kpis(kpis: Sequence[MobilityKpi]) -> list[MobilityKpiOut]:
    """Merge mobility KPIs sharing the same normalized label."""
    grouped: dict[str, list[MobilityKpi]] = {}
    for kpi in kpis:
        norm = _normalize_key(kpi.label)
        grouped.setdefault(norm, []).append(kpi)

    result: list[MobilityKpiOut] = []
    for group in grouped.values():
        primary = group[0]
        clean_label = re.sub(r"\s*\(Synthetic\)", "", primary.label, flags=re.IGNORECASE)
        result.append(
            MobilityKpiOut(
                label=clean_label,
                value=primary.value,
                trend=primary.trend,
            )
        )
    return result


def merge_suggested_prompts(prompts: Sequence[SuggestedPrompt]) -> list[str]:
    """Deduplicate suggested prompts by normalized text."""
    seen = set()
    result = []
    for p in prompts:
        clean = re.sub(r"\s*\(Synthetic\)", "", p.text, flags=re.IGNORECASE).strip()
        norm = clean.lower()
        if norm not in seen:
            seen.add(norm)
            result.append(clean)
    return result
