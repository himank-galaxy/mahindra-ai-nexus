from app.ai.simulation.confidence import (
    calibrated_heuristic_confidence,
    trained_model_confidence,
)


def test_calibrated_heuristic_confidence_is_capped_regardless_of_base() -> None:
    value, band = calibrated_heuristic_confidence(base=200)

    assert value == 70  # the ceiling — below the "high" band by design
    assert band == "medium"


def test_calibrated_heuristic_confidence_applies_penalty() -> None:
    value, band = calibrated_heuristic_confidence(base=60, penalty=20)

    assert value == 40
    assert band == "low"


def test_calibrated_heuristic_confidence_never_goes_negative() -> None:
    value, _band = calibrated_heuristic_confidence(base=10, penalty=50)

    assert value == 0


def test_trained_model_confidence_rewards_decisive_predictions() -> None:
    decisive, decisive_band = trained_model_confidence(
        predicted_probability=0.95,
        in_training_range=True,
        cohort_sample_size=500,
    )
    coin_flip, coin_flip_band = trained_model_confidence(
        predicted_probability=0.5,
        in_training_range=True,
        cohort_sample_size=500,
    )

    assert decisive > coin_flip
    assert decisive_band == "high"
    assert coin_flip_band == "low"


def test_trained_model_confidence_penalizes_extrapolation_and_thin_cohorts() -> None:
    in_range, _ = trained_model_confidence(
        predicted_probability=0.9,
        in_training_range=True,
        cohort_sample_size=500,
    )
    out_of_range, _ = trained_model_confidence(
        predicted_probability=0.9,
        in_training_range=False,
        cohort_sample_size=500,
    )
    thin_cohort, _ = trained_model_confidence(
        predicted_probability=0.9,
        in_training_range=True,
        cohort_sample_size=5,
    )

    assert out_of_range < in_range
    assert thin_cohort < in_range
