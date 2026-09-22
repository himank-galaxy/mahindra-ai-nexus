"""
Thin wrapper around the OpenAI-compatible chat completions API. Credentials
and endpoint come from environment variables (via pews_config.py, loaded
from .env) - never hardcoded here. See copilot/README.md for how to
configure OPENAI_API_BASE_URL / OPENAI_API_KEY / LLM_NAME.
"""

from __future__ import annotations

from openai import OpenAI

from pews_config import (
    COPILOT_MAX_RESPONSE_TOKENS,
    COPILOT_TEMPERATURE,
    LLM_NAME,
    OPENAI_API_BASE_URL,
    OPENAI_API_KEY,
)


class CopilotNotConfiguredError(RuntimeError):
    """Raised when OPENAI_API_BASE_URL / OPENAI_API_KEY / LLM_NAME are missing."""


def _get_client() -> OpenAI:
    if not (OPENAI_API_BASE_URL and OPENAI_API_KEY and LLM_NAME):
        raise CopilotNotConfiguredError(
            "Copilot LLM is not configured. Set OPENAI_API_BASE_URL, "
            "OPENAI_API_KEY, and LLM_NAME in Predictive_Early_Warning_Service/.env "
            "(see copilot/README.md)."
        )

    return OpenAI(base_url=OPENAI_API_BASE_URL, api_key=OPENAI_API_KEY)


def ask(messages: list[dict[str, str]]) -> str:
    """
    messages: a plain OpenAI-style chat message list, already assembled by
    the caller ([system prompt] + [case file as a system/user message] +
    [prior turns] + [new user question]).

    Returns the assistant's reply text. Raises CopilotNotConfiguredError if
    the LLM environment variables are missing, or the underlying openai
    SDK's own exception types on a real API failure (left uncaught here so
    the API layer can decide how to surface it).
    """

    client = _get_client()

    response = client.chat.completions.create(
        model=LLM_NAME,
        messages=messages,
        temperature=COPILOT_TEMPERATURE,
        max_tokens=COPILOT_MAX_RESPONSE_TOKENS,
    )

    return response.choices[0].message.content or ""
