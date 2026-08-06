"""CLI: provision a local SQLite database with schema + seed data.

Development fallback while PostgreSQL (Docker) is unavailable:

Usage (from ``backend/``):
    python scripts/dev_sqlite_seed.py                 # creates dev.db
    python scripts/dev_sqlite_seed.py --path smoke.db

Serve against it with:
    $env:DATABASE_URL="sqlite+aiosqlite:///dev.db"
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as a plain script without packaging/install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401 — register every model on Base.metadata
from app.database.base import Base  # noqa: E402
from app.database.seed import seed_database  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402


async def run(path: str) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        report = await seed_database(session)
    await engine.dispose()
    print(f"Seeded {report.total} rows across {len(report.counts)} tables into {path}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a seeded SQLite dev database.")
    parser.add_argument("--path", default="dev.db", help="SQLite file path (default: dev.db)")
    args = parser.parse_args()
    asyncio.run(run(args.path))


if __name__ == "__main__":
    main()
