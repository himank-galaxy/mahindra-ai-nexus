"""Executive summary LLM polish: grounded replies are used, ungrounded ones fall back.

``conftest.py`` forces ``AI_PROVIDER=rule`` globally so no test ever makes a
live network call even though ``backend/.env`` carries real credentials for
local dev; this file injects a fake provider via monkeypatch to exercise
the polish path itself (app/services/simulation.py::_polish_summary).
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

import app.services.simulation as simulation_service

BASE = "/api/v1/simulations"


def _install_fake_provider(monkeypatch: pytest.MonkeyPatch, complete) -> None:
    fake = type("FakeProvider", (), {"complete": complete})()
    monkeypatch.setattr(simulation_service, "get_llm_provider", lambda settings: fake)  # noqa: ARG005


async def test_summary_uses_llm_reply_when_grounded(
    client: AsyncClient, auto_sales_funnel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (await client.post(f"{BASE}/auto-sales/run", json={})).json()

    async def fake_complete(self, prompt: str) -> str:  # noqa: ARG001
        json_start = prompt.index("INPUT:\n") + len("INPUT:\n")
        original = json.loads(prompt[json_start:])
        polished = dict(original)
        polished["trade_off"] = "Rewritten but faithful: " + original["trade_off"]
        return json.dumps(polished)

    _install_fake_provider(monkeypatch, fake_complete)

    response = await client.post(f"{BASE}/{body['run_id']}/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["recommendation"] == body["recommendedAction"]  # facts/numbers preserved verbatim
    assert summary["trade_off"].startswith("Rewritten but faithful:")  # proves the polish path ran


async def test_summary_falls_back_when_llm_reply_drops_a_number(
    client: AsyncClient, auto_sales_funnel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (await client.post(f"{BASE}/auto-sales/run", json={})).json()

    async def fake_complete(self, prompt: str) -> str:  # noqa: ARG001
        return json.dumps(
            {
                "scenario": "x",
                "inputs_summary": "x",
                "baseline": "x",
                "predicted_outcome": "Bookings improved.",  # every number dropped
                "major_drivers": [],
                "trade_off": "x",
                "recommendation": "x",
                "confidence": "x",
                "risk": "x",
            }
        )

    _install_fake_provider(monkeypatch, fake_complete)

    response = await client.post(f"{BASE}/{body['run_id']}/summary")

    assert response.status_code == 200
    summary = response.json()
    assert str(body["uplift"]) in summary["predicted_outcome"]  # deterministic text, untouched


async def test_summary_falls_back_when_llm_reply_is_not_json(
    client: AsyncClient, auto_sales_funnel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (await client.post(f"{BASE}/auto-sales/run", json={})).json()

    async def fake_complete(self, prompt: str) -> str:  # noqa: ARG001
        return "Sure, here is a nice summary of your simulation!"

    _install_fake_provider(monkeypatch, fake_complete)

    response = await client.post(f"{BASE}/{body['run_id']}/summary")

    assert response.status_code == 200
    assert str(body["uplift"]) in response.json()["predicted_outcome"]


async def test_summary_falls_back_when_llm_raises(
    client: AsyncClient, auto_sales_funnel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = (await client.post(f"{BASE}/auto-sales/run", json={})).json()

    async def fake_complete(self, prompt: str) -> str:  # noqa: ARG001
        raise RuntimeError("provider unavailable")

    _install_fake_provider(monkeypatch, fake_complete)

    response = await client.post(f"{BASE}/{body['run_id']}/summary")

    assert response.status_code == 200
    assert str(body["uplift"]) in response.json()["predicted_outcome"]


async def test_summary_is_deterministic_without_llm_configured(
    client: AsyncClient, auto_sales_funnel: None
) -> None:
    """No monkeypatch here: AI_PROVIDER=rule (conftest.py) — confirms the
    button works with no LLM configured at all, the common case today."""
    body = (await client.post(f"{BASE}/auto-sales/run", json={})).json()

    response = await client.post(f"{BASE}/{body['run_id']}/summary")

    assert response.status_code == 200
    assert str(body["uplift"]) in response.json()["predicted_outcome"]
