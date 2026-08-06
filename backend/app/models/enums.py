"""PostgreSQL ENUM types shared across domain models.

Values are stored lowercase in the database; API schemas map them back to
the display casing the frontend expects. ``values_callable`` ensures
Alembic persists the raw values (not uppercased symbol names).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum


class RecommendationRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    UNDER_REVIEW = "under_review"


class DealerLeadStatus(StrEnum):
    HOT = "hot"
    WARM = "warm"
    COOL = "cool"
    MESSAGE_SENT = "message_sent"
    CONVERTED = "converted"


class TwinApprovalStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"


class CollectionsComplianceFlag(StrEnum):
    OK = "ok"
    REVIEW = "review"
    ESCALATE = "escalate"


class CollectionsCaseStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    HUMAN_REVIEW = "human_review"
    MODIFIED = "modified"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    REVIEWING = "reviewing"
    RECOMMENDED = "recommended"


class TrustApproval(StrEnum):
    APPROVED = "approved"
    HUMAN_REVIEW = "human_review"
    PENDING = "pending"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class TrustRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TrustAudit(StrEnum):
    COMPLETE = "complete"
    PENDING = "pending"


class CopilotRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class SimulationDomain(StrEnum):
    AUTO_SALES = "auto_sales"
    DEALER_ALLOCATION = "dealer_allocation"
    COLLECTIONS = "collections"
    LOGISTICS_DELAY = "logistics_delay"
    CREDIT_PRICING = "credit_pricing"


class SignalPanel(StrEnum):
    """Which UI panel a warehouse-style signal tile belongs to."""

    WAREHOUSE = "warehouse"
    COLLECTIONS_METRICS = "collections_metrics"
    RVSF = "rvsf"


class QaCategory(StrEnum):
    MOBILITY = "mobility"
    DMRV = "dmrv"


def enum_column(enum_cls: type[StrEnum], name: str, **kwargs):
    """Build a named PostgreSQL ENUM column bound to a StrEnum class."""
    return Enum(enum_cls, name=name, values_callable=lambda cls: [member.value for member in cls], **kwargs)
