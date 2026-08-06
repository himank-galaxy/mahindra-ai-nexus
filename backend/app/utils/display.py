"""Enum → frontend display-label mappings.

The frozen Lovable UI renders statuses as human labels ("Human Review",
"OK", "Hot"). The database stores lowercase enum values; these maps are the
single source of truth for converting between the two so response JSON is
render-ready and write endpoints can parse the labels back.
"""

from __future__ import annotations

from app.models.enums import (
    AgentStatus,
    CollectionsCaseStatus,
    CollectionsComplianceFlag,
    DealerLeadStatus,
    RecommendationRisk,
    RecommendationStatus,
    TrustApproval,
    TrustAudit,
    TrustRisk,
    TwinApprovalStatus,
)

RECOMMENDATION_RISK_DISPLAY = {
    RecommendationRisk.LOW: "Low",
    RecommendationRisk.MEDIUM: "Medium",
    RecommendationRisk.HIGH: "High",
}

RECOMMENDATION_STATUS_DISPLAY = {
    RecommendationStatus.PENDING: "Pending",
    RecommendationStatus.APPROVED: "Approved",
    RecommendationStatus.UNDER_REVIEW: "Under Review",
}

DEALER_LEAD_STATUS_DISPLAY = {
    DealerLeadStatus.HOT: "Hot",
    DealerLeadStatus.WARM: "Warm",
    DealerLeadStatus.COOL: "Cool",
    DealerLeadStatus.MESSAGE_SENT: "Message Sent",
    DealerLeadStatus.CONVERTED: "Converted",
}

COLLECTIONS_FLAG_DISPLAY = {
    CollectionsComplianceFlag.OK: "OK",
    CollectionsComplianceFlag.REVIEW: "Review",
    CollectionsComplianceFlag.ESCALATE: "Escalate",
}

COLLECTIONS_CASE_STATUS_DISPLAY = {
    CollectionsCaseStatus.PENDING: "Pending",
    CollectionsCaseStatus.APPROVED: "Approved",
    CollectionsCaseStatus.HUMAN_REVIEW: "Human Review",
    CollectionsCaseStatus.MODIFIED: "Modified",
}

AGENT_STATUS_DISPLAY = {
    AgentStatus.ACTIVE: "Active",
    AgentStatus.REVIEWING: "Reviewing",
    AgentStatus.RECOMMENDED: "Recommended",
}

TRUST_APPROVAL_DISPLAY = {
    TrustApproval.APPROVED: "Approved",
    TrustApproval.HUMAN_REVIEW: "Human Review",
    TrustApproval.PENDING: "Pending",
    TrustApproval.REJECTED: "Rejected",
    TrustApproval.ESCALATED: "Escalated",
}

TRUST_RISK_DISPLAY = {
    TrustRisk.LOW: "Low",
    TrustRisk.MEDIUM: "Medium",
    TrustRisk.HIGH: "High",
}

TRUST_AUDIT_DISPLAY = {
    TrustAudit.COMPLETE: "Complete",
    TrustAudit.PENDING: "Pending",
}

TWIN_APPROVAL_DISPLAY = {
    TwinApprovalStatus.DRAFT: "Draft",
    TwinApprovalStatus.UNDER_REVIEW: "Under Review",
    TwinApprovalStatus.APPROVED: "Approved",
}
