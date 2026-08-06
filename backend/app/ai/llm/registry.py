"""Provider selection from ``Settings.ai_provider``."""

from __future__ import annotations

import logging

from app.ai.llm.provider import LlmProvider, RuleBasedProvider
from app.core.config import Settings

logger = logging.getLogger(__name__)


def get_llm_provider(settings: Settings) -> LlmProvider:
    """Return the active provider; only the rule-based one is wired today."""
    if settings.ai_provider != "rule":
        logger.warning(
            "AI provider '%s' is not wired yet; falling back to the rule-based provider.",
            settings.ai_provider,
        )
    return RuleBasedProvider()
