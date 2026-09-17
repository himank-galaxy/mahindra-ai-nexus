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


class OpenAiProvider:
    """LLM-backed provider for an OpenAI-compatible chat completions endpoint.

    The ``LlmProvider`` protocol only carries a single flat prompt string
    (no structured system/user/history messages), so callers are
    responsible for flattening everything — instructions, case file,
    conversation history, question — into one prompt before calling
    ``complete()``. Sent here as a single user-role message.
    """

    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def complete(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
