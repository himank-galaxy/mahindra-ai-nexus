"""Business validation over statistically significant PCMCI candidates."""

from __future__ import annotations

from app.ai.causal.pcmci_engine import PcmciEdge

# Statistical association alone is insufficient for a user-facing causal
# explanation. These direction pairs enforce the intended operational domain.
ALLOWED_RELATIONSHIPS = {
    ("lead_engagement_score", "dealer_followup_rate"),
    ("lead_volume", "dealer_followup_rate"),
    ("dealer_followup_rate", "test_drive_completion_rate"),
    ("test_drive_completion_rate", "booking_conversion_rate"),
    ("booking_conversion_rate", "finance_approval_rate"),
    ("vehicle_allocation_count", "allocation_delay_days"),
    ("allocation_delay_days", "delivery_delay_days"),
    ("delivery_delay_days", "cancellation_rate"),
    ("finance_approval_rate", "cancellation_rate"),
    ("booking_conversion_rate", "revenue"),
    ("cancellation_rate", "revenue"),
}


def business_validated(edges: list[PcmciEdge]) -> list[PcmciEdge]:
    """Keep only tested directions that make business-semantic sense."""
    return [edge for edge in edges if (edge.source, edge.target) in ALLOWED_RELATIONSHIPS]
