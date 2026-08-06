"""Shared FastAPI dependencies.

Endpoints import dependencies from this module only, so swapping
implementations (e.g. real authentication, read-replica sessions) never
touches endpoint signatures.
"""

from __future__ import annotations

from app.core.security import CurrentUser, get_current_user
from app.database.session import get_db

__all__ = ["CurrentUser", "get_current_user", "get_db"]
