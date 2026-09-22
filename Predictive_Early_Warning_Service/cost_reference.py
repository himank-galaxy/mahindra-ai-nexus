"""
Typical repair cost per issue_category - the piece
docs/data_required_for_warranty_predictive_model.md section 3 flagged as
missing ("a reusable cost-per-part-issue reference table... does not
exist yet"). Computed from the real claim_amount_inr distribution in
warranty_claims.csv + insurance_claims.csv where enough real examples
exist for that issue_category, falling back to the
supplier_component_category-level average otherwise, and to a fleet-wide
average as a last resort. The source of each number is always reported
alongside it - a caller must know whether a number is real-sample-backed
or a fallback, never treat a fallback as equally precise.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import warranty_config

MIN_SAMPLES_FOR_ISSUE_LEVEL_COST = 2


@dataclass(frozen=True)
class CostEstimate:
    issue_category: str
    typical_cost_inr: float
    sample_count: int
    source: str  # "issue_category" | "component_category" | "fleet_average"


def _load_claim_amounts() -> pd.DataFrame:
    frames = []
    try:
        warranty = pd.read_csv(warranty_config.WARRANTY_CLAIMS_PATH)
        frames.append(warranty[["issue_category", "supplier_component_category", "claim_amount_inr"]])
    except FileNotFoundError:
        pass
    try:
        insurance = pd.read_csv(warranty_config.INSURANCE_CLAIMS_PATH)
        insurance = insurance.rename(columns={"supplier_component_category": "supplier_component_category"})
        insurance = insurance.assign(issue_category="ACCIDENT_DAMAGE")
        frames.append(insurance[["issue_category", "supplier_component_category", "claim_amount_inr"]])
    except FileNotFoundError:
        pass

    if not frames:
        return pd.DataFrame(columns=["issue_category", "supplier_component_category", "claim_amount_inr"])
    return pd.concat(frames, ignore_index=True)


def build_cost_reference() -> dict[str, CostEstimate]:
    claims = _load_claim_amounts()

    fleet_average = float(claims["claim_amount_inr"].mean()) if not claims.empty else 0.0

    component_averages = (
        claims.groupby("supplier_component_category")["claim_amount_inr"].mean().to_dict()
        if not claims.empty
        else {}
    )

    issue_stats = (
        claims.groupby("issue_category")["claim_amount_inr"].agg(["mean", "count"])
        if not claims.empty
        else pd.DataFrame(columns=["mean", "count"])
    )

    estimates: dict[str, CostEstimate] = {}
    for component_category, issue_categories in warranty_config.CLUSTERS.items():
        for issue_category in issue_categories:
            if issue_category in issue_stats.index and issue_stats.loc[issue_category, "count"] >= MIN_SAMPLES_FOR_ISSUE_LEVEL_COST:
                estimates[issue_category] = CostEstimate(
                    issue_category=issue_category,
                    typical_cost_inr=float(issue_stats.loc[issue_category, "mean"]),
                    sample_count=int(issue_stats.loc[issue_category, "count"]),
                    source="issue_category",
                )
            elif component_category in component_averages:
                estimates[issue_category] = CostEstimate(
                    issue_category=issue_category,
                    typical_cost_inr=float(component_averages[component_category]),
                    sample_count=int((claims["supplier_component_category"] == component_category).sum()),
                    source="component_category",
                )
            else:
                estimates[issue_category] = CostEstimate(
                    issue_category=issue_category,
                    typical_cost_inr=fleet_average,
                    sample_count=int(len(claims)),
                    source="fleet_average",
                )

    return estimates


def build_component_cost_reference() -> dict[str, CostEstimate]:
    """
    Same claim data as build_cost_reference() above, but keyed by
    supplier_component_category instead of issue_category - needed for
    the live-telematics warning clusters (pews_config.py's
    WARNING_CLUSTERS), whose warning_type names (BATTERY_OVERHEATING,
    STEERING_STRESS, ...) are synthetic early-warning labels, not real
    warranty-claim issue_category values, so they have no entry in
    build_cost_reference()'s dict. Cluster names were deliberately chosen
    to equal the real supplier_component_category values (confirmed 1:1
    against data/generators/auto/service.py's COMPONENT_ISSUE_MAP), so
    this can key directly off the cluster name.
    """

    claims = _load_claim_amounts()
    if claims.empty:
        return {}

    component_stats = claims.groupby("supplier_component_category")["claim_amount_inr"].agg(["mean", "count"])

    estimates: dict[str, CostEstimate] = {}
    for component_category in component_stats.index:
        estimates[component_category] = CostEstimate(
            issue_category=component_category,
            typical_cost_inr=float(component_stats.loc[component_category, "mean"]),
            sample_count=int(component_stats.loc[component_category, "count"]),
            source="component_category",
        )
    return estimates
