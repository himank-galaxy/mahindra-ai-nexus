from app.ai.prompts.simulation_summary import (
    build_prompt,
    parse_polished_summary,
    polish_is_grounded,
)

ORIGINAL = {
    "scenario": "Baseline FY26 — West / XUV700",
    "inputs_summary": "Discount 3.0%, exchange bonus 25,000.",
    "baseline": "16% predicted booking conversion.",
    "predicted_outcome": "Booking uplift 40%, net revenue impact ₹10 Cr.",
    "major_drivers": ["Completed test drive", "Budget fit"],
    "trade_off": "Higher bonus raises revenue but reduces margin.",
    "recommendation": "Deploy the bonus in West.",
    "confidence": "48% (low).",
    "risk": "No historical bonus variation exists.",
}


def test_build_prompt_includes_the_summary_json() -> None:
    prompt = build_prompt('{"scenario": "x"}')

    assert '{"scenario": "x"}' in prompt
    assert "Do NOT invent" in prompt


def test_parse_polished_summary_accepts_valid_json() -> None:
    raw = (
        '{"scenario": "a", "inputs_summary": "b", "baseline": "c", "predicted_outcome": "d", '
        '"major_drivers": ["x"], "trade_off": "e", "recommendation": "f", "confidence": "g", "risk": "h"}'
    )

    parsed = parse_polished_summary(raw)

    assert parsed is not None
    assert parsed["major_drivers"] == ["x"]


def test_parse_polished_summary_strips_code_fence() -> None:
    raw = (
        "```json\n"
        '{"scenario": "a", "inputs_summary": "b", "baseline": "c", "predicted_outcome": "d", '
        '"major_drivers": [], "trade_off": "e", "recommendation": "f", "confidence": "g", "risk": "h"}\n'
        "```"
    )

    assert parse_polished_summary(raw) is not None


def test_parse_polished_summary_rejects_missing_keys() -> None:
    assert parse_polished_summary('{"scenario": "a"}') is None


def test_parse_polished_summary_rejects_invalid_json() -> None:
    assert parse_polished_summary("not json at all") is None


def test_polish_is_grounded_accepts_reworded_text_with_same_numbers() -> None:
    polished = dict(ORIGINAL)
    polished["predicted_outcome"] = "We project a 40% uplift in bookings and ₹10 Cr in additional revenue."

    assert polish_is_grounded(ORIGINAL, polished) is True


def test_polish_is_grounded_rejects_a_dropped_number() -> None:
    polished = dict(ORIGINAL)
    polished["predicted_outcome"] = "Bookings will rise and revenue will improve."  # 40% and ₹10 Cr both gone

    assert polish_is_grounded(ORIGINAL, polished) is False


def test_polish_is_grounded_rejects_an_altered_number() -> None:
    polished = dict(ORIGINAL)
    polished["predicted_outcome"] = "Booking uplift 90%, net revenue impact ₹10 Cr."  # 40 -> 90

    assert polish_is_grounded(ORIGINAL, polished) is False


def test_polish_is_grounded_ignores_sentence_punctuation_around_a_number() -> None:
    """Regression: a naive "[\\d,]*" number regex swallows a sentence's
    trailing comma ("40,000, campaign" -> "40,000,"), producing a false
    mismatch against the same number written without trailing punctuation
    elsewhere — this must not cause a real LLM rewording to be rejected."""
    original = dict(ORIGINAL)
    original["inputs_summary"] = "Discount 5.0%, exchange bonus 40,000, campaign spend ₹2.0 Cr."
    polished = dict(original)
    polished["inputs_summary"] = "5.0% discount, ₹40,000 exchange bonus, ₹2.0 Cr campaign spend."

    assert polish_is_grounded(original, polished) is True


def test_polish_is_grounded_rejects_a_changed_driver_set() -> None:
    polished = dict(ORIGINAL)
    polished["major_drivers"] = ["Completed test drive", "Discount %"]  # "Budget fit" dropped

    assert polish_is_grounded(ORIGINAL, polished) is False
