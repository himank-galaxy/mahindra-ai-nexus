"""
Reads and writes Copilot conversation history as local JSON files -
one file per warning_id, same pattern as warnings_store.py.

Scope: one conversation per warning. Switching to a different warning's
investigation page starts a fresh conversation - see
IMPLEMENTATION_PLAN.md section 4.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from pews_config import COPILOT_CONVERSATIONS_DIR, COPILOT_MAX_HISTORY_TURNS


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    content: str
    timestamp: str


@dataclass
class Conversation:
    warning_id: str
    turns: list[Turn] = field(default_factory=list)


def _path_for(warning_id: str) -> str:
    return os.path.join(COPILOT_CONVERSATIONS_DIR, f"{warning_id}.json")


def load_conversation(warning_id: str) -> Conversation:
    path = _path_for(warning_id)
    if not os.path.exists(path):
        return Conversation(warning_id=warning_id, turns=[])

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    return Conversation(
        warning_id=data["warning_id"],
        turns=[Turn(**t) for t in data.get("turns", [])],
    )


def _save(conversation: Conversation) -> None:
    os.makedirs(COPILOT_CONVERSATIONS_DIR, exist_ok=True)
    with open(_path_for(conversation.warning_id), "w", encoding="utf-8") as file:
        json.dump(asdict(conversation), file, indent=2)


def append_turn(warning_id: str, role: str, content: str) -> Conversation:
    conversation = load_conversation(warning_id)
    conversation.turns.append(
        Turn(role=role, content=content, timestamp=datetime.now(timezone.utc).isoformat())
    )
    _save(conversation)
    return conversation


def recent_turns_for_prompt(warning_id: str) -> list[Turn]:
    """
    The full case-file context is always resent every turn (it's static
    per investigation, cheap to include) - only the CONVERSATION history
    itself needs trimming to control token cost as a chat grows long.
    """

    conversation = load_conversation(warning_id)
    return conversation.turns[-COPILOT_MAX_HISTORY_TURNS:]


def clear_conversation(warning_id: str) -> None:
    path = _path_for(warning_id)
    if os.path.exists(path):
        os.remove(path)
