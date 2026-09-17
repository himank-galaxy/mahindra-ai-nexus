"""Data-driven early-warning helper for API explanations."""

from __future__ import annotations


def warnings(latest: dict[str, float]) -> list[str]:
    result: list[str] = []
    if latest["delivery_delay_days"] > 3:
        result.append("Delivery delay is above the three-day operating threshold.")
    if latest["cancellation_rate"] > 0.12:
        result.append("Cancellation rate is above the 12% intervention threshold.")
    if latest["finance_approval_rate"] < 0.55:
        result.append("Finance approval rate is below the 55% operating threshold.")
    return result
