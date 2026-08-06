"""Financial Services: product portfolio and customer financial twins."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TwinApprovalStatus, enum_column


class FinanceProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Financial product card with portfolio stats."""

    __tablename__ = "finance_products"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    customers: Mapped[str] = mapped_column(String(32))
    risk: Mapped[str] = mapped_column(String(32))
    cross_sell: Mapped[str] = mapped_column(String(32))
    opportunity: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CustomerTwin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Unified customer financial twin: profile, NBA, risk, cross-sell."""

    __tablename__ = "customer_twins"

    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(128))
    income_stability: Mapped[str] = mapped_column(String(32))
    repayment: Mapped[str] = mapped_column(String(32))
    products: Mapped[list[str]] = mapped_column(JSONType, default=list)
    nba: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    risk_decomposition: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict)
    cross_sell: Mapped[dict[str, str]] = mapped_column(JSONType, default=dict)
    approval_status: Mapped[TwinApprovalStatus] = mapped_column(
        enum_column(TwinApprovalStatus, "twin_approval_status"),
        default=TwinApprovalStatus.DRAFT,
    )
