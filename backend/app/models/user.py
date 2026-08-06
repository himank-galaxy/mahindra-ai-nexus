"""Users: auth seam table seeded with the demo principal."""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Application principal (anonymous demo user until real auth lands)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(256), unique=True)
    full_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
