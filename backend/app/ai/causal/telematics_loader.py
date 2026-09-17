"""Runtime loader for the independent vehicle-telematics causal pipeline.

Only the canonical PostgreSQL ``vehicle_telematics_timeseries`` table is
read here.  Physical telemetry is returned as long-format causal records;
vehicle/model/production fields are retained as explanatory metadata and are
never selected as PCMCI variables.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.runtime_schema import runtime_tables

TELEMATICS_TABLE = runtime_tables["vehicle_telematics_timeseries"]
DELIVERIES_TABLE = runtime_tables["deliveries"]

TELEMATICS_METRICS: tuple[str, ...] = (
    "vehicle_speed_kph",
    "ambient_temperature_c",
    "battery_temperature_c",
    "battery_soc_pct",
    "battery_voltage_v",
    "battery_current_a",
    "battery_internal_resistance_ohm",
    "transmission_temperature_c",
    "transmission_slip_ms",
    "torque_converter_slip_rpm",
    "steering_torque_nm",
    "steering_angle_deg",
    "vehicle_vibration_mm_s",
    "vertical_acceleration_g",
    "lateral_acceleration_g",
    "road_roughness_index",
    "impact_g_force",
)

# Context is intentionally separate from TELEMATICS_METRICS.  In particular,
# odometer is a monotonic trend and dtc/warning are downstream evidence.
TELEMATICS_CONTEXT_FIELDS: tuple[str, ...] = (
    "vehicle_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "variant",
    "production_batch_id",
    "supplier_lot_id",
    "plant_id",
    "production_line_id",
)

TELEMATICS_EXCLUDED_FIELDS: tuple[str, ...] = (
    "odometer_km",
    "dtc_count",
    "warning_flag",
    "data_origin",
    "generator_version",
)

DEFAULT_HISTORY_HOURS = 168.0


def _normalise_vehicle_ids(vehicles: Sequence[str]) -> tuple[str, ...]:
    values = tuple(sorted({str(value).strip() for value in vehicles if str(value).strip()}))
    if not values:
        raise ValueError("At least one vehicle ID must be supplied.")
    return values


def _normalise_bound(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime or None.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(UTC)


def _validate_window(
    source_from: datetime | None,
    source_to: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    source_from = _normalise_bound(source_from, "source_from")
    source_to = _normalise_bound(source_to, "source_to")
    if (source_from is None) != (source_to is None):
        raise ValueError("source_from and source_to must be supplied together.")
    if source_from is not None and source_to is not None and source_from >= source_to:
        raise ValueError("source_from must be earlier than source_to.")
    return source_from, source_to


def _validate_history_hours(history_hours: float) -> float:
    try:
        value = float(history_hours)
    except (TypeError, ValueError) as exc:
        raise TypeError("history_hours must be numeric.") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("history_hours must be a finite positive duration.")
    return value


def _row_to_records(row: Any) -> list[dict[str, Any]]:
    vehicle_id = str(row["vehicle_id"])
    context = {field: row[field] for field in TELEMATICS_CONTEXT_FIELDS}
    records: list[dict[str, Any]] = []
    for metric in TELEMATICS_METRICS:
        raw_value = row[metric]
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        records.append(
            {
                "timestamp": row["timestamp"],
                "entity": vehicle_id,
                "metric": metric,
                "value": value,
                **context,
            }
        )
    return records


def rows_to_telematics_records(rows: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert canonical wide rows to the causal long-record contract."""

    records: list[dict[str, Any]] = []
    for row in rows:
        records.extend(_row_to_records(row))
    return records


def _chronology_source() -> tuple[Any, tuple[Any, ...]]:
    source = TELEMATICS_TABLE.join(
        DELIVERIES_TABLE,
        DELIVERIES_TABLE.c.vehicle_id == TELEMATICS_TABLE.c.vehicle_id,
    )
    chronology = (
        DELIVERIES_TABLE.c.actual_delivery_date.is_not(None),
        TELEMATICS_TABLE.c.timestamp >= DELIVERIES_TABLE.c.actual_delivery_date,
    )
    return source, chronology


async def _latest_visible_timestamp(
    session: AsyncSession,
    vehicle_id: str,
    *,
    source_from: datetime | None,
    source_to: datetime | None,
) -> datetime | None:
    source, chronology = _chronology_source()
    query = (
        select(func.max(TELEMATICS_TABLE.c.timestamp))
        .select_from(source)
        .where(TELEMATICS_TABLE.c.vehicle_id == vehicle_id, *chronology)
    )
    if source_to is not None:
        query = query.where(TELEMATICS_TABLE.c.timestamp <= source_to)
    if source_from is not None:
        query = query.where(TELEMATICS_TABLE.c.timestamp >= source_from)
    return (await session.execute(query)).scalar_one_or_none()


async def get_vehicle_visible_latest_timestamp(
    session: AsyncSession,
    vehicle_id: str,
    *,
    source_to: datetime | None = None,
) -> datetime | None:
    """Return one vehicle's latest post-delivery telemetry timestamp, capped
    at ``source_to`` (a replay-safe visibility cutoff). ``None`` when the
    vehicle has no telemetry visible under that cutoff.

    A shared domain-level source plan hands every selected vehicle the same
    ``source_to``, but an individual vehicle's own data may end earlier.
    Callers that need a per-vehicle analytical window (rather than the
    literal domain bound) should re-anchor against this value instead of
    assuming it always equals ``source_to``.
    """

    vehicle_id = str(vehicle_id).strip()
    if not vehicle_id:
        raise ValueError("vehicle_id must not be empty.")
    source_to = _normalise_bound(source_to, "source_to")
    return await _latest_visible_timestamp(session, vehicle_id, source_from=None, source_to=source_to)


