"""Authentication seam.

The demo product runs without login, so every request resolves to an
anonymous demo user. This module is the single integration point for a
future JWT/OAuth implementation: routes depend on ``get_current_user``
only, so swapping in real authentication requires no endpoint changes.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class CurrentUser(BaseModel):
    """Authenticated (or anonymous demo) principal attached to each request."""

    id: UUID
    email: str
    full_name: str
    is_anonymous: bool = Field(default=True, description="True for the demo user; False once real auth is enabled.")


async def get_current_user() -> CurrentUser:
    """FastAPI dependency resolving the current principal.

    Returns the shared anonymous demo user until real authentication is
    wired in (JWT verification would live here).
    """
    return CurrentUser(
        id=DEMO_USER_ID,
        email="demo@mahindra.ai",
        full_name="Demo User",
        is_anonymous=True,
    )
