"""Copilot fallback response when no intent matches the prompt.

Exact port of the default return in ``frontend/src/lib/copilot.ts``.
"""

from __future__ import annotations

COPILOT_FALLBACK: dict[str, object] = {
    "answer": (
        "I can analyze Auto, Finance, Logistics, Circularity, Compliance and Simulation data. "
        "Try a suggested question or ask about bookings, leakage, collections, SLA, credits or warranty."
    ),
    "explanation": (
        "The copilot combines predictive, causal and agentic reasoning across Mahindra businesses. "
        "Ask a specific question to get analysis + recommended action."
    ),
    "sql": "-- Ask a specific question to generate a query",
    "python": "# Ask a specific question to generate analysis",
    "action": "Try one of the suggested prompts to see a full analysis.",
    "confidence": 70,
}
