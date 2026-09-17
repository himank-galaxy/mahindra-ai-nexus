"""Shared confidence contract for every simulation engine.

Two honest paths only — no engine invents its own scheme (see
docs/simulation_centre_implementation.md §5):

- ``calibrated_heuristic``: the engine is a documented business-rule
  function, not fit on observed outcome variation (e.g. Auto Sales'
  incentive-response layer, Credit Pricing's closure probability). Capped
  at a low ceiling regardless of inputs, because there is no statistical
  basis to claim more.
- ``trained_model``: the engine is a calibrated classifier/regressor fit
  on real historical outcomes. Confidence reflects the model's own
  predicted-probability margin, discounted for scenarios that extrapolate
  outside the observed training range and for thin training cohorts.

Both paths return ``(confidence, confidence_band)``; the caller records
``confidence_basis`` itself so the API response is explicit about which
path produced the number.
"""

from __future__ import annotations

CALIBRATED_HEURISTIC_CEILING = 70
TRAINED_MODEL_CEILING = 97


def _band(confidence: int) -> str:
    if confidence >= 75:
        return "high"
    if confidence >= 55:
        return "medium"
    return "low"


def calibrated_heuristic_confidence(
    *,
    base: int,
    penalty: int = 0,
    ceiling: int = CALIBRATED_HEURISTIC_CEILING,
) -> tuple[int, str]:
    """Confidence for a documented business-rule engine, not a trained model.

    ``base`` and ``penalty`` are the engine's own explainable inputs (e.g.
    higher follow-up intensity or region propensity raising ``base``); the
    ceiling keeps the result from ever implying more certainty than a
    calibrated heuristic can honestly claim.
    """
    value = max(0, min(ceiling, base - penalty))
    return value, _band(value)


def trained_model_confidence(
    *,
    predicted_probability: float,
    in_training_range: bool,
    cohort_sample_size: int,
    thin_cohort_threshold: int = 30,
    ceiling: int = TRAINED_MODEL_CEILING,
) -> tuple[int, str]:
    """Confidence for a calibrated classifier/regressor fit on real outcomes.

    ``predicted_probability`` is the model's own calibrated output for the
    predicted class/outcome (0-1); confidence rewards being decisive (far
    from 0.5) and penalizes scenarios that extrapolate beyond what the
    training cohort observed, or cohorts too thin to trust.
    """
    margin = abs(predicted_probability - 0.5) * 2  # 0 (coin flip) .. 1 (certain)
    value = 50 + round(margin * (ceiling - 50))
    if not in_training_range:
        value -= 15
    if cohort_sample_size < thin_cohort_threshold:
        value -= 10
    value = max(0, min(ceiling, value))
    return value, _band(value)
