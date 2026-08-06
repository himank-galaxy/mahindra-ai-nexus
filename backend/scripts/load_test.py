"""Basic load test: concurrent burst against key endpoints.

Fires a configurable number of requests with bounded concurrency against a
representative mix of read and AI endpoints, then reports latency
percentiles, throughput and any non-200 responses.

Usage (from ``backend/`` with the API running):
    python scripts/load_test.py                     # 500 requests, 20 workers
    python scripts/load_test.py --requests 2000 --concurrency 50
    python scripts/load_test.py --base-url http://localhost:8000

Disable rate limiting while load testing (or requests will 429):
    set RATE_LIMIT_ENABLED=false before starting uvicorn.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

# (method, path, optional body) — mirrors real frontend traffic.
ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/overview/kpis", None),
    ("GET", "/api/v1/overview/recommendations", None),
    ("GET", "/api/v1/catalogue/buckets", None),
    ("GET", "/api/v1/dealers", None),
    ("GET", "/api/v1/dealers/d1/leads", None),
    ("GET", "/api/v1/finance/products", None),
    ("GET", "/api/v1/collections/cases", None),
    ("GET", "/api/v1/logistics/routes", None),
    ("GET", "/api/v1/circularity/credits", None),
    ("GET", "/api/v1/trust/decisions", None),
    ("GET", "/api/v1/agents", None),
    ("GET", "/api/v1/mobility-twin/graph", None),
    ("GET", "/api/v1/simulations/meta", None),
    ("GET", "/api/v1/copilot/suggested-prompts", None),
    ("POST", "/api/v1/copilot/chat", {"message": "Why did bookings drop in Pune last week?"}),
    ("POST", "/api/v1/simulations/auto-sales/run", {"discount": 3, "bonus": 25000, "campaign": 1.5}),
]


async def worker(
    client: httpx.AsyncClient,
    queue: asyncio.Queue[tuple[str, str, dict | None]],
    latencies: list[float],
    failures: list[str],
) -> None:
    """Drain the queue, recording latency per request and any failures."""
    while True:
        try:
            method, path, body = queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        started = time.perf_counter()
        try:
            response = await client.request(method, path, json=body)
            if response.status_code >= 400:
                failures.append(f"{method} {path} -> {response.status_code}")
        except httpx.HTTPError as exc:
            failures.append(f"{method} {path} -> {exc.__class__.__name__}")
        latencies.append((time.perf_counter() - started) * 1000)
        queue.task_done()


async def run(base_url: str, total: int, concurrency: int) -> None:
    queue: asyncio.Queue[tuple[str, str, dict | None]] = asyncio.Queue()
    for index in range(total):
        queue.put_nowait(ENDPOINTS[index % len(ENDPOINTS)])

    latencies: list[float] = []
    failures: list[str] = []

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(base_url=base_url, limits=limits, timeout=30) as client:
        started = time.perf_counter()
        async with asyncio.TaskGroup() as group:
            for _ in range(concurrency):
                group.create_task(worker(client, queue, latencies, failures))
        elapsed = time.perf_counter() - started

    latencies.sort()
    percentile = lambda p: latencies[min(int(len(latencies) * p), len(latencies) - 1)]  # noqa: E731
    print(f"Load test against {base_url}")
    print(f"  requests      : {total} ({len(failures)} failed)")
    print(f"  concurrency   : {concurrency}")
    print(f"  wall time     : {elapsed:.2f}s ({total / elapsed:.1f} req/s)")
    print(f"  latency p50   : {percentile(0.50):.1f} ms")
    print(f"  latency p95   : {percentile(0.95):.1f} ms")
    print(f"  latency p99   : {percentile(0.99):.1f} ms")
    print(f"  latency mean  : {statistics.mean(latencies):.1f} ms")
    if failures:
        unique = sorted(set(failures))
        print("  failures      :")
        for failure in unique[:10]:
            print(f"    - {failure}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic HTTP load test for the API.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL.")
    parser.add_argument("--requests", type=int, default=500, help="Total requests to fire.")
    parser.add_argument("--concurrency", type=int, default=20, help="Parallel workers.")
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
