"""
Durable storage for completed causal investigation results.

Before this module existed, a completed investigation's graph/classification
result only lived in api/main.py's in-memory _JOBS dict - if the API
process restarted (which happens routinely during development, and would
happen in any real deployment too), every previously-run investigation
became permanently unreachable, even though the warning record itself
survived (warnings_store.py already persists to disk).

This mirrors warnings_store.py's own pattern: one JSON file per warning,
this time under investigations/, keyed by warning_id (not job_id, since a
warning conceptually has ONE current investigation result, and a user
reopening an old warning should see that result regardless of which
in-memory job produced it or whether the API has restarted since).

The Copilot's context_builder.py depends on this being durable - it must
be able to explain a warning's investigation even if the API was restarted
after that investigation ran.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pews_config import SERVICE_ROOT

INVESTIGATIONS_DIR = os.path.join(SERVICE_ROOT, "investigations")


def _path_for(warning_id: str) -> str:
    return os.path.join(INVESTIGATIONS_DIR, f"{warning_id}.json")


def save_investigation(warning_id: str, result: dict[str, Any]) -> None:
    """
    Persist a completed investigation's result (the same dict shape
    api/main.py builds for job.result) so it survives an API restart.
    """

    os.makedirs(INVESTIGATIONS_DIR, exist_ok=True)

    payload = {
        **result,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(_path_for(warning_id), "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def load_investigation(warning_id: str) -> dict[str, Any] | None:
    path = _path_for(warning_id)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)
