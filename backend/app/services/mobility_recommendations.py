"""Evidence-derived investigative actions for any discovered mobility measure."""

from dataclasses import dataclass

from app.ai.causal.graph_builder import format_duration_minutes


@dataclass(frozen=True)
class DriverSummary:
    label: str
    score: float
    sign: str
    lag_minutes: int


def compute_priority_score(*, top_driver_strength: float, current_value: float, mean: float, std: float) -> float:
    distance = 0.0 if std <= 0 else min(abs(current_value - mean) / std, 3.0)
    return top_driver_strength * (1.0 + distance)


async def recommend_action(
    llm,
    *,
    metric: str,
    label: str,
    current_value: float,
    trend_pct: float | None,
    trend_label: str,
    drivers: list[DriverSummary],
) -> str:
    # These actions are assembled from evidence, so an LLM failure cannot hide node
    # statistics or introduce an unsupported intervention for an unfamiliar feature.
    if not drivers:
        return (
            f"Monitor {label} and review the underlying records. No incoming relationship passed "
            "the current statistical checks, so this graph does not support a driver-specific intervention."
        )
    driver = max(drivers, key=lambda item: abs(item.score))
    movement = "the same direction" if driver.score >= 0 else "opposite directions"
    return (
        f"Investigate {driver.label}, the strongest observed incoming relationship for {label} "
        f"(strength {driver.score:+.2f}, lag about {format_duration_minutes(driver.lag_minutes)}). "
        f"They move in {movement} in this analysis. Verify the relationship in business records "
        "and a controlled trial before changing operations; this score does not estimate an intervention's impact."
    )
