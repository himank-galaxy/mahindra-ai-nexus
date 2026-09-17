"""Minute-level persisted early-warning evaluator entrypoint."""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import get_session_factory
from app.services.causal_runtime import utc_now
from app.services.warranty_quality_evaluation import evaluate_and_persist

logger = get_logger(__name__)


async def run_once() -> None:
    async with get_session_factory()() as session:
        await evaluate_and_persist(session, now=utc_now())


async def loop() -> None:
    settings = get_settings()
    if not settings.causal_warning_evaluator_enabled:
        logger.info("warning_evaluator_disabled")
        return
    logger.info("warning_evaluator_started", poll_seconds=settings.causal_warning_evaluator_poll_seconds)
    while True:
        try:
            await run_once()
        except Exception as exc:  # noqa: BLE001 - survive transient DB/model failures
            logger.exception("warning_evaluator_iteration_failed", error=str(exc))
        await asyncio.sleep(settings.causal_warning_evaluator_poll_seconds)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(run_once() if args.once else loop())


if __name__ == "__main__":
    main()
