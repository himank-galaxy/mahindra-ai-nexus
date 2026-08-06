"""PoC roadmap items (server-side replacement for localStorage)."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PocItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Solution shortlisted for the PoC roadmap."""

    __tablename__ = "poc_items"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    bucket: Mapped[str] = mapped_column(String(128))
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