async def fetch_vehicle_rows(
    session: AsyncSession,
    vehicle_id: str,
    *,
    history_hours: float = DEFAULT_HISTORY_HOURS,
    source_from: datetime | None = None,
    source_to: datetime | None = None,
) -> list[Any]:
    """Fetch one vehicle's bounded wide source rows from PostgreSQL."""

    vehicle_id = str(vehicle_id).strip()
    if not vehicle_id:
        raise ValueError("vehicle_id must not be empty.")
    history_hours_value = _validate_history_hours(history_hours)
    source_from, source_to = _validate_window(source_from, source_to)

    source, chronology = _chronology_source()
    latest = await _latest_visible_timestamp(session, vehicle_id, source_from=source_from, source_to=source_to)
    if latest is None:
        raise ValueError(f"Unknown vehicle ID or no telemetry: {vehicle_id}")

    query = (
        select(
            TELEMATICS_TABLE.c.timestamp,
            *(TELEMATICS_TABLE.c[field] for field in TELEMATICS_CONTEXT_FIELDS),
            *(TELEMATICS_TABLE.c[field] for field in TELEMATICS_METRICS),
        )
        .select_from(source)
        .where(TELEMATICS_TABLE.c.vehicle_id == vehicle_id, *chronology)
    )

    if source_from is not None and source_to is not None:
        query = query.where(
            TELEMATICS_TABLE.c.timestamp >= source_from,
            TELEMATICS_TABLE.c.timestamp <= source_to,
        )
    else:
        window_start = latest - timedelta(hours=history_hours_value)
        query = query.where(TELEMATICS_TABLE.c.timestamp > window_start)

    query = query.order_by(TELEMATICS_TABLE.c.timestamp.asc())
    rows = (await session.execute(query)).mappings().all()
    if len(rows) < 2:
        raise ValueError(f"Insufficient telemetry history for {vehicle_id}: {len(rows)} rows")
    return rows


async def fetch_vehicle_records(
    session: AsyncSession,
    vehicle_id: str,
    *,
    history_hours: float = DEFAULT_HISTORY_HOURS,
    source_from: datetime | None = None,
    source_to: datetime | None = None,
) -> list[dict[str, Any]]:
    """Fetch one vehicle as long-format physical telemetry records."""

    rows = await fetch_vehicle_rows(
        session,
        vehicle_id,
        history_hours=history_hours,
        source_from=source_from,
        source_to=source_to,
    )
    return rows_to_telematics_records(rows)


async def fetch_raw_records(
    session: AsyncSession,
    vehicle_ids: Sequence[str],
    *,
    history_hours: float = DEFAULT_HISTORY_HOURS,
    source_from: datetime | None = None,
    source_to: datetime | None = None,
) -> list[dict[str, Any]]:
    """Fetch selected vehicles independently; never concatenate boundaries."""

    ids = _normalise_vehicle_ids(vehicle_ids)
    records: list[dict[str, Any]] = []
    for vehicle_id in ids:
        records.extend(
            await fetch_vehicle_records(
                session,
                vehicle_id,
                history_hours=history_hours,
                source_from=source_from,
                source_to=source_to,
            )
        )
    return records


def detect_raw_frequency_minutes(rows_or_records: Sequence[Any]) -> float:
    """Return the modal positive timestamp cadence, calculated per vehicle."""

    timestamps_by_vehicle: dict[str, set[datetime]] = {}
    for item in rows_or_records:
        if isinstance(item, dict):
            vehicle = str(item.get("vehicle_id") or item.get("entity") or "").strip()
            timestamp = item.get("timestamp")
        else:
            vehicle = str(item.get("vehicle_id") or "").strip()
            timestamp = item.get("timestamp")
        if vehicle and timestamp is not None:
            timestamps_by_vehicle.setdefault(vehicle, set()).add(timestamp)

    cadence_seconds: Counter[float] = Counter()
    for timestamps in timestamps_by_vehicle.values():
        ordered = sorted(timestamps)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            delta = (current - previous).total_seconds()
            if delta > 0:
                cadence_seconds[float(delta)] += 1
    if not cadence_seconds:
        raise ValueError("At least two distinct telemetry timestamps are required.")
    mode_seconds = min(cadence_seconds, key=lambda seconds: (-cadence_seconds[seconds], seconds))
    return mode_seconds / 60.0


__all__ = [
    "DEFAULT_HISTORY_HOURS",
    "TELEMATICS_CONTEXT_FIELDS",
    "TELEMATICS_EXCLUDED_FIELDS",
    "TELEMATICS_METRICS",
    "TELEMATICS_TABLE",
    "detect_raw_frequency_minutes",
    "fetch_raw_records",
    "fetch_vehicle_records",
    "fetch_vehicle_rows",
    "get_vehicle_visible_latest_timestamp",
    "rows_to_telematics_records",
]
