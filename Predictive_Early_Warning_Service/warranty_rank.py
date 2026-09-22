"""
Fleet-wide ranking of predicted issues by total expected liability, per
docs/data_required_for_warranty_predictive_model.md section 5:

    priority = failure probability x cost per claim x number of affected vehicles
             = total expected fleet-wide liability

Implemented as a direct sum of each vehicle's own
(probability x cost x eligibility) rather than one shared average
probability x a count - mathematically the same total, but using each
vehicle's real predicted probability rather than a fleet-average
approximation. Severity acts as a documented escalation flag on top of
the rupee ranking (not folded into the same number) - exactly as
section 5 specifies, so a cheap-but-safety-critical issue doesn't get
silently buried under rupee-ranked noise-type issues.

Two entry points:
- rank_fleet_issues() - recomputes predictions live (~25s for the whole
  fleet - see predict.py's batching). Used by this module's own CLI and
  right after a fresh scheduler tick.
- rank_from_stored_predictions() - aggregates from whatever
  scheduler.py last persisted (predictions_store.py) - fast, no model
  calls. This is what the API uses (see api/main.py): an API request
  must never trigger a ~25s live recomputation in the request path, the
  same principle PEWS's API follows (it only ever reads what
  scheduler.py already computed).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

import warranty_config
from warranty_predict import load_prediction_context, predict_for_fleet_in_context
from warranty_predictions_store import load_all_predictions

# A vehicle counts as "affected" by an issue only above this probability -
# otherwise every vehicle at some negligible nonzero probability would
# inflate the affected-count for every issue.
AFFECTED_PROBABILITY_THRESHOLD = 0.30

_SEVERITY_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}


@dataclass(frozen=True)
class RankedIssue:
    issue_category: str
    component_category: str
    total_expected_liability_inr: float
    affected_vehicle_count: int
    fleet_size: int
    typical_severity: str
    low_confidence: bool
    rupee_rank: int
    escalated: bool  # True if a HIGH-severity issue was pulled above its raw rupee rank


def _typical_severity(issue_category: str, service_events: pd.DataFrame) -> str:
    matches = service_events[service_events["issue_category"] == issue_category]
    if matches.empty:
        return "NONE"
    return str(matches["severity"].value_counts().idxmax())


def _aggregate_and_rank(
    vehicle_predictions: dict[str, list[dict]],
    fleet_size: int,
    severities: dict[str, str],
) -> list[RankedIssue]:
    totals: dict[str, float] = {}
    affected_counts: dict[str, int] = {}
    component_by_issue: dict[str, str] = {}
    low_confidence_by_issue: dict[str, bool] = {}

    for predictions in vehicle_predictions.values():
        for prediction in predictions:
            if not prediction["eligibility"]["is_eligible"]:
                continue  # not Mahindra's liability - correctly excluded from the ranking entirely
            issue = prediction["issue_category"]
            totals[issue] = totals.get(issue, 0.0) + prediction["expected_liability_inr"]
            if prediction["probability"] >= AFFECTED_PROBABILITY_THRESHOLD:
                affected_counts[issue] = affected_counts.get(issue, 0) + 1
            component_by_issue[issue] = prediction["component_category"]
            low_confidence_by_issue[issue] = prediction["low_confidence"]

    rupee_ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    rupee_rank_by_issue = {issue: rank + 1 for rank, (issue, _) in enumerate(rupee_ordered)}

    # Escalation: a HIGH-severity issue is pulled to sit above every
    # MEDIUM/LOW-severity issue ranked below it, without changing the
    # relative rupee order within the same severity tier - the rupee
    # figure itself is never altered, only the display order.
    def sort_key(item: tuple[str, float]) -> tuple[int, float]:
        issue, total = item
        return (-_SEVERITY_RANK.get(severities.get(issue, "NONE"), 0), -total)

    escalated_ordered = sorted(totals.items(), key=sort_key)

    ranked: list[RankedIssue] = []
    for issue, total in escalated_ordered:
        raw_rank = rupee_rank_by_issue[issue]
        display_rank = len(ranked) + 1
        ranked.append(
            RankedIssue(
                issue_category=issue,
                component_category=component_by_issue[issue],
                total_expected_liability_inr=total,
                affected_vehicle_count=affected_counts.get(issue, 0),
                fleet_size=fleet_size,
                typical_severity=severities.get(issue, "NONE"),
                low_confidence=low_confidence_by_issue[issue],
                rupee_rank=raw_rank,
                escalated=display_rank < raw_rank,
            )
        )

    return ranked


def rank_fleet_issues() -> list[RankedIssue]:
    """Recomputes live - see module docstring for when to use this vs.
    rank_from_stored_predictions()."""
    context = load_prediction_context()
    delivered_vehicle_ids = context.deliveries["vehicle_id"].astype(str).tolist()
    fleet_predictions = predict_for_fleet_in_context(context)

    vehicle_predictions = {
        vehicle_id: [asdict(p) for p in predictions] for vehicle_id, predictions in fleet_predictions.items()
    }
    severities = {
        issue: _typical_severity(issue, context.service_events)
        for predictions in vehicle_predictions.values()
        for issue in {p["issue_category"] for p in predictions}
    }

    return _aggregate_and_rank(vehicle_predictions, len(delivered_vehicle_ids), severities)


def rank_from_stored_predictions() -> list[RankedIssue]:
    """Fast path - aggregates whatever scheduler.py last persisted. No
    model calls, no ~25s wait - this is what the API should call."""
    records = load_all_predictions()
    vehicle_predictions = {record["vehicle_id"]: record["predictions"] for record in records}

    service_events = pd.read_csv(warranty_config.SERVICE_EVENTS_PATH)
    severities = {
        issue: _typical_severity(issue, service_events)
        for predictions in vehicle_predictions.values()
        for issue in {p["issue_category"] for p in predictions}
    }

    return _aggregate_and_rank(vehicle_predictions, len(vehicle_predictions), severities)


if __name__ == "__main__":
    ranked = rank_fleet_issues()
    print(f"{'Rank':>4} {'Issue':25s} {'Severity':8s} {'Total Expected Liability':>25s} {'Affected':>9s}  Notes")
    for display_rank, issue in enumerate(ranked[:25], start=1):
        notes = []
        if issue.escalated:
            notes.append(f"ESCALATED from rupee-rank #{issue.rupee_rank}")
        if issue.low_confidence:
            notes.append("LOW-CONFIDENCE")
        print(
            f"{display_rank:>4} {issue.issue_category:25s} {issue.typical_severity:8s} "
            f"Rs.{issue.total_expected_liability_inr:>18,.2f} {issue.affected_vehicle_count:>9d}  "
            f"{', '.join(notes)}"
        )
