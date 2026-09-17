"""Provider selection from ``Settings.ai_provider``."""

from __future__ import annotations

import logging

from app.ai.llm.provider import LlmProvider, OpenAiProvider, RuleBasedProvider
from app.core.config import Settings

logger = logging.getLogger(__name__)


def get_llm_provider(settings: Settings) -> LlmProvider:
    """Return the active provider.

    ``ai_provider="openai"`` is only honored when the base URL, API key, and
    model are all configured — otherwise this falls back to the rule-based
    provider (with a warning) rather than constructing a client that would
    fail on first use.
    """
    if settings.ai_provider == "openai":
        if settings.openai_base_url and settings.openai_api_key and settings.openai_model:
            return OpenAiProvider(
                base_url=settings.openai_base_url,
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )
        logger.warning(
            "ai_provider='openai' but openai_base_url/openai_api_key/openai_model are not "
            "all configured; falling back to the rule-based provider.",
        )
    return RuleBasedProvider()
