"""
Fleet-wide ranking of currently OPEN live-telematics warnings by total
expected Mahindra financial impact - the telematics-side counterpart to
warranty_rank.py's fleet-wide ranking of batch warranty predictions.

Directly reuses warranty_rank.py's _aggregate_and_rank() (same rupee-total
+ severity-escalation logic, same RankedIssue shape) rather than
reimplementing it - only the INPUT differs: here it's built from open
Warning records (warnings_store.py) instead of warranty_predict.py's
per-vehicle IssuePrediction batch.

Computed once per PEWS scheduler tick (see scheduler.py's main loop) and
cached via warnings_store.save_impact_ranking() - never recomputed live
in a request path, the same "scheduler computes, API only reads"
principle already proven for warranty_predictions_store.py's fleet
ranking (a naive per-request aggregation there measured ~46s).
"""

from __future__ import annotations

import pandas as pd

import warranty_config
from cost_reference import build_component_cost_reference
from pews_config import WARNING_TYPES_BY_NAME
from warnings_store import OPEN_STATUSES, list_warnings
from warranty_rank import RankedIssue, _aggregate_and_rank


def compute_impact_ranking() -> list[RankedIssue]:
    open_warnings = [w for w in list_warnings() if w.status in OPEN_STATUSES]
    cost_by_component = build_component_cost_reference()

    vehicle_predictions: dict[str, list[dict]] = {}
    for warning in open_warnings:
        config = WARNING_TYPES_BY_NAME.get(warning.warning_type)
        if config is None:
            continue  # a warning_type retired from pews_config.py since this warning was created

        cost = cost_by_component.get(config.cluster)
        typical_cost = cost.typical_cost_inr if cost is not None else 0.0
        is_eligible = bool(warning.is_warranty_eligible)
        expected_liability = warning.prediction_probability * typical_cost * (1.0 if is_eligible else 0.0)

        vehicle_predictions.setdefault(warning.vehicle_id, []).append(
            {
                "issue_category": warning.warning_type,
                "component_category": config.cluster,
                "probability": warning.prediction_probability,
                "eligibility": {"is_eligible": is_eligible},
                "expected_liability_inr": expected_liability,
                # Not a low-confidence flag from a thin-data model here -
                # these clusters were trained fleet-wide (see
                # train_model.py), not per-issue on a handful of rows.
                "low_confidence": False,
            }
        )

    try:
        fleet_size = len(pd.read_csv(warranty_config.DELIVERIES_PATH))
    except FileNotFoundError:
        fleet_size = len(vehicle_predictions)

    severities = {warning_type: config.severity_label for warning_type, config in WARNING_TYPES_BY_NAME.items()}

    return _aggregate_and_rank(vehicle_predictions, fleet_size, severities)


if __name__ == "__main__":
    ranked = compute_impact_ranking()
    print(f"{'Rank':>4} {'Warning Type':25s} {'Severity':8s} {'Total Expected Liability':>25s} {'Affected':>9s}  Notes")
    for display_rank, issue in enumerate(ranked[:25], start=1):
        notes = f"ESCALATED from rupee-rank #{issue.rupee_rank}" if issue.escalated else ""
        print(
            f"{display_rank:>4} {issue.issue_category:25s} {issue.typical_severity:8s} "
            f"Rs.{issue.total_expected_liability_inr:>18,.2f} {issue.affected_vehicle_count:>9d}  {notes}"
        )
