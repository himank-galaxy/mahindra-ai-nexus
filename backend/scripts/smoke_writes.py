"""Phase 3 live smoke probes (throwaway; run against uvicorn on port 8010)."""

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
    if len(payload) > 220:
        payload = payload[:220] + "…"
    print(f"[{resp.status_code}] {label}: {payload}")


def main() -> int:
    with httpx.Client(timeout=10) as c:
        # 1. Approve recommendation, then verify persistence.
        show("PATCH /recommendations/r1", c.patch(f"{BASE}/recommendations/r1", json={"status": "Approved"}))
        recs = c.get(f"{BASE}/overview/recommendations").json()
        r1 = next(row for row in recs if row["id"] == "r1")
        print(f"     persisted status of r1: {r1['status']}")

        # 2. PoC add / duplicate / roadmap-plan / delete.
        payload = {"name": "AI Simulation Center", "bucket": "Intelligence Platforms"}
        show("POST /poc", c.post(f"{BASE}/poc", json=payload))
        show("POST /poc duplicate", c.post(f"{BASE}/poc", json=payload))
        show("GET /poc/roadmap-plan", c.get(f"{BASE}/poc/roadmap-plan"))
        show("DELETE /poc", c.delete(f"{BASE}/poc", params={"name": payload["name"]}))

        # 3. Dealer lead convert.
        leads = c.get(f"{BASE}/dealers/d1/leads").json()
        lead = leads[0]
        show(f"POST /dealer-leads/{lead['name']}/convert", c.post(f"{BASE}/dealer-leads/{lead['id']}/convert"))

        # 4. Trust approve + reject.
        show("POST /trust AUTO-1042 approve", c.post(f"{BASE}/trust/decisions/AUTO-1042/approve"))
        show("POST /trust FIN-8821 reject", c.post(f"{BASE}/trust/decisions/FIN-8821/reject", json={"reason": "smoke"}))

        # 5. Logistics reroute + auto-heal.
        routes = c.get(f"{BASE}/logistics/routes").json()
        route = routes[0]
        show(f"POST reroute {route['name']}", c.post(f"{BASE}/logistics/routes/{route['id']}/reroute"))
        show(f"POST auto-heal {route['name']}", c.post(f"{BASE}/logistics/routes/{route['id']}/auto-heal"))

        # 6. Finance submit-approval twice (second must 409).
        twins = c.get(f"{BASE}/finance/twins").json()
        twin = twins[0]
        show("POST submit-approval", c.post(f"{BASE}/finance/twins/{twin['id']}/submit-approval"))
        show("POST submit-approval again", c.post(f"{BASE}/finance/twins/{twin['id']}/submit-approval"))

        # 7. Circularity match-buyer.
        show("POST match-buyer CR-2214", c.post(f"{BASE}/circularity/credits/CR-2214/match-buyer"))

        # 8. Error envelope on missing entity.
        show("PATCH /recommendations/r99", c.patch(f"{BASE}/recommendations/r99", json={"status": "Approved"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
