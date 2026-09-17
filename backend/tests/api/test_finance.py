"""Read API tests: Financial Services."""

from __future__ import annotations

import uuid

from app.database import seed_data
from httpx import AsyncClient


async def test_products_match_seed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/finance/products")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.FINANCE_PRODUCTS)

    first, expected = body[0], seed_data.FINANCE_PRODUCTS[0]
    assert first["name"] == expected["name"]
    assert first["customers"] == expected["customers"]
    assert first["risk"] == expected["risk"]
    assert first["cross"] == expected["cross_sell"]
    assert first["opp"] == expected["opportunity"]


async def test_twin_index_lists_ids_and_names(client: AsyncClient) -> None:
    response = await client.get("/api/v1/finance/twins")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(seed_data.CUSTOMER_TWINS)
    assert body[0]["name"] == seed_data.CUSTOMER_TWINS[0]["name"]
    uuid.UUID(body[0]["id"])  # parseable UUID for lookup


async def test_twin_detail_matches_seed(client: AsyncClient) -> None:
    index = (await client.get("/api/v1/finance/twins")).json()
    twin_id = index[0]["id"]

    response = await client.get(f"/api/v1/finance/customers/{twin_id}/twin")

    assert response.status_code == 200
    body = response.json()
    expected = seed_data.CUSTOMER_TWINS[0]
    assert body["name"] == expected["name"]
    assert body["location"] == expected["location"]
    assert body["income_stability"] == expected["income_stability"]
    assert body["repayment"] == expected["repayment"]
    assert body["products"] == expected["products"]
    assert body["nba"] == expected["nba"]
    assert body["risk_decomposition"] == expected["risk_decomposition"]
    assert body["cross_sell"] == expected["cross_sell"]
    assert body["approval_status"] == "Draft"


async def test_unknown_twin_returns_structured_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    response = await client.get(f"/api/v1/finance/customers/{missing}/twin")

    assert response.status_code == 404
    assert response.json()["code"] == "twin_not_found"
