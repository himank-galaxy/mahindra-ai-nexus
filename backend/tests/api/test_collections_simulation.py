"""Finance Collections Simulation Phase 4: real trained recovery model.

Recovery probability, channel response, and offer response come from one
logistic regression trained on the real ``payment_after_contact`` outcome
(never a formula) — see app/ai/simulation/collections_sim.py. Channel and
offer are the exact real recorded categories (no UI-to-real translation,
unlike the retired "Digital" grouping and "Waiver" option), so every
combination is genuinely trained — confidence_basis is always
"trained_model" for this domain. Assertions check shape/ranges/consistency
rather than brittle exact values, matching the testing philosophy already
used for Auto Sales/Dealer Allocation.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/simulations"
CHANNELS = ("SMS", "WHATSAPP", "EMAIL", "CALL", "FIELD_VISIT")
OFFERS = ("NONE", "PAYMENT_REMINDER", "PARTIAL_PAYMENT_PLAN", "REPAYMENT_PLAN_DISCUSSION")


async def _run(client: AsyncClient, **overrides: object) -> dict:
    payload = {"risk": "Medium", "channel": "WHATSAPP", "offer": "REPAYMENT_PLAN_DISCUSSION", "field": 40, **overrides}
    response = await client.post(f"{BASE}/collections/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_collections_run_uses_real_trained_model(client: AsyncClient, collections_seed: None) -> None:
    body = await _run(client)

    assert uuid.UUID(body["run_id"]).version == 4
    assert body["status"] == "PROPOSED"
    assert body["confidence_basis"] == "trained_model"
    assert 0 <= body["prob"] <= 100
    assert body["cost"] == 60  # WhatsApp calibrated cost, unaffected by the model
    assert isinstance(body["net"], int)


async def test_collections_every_real_channel_and_offer_is_trained(
    client: AsyncClient, collections_seed: None
) -> None:
    """Regression: since channel/offer now use the exact real recorded
    categories (no UI grouping or invented option like the retired
    "Waiver"), every combination in the actual action space must be a
    trained prediction — there is no calibrated-heuristic path left in
    this domain at all."""
    for channel in CHANNELS:
        for offer in OFFERS:
            body = await _run(client, channel=channel, offer=offer)
            assert body["confidence_basis"] == "trained_model", f"{channel}/{offer} was not trained"


async def test_collections_field_visit_costs_more_than_whatsapp(client: AsyncClient, collections_seed: None) -> None:
    whatsapp = await _run(client, channel="WHATSAPP")
    field_visit = await _run(client, channel="FIELD_VISIT", field=80)

    assert field_visit["cost"] > whatsapp["cost"]
    assert field_visit["friction"] > whatsapp["friction"]


async def test_collections_drivers_show_channel_and_offer_for_this_run(
    client: AsyncClient, collections_seed: None
) -> None:
    body = await _run(client, channel="CALL", offer="PARTIAL_PAYMENT_PLAN")

    drivers = (await client.get(f"{BASE}/{body['run_id']}/drivers")).json()

    names = [item["name"] for item in drivers["predictive_drivers"]]
    assert any("Call" in name for name in names)
    assert any("Partial Payment Plan" in name for name in names)
    assert drivers["causal_evidence"] == []
    assert {item["source"] for item in drivers["predictive_drivers"]} == {"trained_model"}


async def test_collections_summary_reflects_the_actual_run(client: AsyncClient, collections_seed: None) -> None:
    body = await _run(client)

    summary = (await client.post(f"{BASE}/{body['run_id']}/summary")).json()

    assert str(body["prob"]) in summary["predicted_outcome"]
    assert summary["recommendation"] == body["recommendedAction"]
    assert summary["major_drivers"]


async def test_collections_insufficient_data_returns_clear_error(client: AsyncClient) -> None:
    """No seed fixture applied — the collection_interactions table is empty."""
    response = await client.post(f"{BASE}/collections/run", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_training_data"
