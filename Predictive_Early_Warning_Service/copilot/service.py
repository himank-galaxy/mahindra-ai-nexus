"""
Orchestrates one Copilot turn: load warning + investigation -> build case
file -> assemble prompt with conversation history -> call the LLM ->
persist both turns -> return the answer.

Kept separate from api/main.py the same way investigate.py is kept
separate from the API layer - this module has no FastAPI dependency and
could be tested/reused on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

COPILOT_ROOT = Path(__file__).resolve().parent
PREW_ROOT = COPILOT_ROOT.parent
if str(PREW_ROOT) not in sys.path:
    sys.path.insert(0, str(PREW_ROOT))

from investigation_store import load_investigation  # noqa: E402

from context_builder import build_case_file  # noqa: E402
from conversation_store import append_turn, recent_turns_for_prompt  # noqa: E402
from llm_client import ask  # noqa: E402
from prompts import SYSTEM_PROMPT  # noqa: E402


class NoInvestigationYetError(RuntimeError):
    """Raised when a user tries to chat before any investigation has been run."""


def ask_copilot(warning: dict[str, Any], user_message: str) -> str:
    """
    warning: the Warning record's __dict__.
    Returns the assistant's reply text (also persisted to
    copilot_conversations/<warning_id>.json, alongside the user's turn).
    """

    warning_id = warning["warning_id"]

    investigation = load_investigation(warning_id)
    case_file = build_case_file(warning, investigation)

    prior_turns = recent_turns_for_prompt(warning_id)

    # This LLM gateway requires exactly one system message, at the start -
    # a second system message is rejected outright (confirmed against the
    # real endpoint). So the case file is folded into the same system
    # message as the instructions, rather than sent as a separate one.
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}\n\nCASE FILE FOR THIS WARNING:\n\n{case_file}",
        },
    ]
    for turn in prior_turns:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": user_message})

    # Both turns are only persisted AFTER a successful reply, together -
    # if the LLM call fails, nothing is saved, so a failed attempt doesn't
    # leave an unanswered question permanently stuck in the transcript.
    reply = ask(messages)

    append_turn(warning_id, "user", user_message)
    append_turn(warning_id, "assistant", reply)

    return reply
