"""AI Solution Catalogue: buckets and their solutions."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, uuid_pk


class SolutionBucket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalogue bucket grouping solutions under a business theme + tag."""

    __tablename__ = "solution_buckets"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    tag: Mapped[str] = mapped_column(String(64), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    solutions: Mapped[list[Solution]] = relationship(
        back_populates="bucket",
        cascade="all, delete-orphan",
        order_by="Solution.sort_order",
    )


class Solution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One AI solution card inside a catalogue bucket."""

    __tablename__ = "solutions"

    bucket_id: Mapped[uuid.UUID] = mapped_column(
        uuid_pk(),
        ForeignKey("solution_buckets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), unique=True)
    problem: Mapped[str] = mapped_column(Text)
    solution: Mapped[str] = mapped_column(Text)
    differentiator: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    bucket: Mapped[SolutionBucket] = relationship(back_populates="solutions")
