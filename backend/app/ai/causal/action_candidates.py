"""Domain-knowledge menu of candidate actions per Auto Mobility metric.

This is the "menu" layer of recommended actions
(docs/Implementation_plan_mobility_causal.md §6): a small, explicit,
human-editable table — never LLM-generated — so a recommendation always
has a grounded set of real options to choose from. The LLM (see
app/services/mobility_recommendations.py) only ranks and phrases within
this menu; it never invents an action outside it.
"""

from __future__ import annotations

ACTION_CANDIDATES: dict[str, tuple[str, ...]] = {
    "lead_volume": (
        "Increase digital campaign spend in the regions generating the fewest leads",
        "Expand outreach to previously unengaged customer segments",
        "Run a targeted referral incentive campaign",
    ),
    "lead_engagement_score": (
        "Prioritize follow-up on the most engaged leads first",
        "A/B test lead-nurturing content for lower-scoring segments",
        "Route highly engaged leads to senior sales staff",
    ),
    "dealer_followup_rate": (
        "Escalate leads with no dealer follow-up after 2 hours",
        "Add WhatsApp/SMS reminder templates for dealer staff",
        "Reassign stale leads to dealers with a higher follow-up SLA",
    ),
    "test_drive_completion_rate": (
        "Send automated reminders ahead of scheduled test drives",
        "Offer flexible weekend/evening test-drive slots",
        "Follow up immediately with no-shows to reschedule",
    ),
    "booking_conversion_rate": (
        "Target the dealers/regions with the highest historical conversion",
        "Offer a limited-time bundle to customers who completed a test drive but haven't booked",
        "Introduce a fast-track booking desk for high-intent leads",
    ),
    "finance_approval_rate": (
        "Pre-screen applications for the most common rejection reasons",
        "Offer alternate-data underwriting for thin-file applicants",
        "Provide a finance concierge for borderline applications",
    ),
    "vehicle_allocation_count": (
        "Rebalance inventory from low-demand to high-demand regions",
        "Prioritize allocation for the oldest pending bookings",
        "Flag persistent regional shortages to production planning",
    ),
    "allocation_delay_days": (
        "Clear the oldest pending allocations first",
        "Increase allocation batch frequency in the most delayed regions",
        "Escalate allocations blocked on financing or documentation",
    ),
    "delivery_delay_days": (
        "Prioritize logistics capacity for at-risk delivery commitments",
        "Add buffer capacity on the most frequently delayed routes",
        "Proactively notify affected customers of expected delays",
    ),
    "cancellation_rate": (
        "Reach out proactively to customers showing cancellation-risk signals",
        "Offer a retention incentive before the cancellation window closes",
        "Shorten the slowest step in the booking-to-delivery pipeline",
    ),
    "revenue": (
        "Focus conversion effort on the highest-margin models",
        "Reduce leakage at the funnel stage with the largest drop-off",
        "Expand cross-sell/upsell at the booking stage",
    ),
}
