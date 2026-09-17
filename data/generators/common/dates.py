"""
Date/time utilities for the Mahindra AI Nexus Synthetic Data Factory.

Purpose:
- Generate timestamps inside the configured synthetic-data window.
- Preserve event ordering.
- Generate regular manufacturing/logistics time-series timestamps.
"""

from __future__ import annotations

import random
import re

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Kolkata"


def parse_datetime(
    value: str | date | datetime,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Convert a string/date/datetime to a timezone-aware datetime.

    Supported examples:
        "2026-01-01"
        "2026-01-01T10:30:00"
    """

    tz = ZoneInfo(timezone)

    if isinstance(value, datetime):
        result = value

    elif isinstance(value, date):
        result = datetime.combine(
            value,
            datetime.min.time(),
        )

    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid datetime value: {value}"
            ) from exc

    else:
        raise TypeError(
            "value must be a string, date, or datetime"
        )

    if result.tzinfo is None:
        result = result.replace(tzinfo=tz)
    else:
        result = result.astimezone(tz)

    return result


def random_datetime(
    start: str | date | datetime,
    end: str | date | datetime,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Generate a random timestamp between start and end.
    """

    start_dt = parse_datetime(
        start,
        timezone,
    )

    end_dt = parse_datetime(
        end,
        timezone,
    )

    if end_dt <= start_dt:
        raise ValueError(
            "end must be later than start"
        )

    total_seconds = (
        end_dt - start_dt
    ).total_seconds()

    offset_seconds = random.uniform(
        0,
        total_seconds,
    )

    return start_dt + timedelta(
        seconds=offset_seconds
    )


def add_random_hours(
    timestamp: str | date | datetime,
    min_hours: float,
    max_hours: float,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Add a random number of hours to a timestamp.

    Useful for:
        lead -> follow-up
        finance submitted -> finance decision
    """

    if min_hours > max_hours:
        raise ValueError(
            "min_hours cannot be greater than max_hours"
        )

    ts = parse_datetime(
        timestamp,
        timezone,
    )

    hours = random.uniform(
        min_hours,
        max_hours,
    )

    return ts + timedelta(
        hours=hours
    )


def add_random_days(
    timestamp: str | date | datetime,
    min_days: float,
    max_days: float,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Add a random number of days to a timestamp.

    Useful for:
        test drive -> booking
        booking -> allocation
        delivery -> service
    """

    if min_days > max_days:
        raise ValueError(
            "min_days cannot be greater than max_days"
        )

    ts = parse_datetime(
        timestamp,
        timezone,
    )

    days = random.uniform(
        min_days,
        max_days,
    )

    return ts + timedelta(
        days=days
    )


def ensure_after(
    timestamp: str | date | datetime,
    reference: str | date | datetime,
    minimum_gap: timedelta = timedelta(seconds=1),
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """
    Ensure timestamp occurs after reference.

    If timestamp is already valid, it is returned unchanged.
    Otherwise it is moved to reference + minimum_gap.
    """

    ts = parse_datetime(
        timestamp,
        timezone,
    )

    ref = parse_datetime(
        reference,
        timezone,
    )

    minimum_allowed = ref + minimum_gap

    if ts < minimum_allowed:
        return minimum_allowed

    return ts


def parse_frequency(frequency: str) -> timedelta:
    """
    Convert a frequency string into timedelta.

    Supported:
        hourly
        daily
        1h
        6h
        30m
        15min
        1d
    """

    value = frequency.strip().lower()

    aliases = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
    }

    if value in aliases:
        return aliases[value]

    pattern = re.fullmatch(
        r"(\d+)\s*(h|hr|hour|hours|m|min|minute|minutes|d|day|days)",
        value,
    )

    if not pattern:
        raise ValueError(
            f"Unsupported frequency: {frequency}"
        )

    amount = int(pattern.group(1))
    unit = pattern.group(2)

    if amount <= 0:
        raise ValueError(
            "frequency amount must be > 0"
        )

    if unit in {"h", "hr", "hour", "hours"}:
        return timedelta(hours=amount)

    if unit in {"m", "min", "minute", "minutes"}:
        return timedelta(minutes=amount)

    if unit in {"d", "day", "days"}:
        return timedelta(days=amount)

    raise ValueError(
        f"Unsupported frequency: {frequency}"
    )


def generate_time_range(
    start: str | date | datetime,
    end: str | date | datetime,
    frequency: str = "1h",
    timezone: str = DEFAULT_TIMEZONE,
) -> list[datetime]:
    """
    Generate ordered timestamps from start to end.

    Example:
        generate_time_range(
            "2026-01-01",
            "2026-01-03",
            "1h",
        )
    """

    start_dt = parse_datetime(
        start,
        timezone,
    )

    end_dt = parse_datetime(
        end,
        timezone,
    )

    if end_dt < start_dt:
        raise ValueError(
            "end cannot be earlier than start"
        )

    step = parse_frequency(
        frequency
    )

    timestamps: list[datetime] = []

    current = start_dt

    while current <= end_dt:
        timestamps.append(current)
        current += step

    return timestamps


def get_shift(
    timestamp: str | date | datetime,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Convert a timestamp to a manufacturing shift.

    Default synthetic convention:

        Shift A: 06:00 - 13:59
        Shift B: 14:00 - 21:59
        Shift C: 22:00 - 05:59
    """

    ts = parse_datetime(
        timestamp,
        timezone,
    )

    hour = ts.hour

    if 6 <= hour < 14:
        return "A"

    if 14 <= hour < 22:
        return "B"

    return "C"


def to_iso(
    timestamp: str | date | datetime,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    """
    Convert timestamp to ISO-8601 text.
    """

    return parse_datetime(
        timestamp,
        timezone,
    ).isoformat()