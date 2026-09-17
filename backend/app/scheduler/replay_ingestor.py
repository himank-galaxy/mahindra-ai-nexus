"""Process entrypoint for the transactional replay ingestor."""

from __future__ import annotations

import argparse
import asyncio

from app.database.session import get_session_factory
from app.services.live_ingestion import ensure_ingestion_states, ingest_tick, ingestion_loop


async def run_once() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await ensure_ingestion_states(session)
    await ingest_tick(factory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_once() if args.once else ingestion_loop())


if __name__ == "__main__":
    main()
