"""
Persists a run's metadata (and, once LPCMCI is actually executed in a
later phase, its graph) as local JSON files under
Causal_Discovery_Service/runs/<domain>/<run_id>/.

No database writes happen anywhere in this module - see
IMPLEMENTATION_PLAN.md section 1 and 12.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any

from config import RUNS_OUTPUT_ROOT


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def new_run_id() -> str:
    return uuid.uuid4().hex


def run_output_dir(domain: str, run_id: str) -> str:
    return os.path.join(RUNS_OUTPUT_ROOT, domain, run_id)


def write_run_metadata(
    domain: str, run_id: str, metadata: dict[str, Any]
) -> str:
    """
    Write run_metadata.json for one run. Returns the file path written.
    """

    output_dir = run_output_dir(domain, run_id)
    os.makedirs(output_dir, exist_ok=True)

    metadata_with_timestamp = {
        "run_id": run_id,
        "written_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }

    output_path = os.path.join(output_dir, "run_metadata.json")
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(metadata_with_timestamp, file, indent=2, default=_json_default)

    return output_path


def write_graph(domain: str, run_id: str, graph_dict: dict[str, Any]) -> str:
    """
    Write graph.json for one run. Only meaningful once LPCMCI has actually
    been executed - not called in this phase.
    """

    output_dir = run_output_dir(domain, run_id)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "graph.json")
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(graph_dict, file, indent=2, default=_json_default)

    return output_path
