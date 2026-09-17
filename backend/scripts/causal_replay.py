"""Inspect and control the persistent synthetic causal replay clock.

Examples inside the backend/scheduler container:
    python scripts/causal_replay.py status
    python scripts/causal_replay.py pause
    python scripts/causal_replay.py resume
    python scripts/causal_replay.py reset --as-of 2026-08-27T18:00:00Z --pause
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import get_session_factory
from app.services.causal_runtime import (
    advance_replay_clock,
    get_replay_state,
    reset_replay_clock,
    set_replay_paused,
)


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone, for example ...Z")
    return parsed.astimezone(UTC)


def state_payload(state) -> dict[str, object]:
    return {
        "simulation_as_of": state.simulation_as_of.isoformat(),
        "replay_start": state.replay_start.isoformat(),
        "replay_end": state.replay_end.isoformat(),
        "replay_speed": state.replay_speed,
        "paused": state.paused,
        "last_tick_at": state.last_tick_at.isoformat(),
        "tick_count": state.tick_count,
        "last_error": state.last_error,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("pause")
    sub.add_parser("resume")
    sub.add_parser("tick")
    reset = sub.add_parser("reset")
    reset.add_argument("--as-of", required=True, dest="as_of")
    reset.add_argument("--speed", type=float, default=None)
    reset.add_argument("--pause", action="store_true")
    reset.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    factory = get_session_factory()
    async with factory() as session:
        if args.command == "status":
            state = await get_replay_state(session, initialize=True)
        elif args.command == "pause":
            state = await set_replay_paused(session, True)
        elif args.command == "resume":
            state = await set_replay_paused(session, False)
        elif args.command == "tick":
            state = await advance_replay_clock(session)
        else:
            paused = True if args.pause else (False if args.resume else None)
            state = await reset_replay_clock(
                session,
                simulation_as_of=parse_timestamp(args.as_of),
                replay_speed=args.speed,
                paused=paused,
            )
    print(json.dumps(state_payload(state), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
