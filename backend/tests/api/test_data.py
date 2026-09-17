"""Read API tests for the module-first Data explorer."""

from __future__ import annotations

from app.services.data_catalog import DATASET_SPECS, MODULES, datasets_for_module
from httpx import AsyncClient


async def test_data_catalog_contains_every_runtime_dataset(client: AsyncClient) -> None:
    response = await client.get("/api/v1/data/catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["generated_from"] == "docs/Data_Dictionary.docx"
    assert len(body["modules"]) == len(MODULES)

    catalog_dataset_ids = {dataset["id"] for module in body["modules"] for dataset in module["datasets"]}
    assert catalog_dataset_ids == {dataset.id for dataset in DATASET_SPECS}


async def test_data_catalog_preserves_screen_links_and_supporting_group(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/data/catalog")).json()
    modules = {module["id"]: module for module in body["modules"]}

    overview_ids = {dataset["id"] for dataset in modules["overview"]["datasets"]}
    dealer_ids = {dataset["id"] for dataset in modules["dealer"]["datasets"]}
    supporting_ids = {dataset["id"] for dataset in modules["other-supporting"]["datasets"]}

    assert {"bookings", "cancellations", "finance_applications"} <= overview_ids
    assert {"bookings", "leads", "test_drives"} <= dealer_ids
    assert {"agent_workflow_runs", "copilot_eval_questions", "production_batches"} <= supporting_ids

    for module in MODULES:
        response_ids = {dataset["id"] for dataset in modules[module.id]["datasets"]}
        assert response_ids == {dataset.id for dataset in datasets_for_module(module.id)}
