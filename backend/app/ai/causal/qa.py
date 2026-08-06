"""Ask-Causal-Twin matcher over the seeded ``causal_qa`` table."""

from __future__ import annotations

from collections.abc import Iterable

MOBILITY_FALLBACK = (
    "The causal twin currently answers the suggested questions — pick one to see a "
    "causal breakdown with a recommended action."
)


def match_answer(
    question: str,
    candidates: Iterable[tuple[str, str]],
    fallback: str,
) -> str:
    """Case-insensitive exact match of a question against (question, answer) pairs."""
    normalized = " ".join(question.lower().split())
    for candidate_question, answer in candidates:
        if normalized == " ".join(candidate_question.lower().split()):
            return answer
    return fallback
