"""Unit tests for the in-memory read cache."""

from __future__ import annotations

from app.core.cache import cached_read, clear_read_cache


async def test_cached_read_loads_once_per_key() -> None:
    """Repeated reads for the same key hit the loader a single time."""
    clear_read_cache()
    calls = {"count": 0}

    async def loader() -> list[str]:
        calls["count"] += 1
        return ["value"]

    first = await cached_read("unit:key", loader)
    second = await cached_read("unit:key", loader)

    assert first == second == ["value"]
    assert calls["count"] == 1


async def test_cached_read_distinguishes_keys() -> None:
    """Different keys load independently."""
    clear_read_cache()

    async def make_loader(value: str):
        async def loader() -> str:
            return value

        return loader

    assert await cached_read("unit:a", await make_loader("alpha")) == "alpha"
    assert await cached_read("unit:b", await make_loader("beta")) == "beta"


async def test_clear_read_cache_forces_reload() -> None:
    """Clearing the cache drops stored values so the next read reloads."""
    clear_read_cache()
    calls = {"count": 0}

    async def loader() -> int:
        calls["count"] += 1
        return calls["count"]

    assert await cached_read("unit:reload", loader) == 1
    clear_read_cache()
    assert await cached_read("unit:reload", loader) == 2
