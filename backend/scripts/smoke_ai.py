"""Phase 4 live smoke probes for the AI layer (run against a local uvicorn)."""

from __future__ import annotations

import json
import sys

import httpx

PORT = sys.argv[1] if len(sys.argv) > 1 else "8011"
BASE = f"http://127.0.0.1:{PORT}/api/v1"


def show(label: str, resp: httpx.Response) -> None:
    try:
        payload = json.dumps(resp.json(), ensure_ascii=False)
    except ValueError:
        payload = repr(resp.text)
    if len(payload) > 240:
        payload = payload[:240] + "…"
    print(f"[{resp.status_code}] {label}: {payload}")


def main() -> int:
    with httpx.Client(timeout=10) as c:
        # 1. Simulation engines.
        show("POST /simulations/auto-sales/run", c.post(f"{BASE}/simulations/auto-sales/run", json={}))
        show(
            "POST /simulations/auto-sales/run (High/North)",
            c.post(
                f"{BASE}/simulations/auto-sales/run",
                json={"region": "North", "discount": 3.5, "bonus": 50000, "campaign": 2.0, "intensity": "High"},
            ),
        )
        show("POST /simulations/dealer-allocation/run", c.post(f"{BASE}/simulations/dealer-allocation/run", json={}))
        show("POST /simulations/collections/run", c.post(f"{BASE}/simulations/collections/run", json={}))
        show("POST /simulations/logistics-delay/run", c.post(f"{BASE}/simulations/logistics-delay/run", json={}))
        show("POST /simulations/credit-pricing/run", c.post(f"{BASE}/simulations/credit-pricing/run", json={}))
        show(
            "GET /simulations/causal-drivers",
            c.get(f"{BASE}/simulations/causal-drivers", params={"domain": "collections"}),
        )
        show(
            "GET /simulations/causal-drivers (unknown)",
            c.get(f"{BASE}/simulations/causal-drivers", params={"domain": "warp"}),
        )

        # 2. Executive summary.
        show(
            "POST /executive-summary",
            c.post(f"{BASE}/executive-summary", json={"useCase": "Logistics Delay Simulation"}),
        )

        # 3. Copilot chat.
        show(
            "POST /copilot/chat (Pune)",
            c.post(f"{BASE}/copilot/chat", json={"message": "Why did bookings drop in Pune?"}),
        )
        show("POST /copilot/chat (fallback)", c.post(f"{BASE}/copilot/chat", json={"message": "hello"}))

        # 4. Mobility twin + dMRV.
        show(
            "POST /mobility-twin/ask",
            c.post(f"{BASE}/mobility-twin/ask", json={"question": "Why did bookings drop in Pune?"}),
        )
        show("GET /circularity/dmrv/prompts", c.get(f"{BASE}/circularity/dmrv/prompts"))
        show(
            "POST /circularity/dmrv/ask",
            c.post(f"{BASE}/circularity/dmrv/ask", json={"question": "Estimate carbon credits for this batch."}),
        )

        # 5. ELV + finance AI + workflow.
        show("POST /circularity/elv/estimate", c.post(f"{BASE}/circularity/elv/estimate", json={}))
        twins = c.get(f"{BASE}/finance/twins").json()
        twin_id = twins[0]["id"]
        show("POST /finance/twins/{id}/explain", c.post(f"{BASE}/finance/twins/{twin_id}/explain"))
        show("POST /finance/twins/{id}/rm-script", c.post(f"{BASE}/finance/twins/{twin_id}/rm-script"))
        show(
            "POST /finance/twins/{id}/simulate-offer",
            c.post(f"{BASE}/finance/twins/{twin_id}/simulate-offer", json={"amount": 450000}),
        )
        show("POST /agents/workflow/run", c.post(f"{BASE}/agents/workflow/run"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
