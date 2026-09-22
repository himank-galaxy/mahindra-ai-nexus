"""
Durable storage for auto-generated AI Explanation reports - mirrors
investigation_store.py exactly (one JSON file per warning_id, under
explanations/), for the same reason: without this, a generated
explanation would only ever exist for as long as the API process that
generated it stays up, and reopening an old warning after a restart would
silently lose it even though the investigation itself survived.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pews_config import SERVICE_ROOT

EXPLANATIONS_DIR = os.path.join(SERVICE_ROOT, "explanations")


def _path_for(warning_id: str) -> str:
    return os.path.join(EXPLANATIONS_DIR, f"{warning_id}.json")


def save_explanation(warning_id: str, result: dict[str, Any]) -> None:
    os.makedirs(EXPLANATIONS_DIR, exist_ok=True)

    payload = {
        **result,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(_path_for(warning_id), "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def load_explanation(warning_id: str) -> dict[str, Any] | None:
    path = _path_for(warning_id)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)
