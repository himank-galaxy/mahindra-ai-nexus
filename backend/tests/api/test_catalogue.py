"""Read API tests: AI Solution Catalogue."""

from __future__ import annotations

from app.database import seed_data
from httpx import AsyncClient


async def test_buckets_match_seed_with_nested_items(client: AsyncClient) -> None:
    response = await client.get("/api/v1/catalogue/buckets")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.SOLUTION_BUCKETS)

    first, expected = body[0], seed_data.SOLUTION_BUCKETS[0]
    assert first["name"] == expected["name"]
    assert first["tag"] == expected["tag"]
    assert len(first["items"]) == len(expected["items"])
    assert first["items"][0] == expected["items"][0]


async def test_buckets_can_be_filtered_by_tag(client: AsyncClient) -> None:
    tag = seed_data.SOLUTION_BUCKETS[0]["tag"]
    body = (await client.get(f"/api/v1/catalogue/buckets?tag={tag}")).json()
    assert body
    assert all(bucket["tag"] == tag for bucket in body)


async def test_unknown_tag_returns_empty_list(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/catalogue/buckets?tag=NoSuchTag")).json()
    assert body == []


async def test_tags_return_frontend_chip_list(client: AsyncClient) -> None:
    response = await client.get("/api/v1/catalogue/tags")
    assert response.status_code == 200
    assert response.json() == seed_data.SOLUTION_TAGS
