"""Discover numeric business measures; metadata never restricts graph membership."""

from dataclasses import dataclass

import numpy as np
from sqlalchemy import Boolean, Float, Integer, Numeric, Table


@dataclass(frozen=True)
class MobilityFeature:
    key: str
    label: str
    unit: str
    aggregation: str
    polarity: str
    weight: str | None = None


AVERAGE_WEIGHTS = {
    "avg_lead_engagement_score": "lead_count",
    "avg_followup_response_minutes": "customer_response_count",
    "avg_allocation_wait_hours": "allocated_vehicle_count",
    "avg_delivery_delay_days": "delayed_delivery_count",
}

# Business-reviewed polarity calls that don't follow a generalizable naming
# pattern (unlike the keyword heuristic below) - checked first, so these
# take priority over any keyword match.
EXPLICIT_POLARITY: dict[str, str] = {
    "finance_application_count": "higher",
    "lead_count": "higher",
    "booking_count": "higher",
    "delivered_vehicle_count": "higher",
    "allocated_vehicle_count": "higher",
    "test_drive_requested_count": "higher",
    "warranty_claim_count": "lower",
    "warranty_claim_amount_inr": "lower",
}


def feature_metadata(key: str, available: set[str]) -> MobilityFeature:
    label = key.removeprefix("avg_").removesuffix("_inr").replace("_", " ").title()
    if key.startswith("avg_"):
        label = f"Average {label}"
    unit = next(
        (
            unit
            for suffix, unit in (
                ("_inr", "INR"),
                ("_hours", "hours"),
                ("_minutes", "minutes"),
                ("_days", "days"),
                ("_rate", "ratio"),
                ("_score", "score"),
                ("_count", "count"),
            )
            if key.endswith(suffix)
        ),
        "number",
    )
    weight = AVERAGE_WEIGHTS.get(key)
    if weight not in available:
        weight = None
    aggregation = (
        "weighted regional mean" if weight else ("national sum" if unit in {"INR", "count"} else "regional mean")
    )
    if key in EXPLICIT_POLARITY:
        polarity = EXPLICIT_POLARITY[key]
    elif any(
        token in key
        for token in (
            "delay",
            "wait",
            "cancellation",
            "rejected",
            "no_show",
            "unscheduled_repair",
            "response_minutes",
            "approval_tat",
        )
    ):
        polarity = "lower"
    elif any(token in key for token in ("completed", "engagement", "booking_value", "approved_count")):
        polarity = "higher"
    else:
        polarity = "neutral"
    return MobilityFeature(key, label, unit, aggregation, polarity, weight)


def discover_features(table: Table) -> tuple[MobilityFeature, ...]:
    available = set(table.c.keys())
    return tuple(
        feature_metadata(column.name, available)
        for column in table.c
        if isinstance(column.type, (Integer, Float, Numeric))
        and not isinstance(column.type, Boolean)
        and not column.primary_key
        and not column.foreign_keys
        and not column.name.endswith(("_id", "_version"))
        and column.name not in {"id", "generator_version"}
        and not column.name.startswith(("true_", "latent_", "scenario_", "is_anomaly"))
    )


def aggregate_feature(feature: MobilityFeature, rows: list[dict]) -> float:
    values = np.array([float(row[feature.key]) if row[feature.key] is not None else np.nan for row in rows])
    if not np.isfinite(values).all():
        return float("nan")
    if feature.weight:
        weights = np.array([float(row[feature.weight] or 0) for row in rows])
        return float(np.average(values, weights=weights)) if weights.sum() > 0 else 0.0
    return float(values.sum() if feature.aggregation == "national sum" else values.mean())


def display_value(feature: MobilityFeature, value: float) -> str:
    if feature.unit == "INR":
        return f"₹{value:,.0f}"
    if feature.unit == "ratio":
        return f"{value * 100:.1f}%"
    if feature.unit in {"hours", "minutes", "days"}:
        return f"{value:,.1f} {feature.unit}"
    return f"{value:,.0f}" if feature.unit == "count" else f"{value:,.3f}"


def trend_percent(value: float, previous: float) -> float | None:
    return (value - previous) / abs(previous) * 100 if previous else (0.0 if value == 0 else None)


def trend_tone(feature: MobilityFeature, value: float, previous: float) -> str:
    if feature.polarity == "neutral" or value == previous:
        return "default"
    improving = value > previous if feature.polarity == "higher" else value < previous
    return "success" if improving else "danger"
