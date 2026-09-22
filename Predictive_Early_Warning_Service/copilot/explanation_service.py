"""
Orchestrates the full auto-generated AI Explanation report: deterministic
sections from explanation_builder.py, plus one LLM call for the "What To
Do Next" section (constrained to action_candidates.py's menu) -> assembled
into one structured result -> persisted via explanation_store.py.

Kept separate from api/main.py the same way service.py (the Copilot) is -
no FastAPI dependency, could be tested/reused standalone. Deliberately a
single non-conversational LLM call, not a chat - this report is generated
once, automatically, right after an investigation completes.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COPILOT_ROOT = Path(__file__).resolve().parent
PREW_ROOT = COPILOT_ROOT.parent
if str(PREW_ROOT) not in sys.path:
    sys.path.insert(0, str(PREW_ROOT))

from action_candidates import candidates_for  # noqa: E402
from explanation_builder import build_explanation_context  # noqa: E402
from explanation_prompts import NEXT_STEPS_SYSTEM_PROMPT  # noqa: E402
from llm_client import CopilotNotConfiguredError, ask  # noqa: E402

# Matches a leading list marker only ("1.", "1)", "-", "*"), never a
# period elsewhere in the line - a plain `split(". ", 1)` would also cut
# on any ". " inside a candidate's own text (e.g. "... (e.g. frequent
# fast-charging)"), corrupting it.
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]|[-*])\s*")


def _fallback_next_steps(candidates: tuple[str, ...]) -> list[str]:
    """Used when the LLM isn't configured or fails - returns the first
    few candidates as-is, unranked, rather than showing nothing."""
    return list(candidates[:4])


def _parse_steps(reply: str, candidates: tuple[str, ...]) -> list[str]:
    steps = []
    for line in reply.strip().splitlines():
        cleaned = _LIST_MARKER.sub("", line).strip()
        if cleaned:
            steps.append(cleaned)
    if steps:
        return steps
    return _fallback_next_steps(candidates)


def _generate_next_steps(warning: dict[str, Any], context: dict[str, Any]) -> tuple[list[str], str]:
    """Returns (steps, source) where source is "llm" or "fallback_menu" -
    the API/UI can show a subtle note when the fallback was used."""

    candidates = candidates_for(warning["warning_type"])
    if not candidates:
        return [], "fallback_menu"

    case_context = (
        f"WARNING TYPE: {warning['warning_type']}\n"
        f"TARGET METRIC: {warning['target_metric']}\n"
        f"ROOT CAUSE(S): {', '.join(context['root_cause_metrics']) or 'none found'}\n"
        f"DOWNSTREAM RISK: {', '.join(context['downstream_metrics']) or 'none found'}\n\n"
        "CANDIDATE ACTIONS (choose 3-5, ranked, phrased ONLY from this list):\n"
        + "\n".join(f"- {c}" for c in candidates)
    )

    # Same single-system-message constraint already confirmed against the
    # real LLM gateway in service.py.
    messages = [
        {"role": "system", "content": f"{NEXT_STEPS_SYSTEM_PROMPT}\n\nCASE CONTEXT:\n\n{case_context}"},
        {"role": "user", "content": "Generate the next-steps list now."},
    ]

    try:
        reply = ask(messages)
    except CopilotNotConfiguredError:
        return _fallback_next_steps(candidates), "fallback_menu"
    except Exception:  # noqa: BLE001 - a real LLM failure must not break report generation
        return _fallback_next_steps(candidates), "fallback_menu"

    return _parse_steps(reply, candidates), "llm"


def build_explanation(warning: dict[str, Any], investigation: dict[str, Any]) -> dict[str, Any]:
    """
    warning: a Warning record's __dict__.
    investigation: the persisted investigation result dict - callers
    should only call this once an investigation has actually completed.
    """

    context = build_explanation_context(warning, investigation)
    next_steps, next_steps_source = _generate_next_steps(warning, context)

    return {
        "warning_id": warning["warning_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "whats_happening": context["whats_happening"],
        "chain_narrative": context["chain_narrative"],
        "chain_nodes": context["chain_nodes"],
        "root_cause_summary": context["root_cause_summary"],
        "what_could_go_wrong": context["what_could_go_wrong"],
        "next_steps": next_steps,
        "next_steps_source": next_steps_source,
    }
