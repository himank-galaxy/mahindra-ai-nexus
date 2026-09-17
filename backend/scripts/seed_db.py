"""CLI: apply the deterministic seed dataset to the configured database.

Usage (from ``backend/``):
    python scripts/seed_db.py            # idempotent upsert
    python scripts/seed_db.py --reset    # TRUNCATE first, then seed

Assumes migrations are already applied (``alembic upgrade head``).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as a plain script without packaging/install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.seed import seed_database  # noqa: E402
from app.database.session import dispose_engine, get_session_factory  # noqa: E402


async def run(reset: bool) -> None:
    factory = get_session_factory()
    try:
        async with factory() as session:
            report = await seed_database(session, reset=reset)
    finally:
        await dispose_engine()

    for table, count in sorted(report.counts.items()):
        print(f"  {table:<22} {count:>4}")
    print(f"Seeded {report.total} rows across {len(report.counts)} tables.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Mahindra AI Nexus database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="TRUNCATE all seeded tables before inserting (destructive).",
    )
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))


if __name__ == "__main__":
    main()
