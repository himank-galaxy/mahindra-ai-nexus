"""In-memory TTL cache for static read endpoints.

Read-heavy data that never mutates through the API (catalogue buckets,
agents, mobility graph, simulation metadata, XR cards, prompt libraries)
is cached process-wide to cut database load. TTL expiry keeps values
fresh after reseeds; ``clear_read_cache`` is exposed for tests and
admin seeding flows.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from cachetools import TTLCache

from app.core.config import get_settings

_cache: TTLCache[str, Any] | None = None


def _get_cache() -> TTLCache[str, Any]:
    """Lazily build the process-wide cache with the configured TTL."""
    global _cache
    if _cache is None:
        ttl = get_settings().read_cache_ttl_seconds
        _cache = TTLCache(maxsize=512, ttl=ttl if ttl > 0 else 1)
    return _cache


async def cached_read[T](key: str, loader: Callable[[], Awaitable[T]]) -> T:
    """Return the cached value for ``key`` or load (and store) it."""
    cache = _get_cache()
    if key in cache:
        return cache[key]  # type: ignore[no-any-return]
    value = await loader()
    cache[key] = value
    return value


def clear_read_cache() -> None:
    """Drop every cached read entry (used after reseeds and in tests)."""
    _get_cache().clear()
