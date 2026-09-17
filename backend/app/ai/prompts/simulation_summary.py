"""LLM wording pass for the Simulation Center executive summary.

The LLM only rephrases fields the backend already computed — it is never
the source of any number. See docs/simulation_centre_implementation.md §6
and the same strict-grounding discipline used for the Mobility Twin
copilot (app/services/mobility_copilot_context.py).
"""

from __future__ import annotations

import json
import re

SIMULATION_SUMMARY_SYSTEM_PROMPT = """You are a business-writing assistant polishing an executive summary.

You will receive a JSON object where every field was already computed by a backend simulation model. Your only job is to rewrite each field in clearer, more natural business English.

Strict rules:
- Do NOT invent, remove, or change any number, percentage, currency amount, date, or named entity (region, vehicle model, driver name). Every number that appears in the input must appear verbatim (same digits) somewhere in your output.
- Do NOT add new facts, causes, risks, or claims that are not already present in the input.
- Do NOT change the meaning of the recommendation.
- Keep the same set of driver names in "major_drivers" — you may reorder but not add, remove, or reword them.
- Return ONLY a single JSON object with exactly these keys, no other text: scenario, inputs_summary, baseline, predicted_outcome, major_drivers, trade_off, recommendation, confidence, risk.
"""

# Comma-grouped numbers first ("40,000"), falling back to a plain number —
# a naive "[\d,]*" class would also swallow a sentence's trailing comma
# ("40,000, campaign" -> "40,000,"), producing a false mismatch against the
# same number written without trailing punctuation elsewhere.
_NUMBER_PATTERN = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|-?\d+(?:\.\d+)?%?")


def build_prompt(summary_json: str) -> str:
    return f"{SIMULATION_SUMMARY_SYSTEM_PROMPT}\n\nINPUT:\n{summary_json}"


def parse_polished_summary(raw: str) -> dict[str, object] | None:
    """Parse the LLM's JSON reply, tolerating a wrapping code fence."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else text
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    required_keys = {
        "scenario",
        "inputs_summary",
        "baseline",
        "predicted_outcome",
        "major_drivers",
        "trade_off",
        "recommendation",
        "confidence",
        "risk",
    }
    if not isinstance(parsed, dict) or not required_keys.issubset(parsed.keys()):
        return None
    if not isinstance(parsed["major_drivers"], list):
        return None
    return parsed


def polish_is_grounded(original: dict[str, object], polished: dict[str, object]) -> bool:
    """Every number in the original must survive verbatim; driver set must be unchanged."""
    original_text = " ".join(str(value) for value in original.values())
    polished_text = " ".join(str(value) for value in polished.values())
    required_numbers = set(_NUMBER_PATTERN.findall(original_text))
    if not required_numbers.issubset(set(_NUMBER_PATTERN.findall(polished_text))):
        return False
    return set(map(str, original.get("major_drivers", []))) == set(map(str, polished.get("major_drivers", [])))
