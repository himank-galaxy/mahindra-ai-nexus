"""
Thin wrapper around the OpenAI-compatible chat completions API. Mirrors
Predictive_Early_Warning_Service/copilot/llm_client.py exactly - same
gateway convention, same "exactly one system message" constraint already
confirmed against the real endpoint. Credentials come from warranty_config.py
(loaded from .env) - never hardcoded here.
"""

from __future__ import annotations

from openai import OpenAI

from warranty_config import (
    LLM_NAME,
    OPENAI_API_BASE_URL,
    OPENAI_API_KEY,
    RAG_MAX_RESPONSE_TOKENS,
    RAG_TEMPERATURE,
)


class RagNotConfiguredError(RuntimeError):
    """Raised when OPENAI_API_BASE_URL / OPENAI_API_KEY / LLM_NAME are missing."""


def _get_client() -> OpenAI:
    if not (OPENAI_API_BASE_URL and OPENAI_API_KEY and LLM_NAME):
        raise RagNotConfiguredError(
            "RAG-answering LLM is not configured. Set OPENAI_API_BASE_URL, "
            "OPENAI_API_KEY, and LLM_NAME in Warranty_Predictive_Service/.env."
        )
    return OpenAI(base_url=OPENAI_API_BASE_URL, api_key=OPENAI_API_KEY)


def ask(messages: list[dict[str, str]]) -> str:
    """messages: a plain OpenAI-style chat message list, already
    assembled by the caller. Returns the assistant's reply text."""

    client = _get_client()

    response = client.chat.completions.create(
        model=LLM_NAME,
        messages=messages,
        temperature=RAG_TEMPERATURE,
        max_tokens=RAG_MAX_RESPONSE_TOKENS,
    )

    return response.choices[0].message.content or ""
