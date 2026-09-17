"""Copilot engine: protocol + deterministic rule-based implementation."""

from __future__ import annotations

from typing import Protocol

from app.ai.copilot.intents import INTENT_RULES
from app.ai.prompts.copilot_fallback import COPILOT_FALLBACK


class CopilotEngine(Protocol):
    """Answers analytics prompts with analysis + SQL + Python + action."""

    def respond(self, prompt: str) -> dict[str, object]: ...


class RuleBasedCopilot:
    """Deterministic keyword-intent copilot (port of ``copilot.ts``).

    Swappable for an LLM-backed engine behind ``Settings.ai_provider``
    without touching the service layer.
    """

    def respond(self, prompt: str) -> dict[str, object]:
        lowered = prompt.lower()
        for matches, result in INTENT_RULES:
            if matches(lowered):
                return dict(result)
        return dict(COPILOT_FALLBACK)
