"""LLM provider seam: protocol + deterministic rule-based provider."""

from __future__ import annotations

from typing import Protocol

from app.ai.prompts.copilot_fallback import COPILOT_FALLBACK


class LlmProvider(Protocol):
    """Completion contract shared by rule-based and LLM-backed providers."""

    async def complete(self, prompt: str) -> str: ...


class RuleBasedProvider:
    """Deterministic stand-in until an LLM provider is wired."""

    async def complete(self, prompt: str) -> str:
        return str(COPILOT_FALLBACK["answer"])
