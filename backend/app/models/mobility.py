"""Auto Mobility Causal Twin: graph, business KPIs and Q&A."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk
from app.models.enums import QaCategory, enum_column


class CausalNode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Node in the mobility causal decision graph (SVG coordinates included)."""

    __tablename__ = "causal_nodes"

    label: Mapped[str] = mapped_column(String(128), unique=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    metric: Mapped[str] = mapped_column(String(128))
    trend: Mapped[str] = mapped_column(String(32))
    drivers: Mapped[list[str]] = mapped_column(JSONType, default=list)
    action: Mapped[str] = mapped_column(String(256))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CausalEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Directed edge between two causal nodes."""

    __tablename__ = "causal_edges"

    source_node_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("causal_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("causal_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (UniqueConstraint("source_node_id", "target_node_id", name="uq_causal_edges_pair"),)


class MobilityKpi(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Business health KPI shown beside the causal graph."""

    __tablename__ = "mobility_kpis"

    label: Mapped[str] = mapped_column(String(128), unique=True)
    value: Mapped[str] = mapped_column(String(64))
    trend: Mapped[str] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CausalQa(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Pre-authored Q&A for 'Ask Causal Twin' and dMRV copilot lookups."""

    __tablename__ = "causal_qa"

    category: Mapped[QaCategory] = mapped_column(
        enum_column(QaCategory, "qa_category"),
        default=QaCategory.MOBILITY,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_causal_qa_category_question", "category", "question"),)
