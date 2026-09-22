"""
Live database writer for the manufacturing-timeseries,
vehicle-telematics, and mobility-timeseries pipelines.

Inserts each minute's freshly generated rows directly into the
existing PostgreSQL runtime tables:

    manufacturing_timeseries
    vehicle_telematics_timeseries
    mobility_timeseries

These are the SAME tables (same columns, same types, same primary
keys, same foreign keys) already used by
data/scripts/import_postgres.py for the historical bulk import. This
module does not create, alter, or migrate any table — it only runs
plain INSERT statements against the schema exactly as it already
exists.

Connection resolution mirrors data/scripts/import_postgres.py:
    MAHINDRA_DATABASE_URL, then DATABASE_URL, then a local default.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
import pandas as pd

DEFAULT_DATABASE_URL = (
    "postgresql://mahindra:mahindra@127.0.0.1:5432/mahindra_ai"
)

MANUFACTURING_TABLE = "manufacturing_timeseries"
TELEMATICS_TABLE = "vehicle_telematics_timeseries"
MOBILITY_TABLE = "mobility_timeseries"

MANUFACTURING_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "plant_id",
    "plant_name",
    "production_line_id",
    "production_line_name",
    "line_type",
    "machine_id",
    "machine_name",
    "production_batch_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "supplier_lot_id",
    "batch_status",
    "ambient_temperature_c",
    "ambient_humidity_pct",
    "machine_load",
    "machine_temperature_c",
    "vibration_mm_s",
    "power_kw",
    "line_speed_units_per_hour",
    "cycle_time_seconds",
    "hours_since_maintenance",
    "maintenance_overdue_hours",
    "supplier_lot_quality_score",
    "torque_deviation_nm",
    "paint_booth_temperature_c",
    "paint_booth_humidity_pct",
    "paint_defect_rate",
    "defect_rate",
    "rework_rate",
    "downtime_minutes",
    "quality_score",
    "data_origin",
    "generator_version",
)

TELEMATICS_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "vehicle_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "variant",
    "production_batch_id",
    "supplier_lot_id",
    "plant_id",
    "production_line_id",
    "odometer_km",
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
    "dtc_count",
    "warning_flag",
    "data_origin",
    "generator_version",
)

MOBILITY_COLUMNS: tuple[str, ...] = (
    "region_id",
    "region_name",
    "window_start",
    "window_end",
    "lead_count",
    "avg_lead_engagement_score",
    "followup_count",
    "followup_completed_count",
    "customer_response_count",
    "avg_followup_response_minutes",
    "test_drive_requested_count",
    "test_drive_completed_count",
    "test_drive_no_show_count",
    "booking_count",
    "booking_value_inr",
    "finance_application_count",
    "finance_approved_count",
    "finance_rejected_count",
    "finance_manual_review_count",
    "avg_finance_approval_tat_hours",
    "cancellation_count",
    "allocated_vehicle_count",
    "avg_allocation_wait_hours",
    "delivered_vehicle_count",
    "delayed_delivery_count",
    "avg_delivery_delay_days",
    "service_event_count",
    "unscheduled_repair_count",
    "warranty_claim_count",
    "warranty_approved_count",
    "warranty_claim_amount_inr",
    "waitlisted_booking_count",
    "data_origin",
    "generator_version",
)


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql://" + value[len("postgresql+asyncpg://") :]
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def resolve_database_url() -> str:
    """
    Resolve the database URL the same way
    data/scripts/import_postgres.py does: MAHINDRA_DATABASE_URL, then
    DATABASE_URL, then a local default.
    """

    raw = (
        os.getenv("MAHINDRA_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )

    return _normalize_database_url(raw)


def _row_values(
    row: dict[str, Any], columns: tuple[str, ...]
) -> tuple[Any, ...]:

    values = []

    for column in columns:
        value = row.get(column)

        if value is None:
            values.append(None)
            continue

        if isinstance(value, float) and pd.isna(value):
            values.append(None)
            continue

        values.append(value)

    return tuple(values)


class LiveDatabaseWriter:
    """
    Holds a single pooled connection to PostgreSQL and inserts new
    minute-batches of rows into the existing runtime tables.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or resolve_database_url()
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=2,
            )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _insert_rows(
        self,
        table_name: str,
        columns: tuple[str, ...],
        rows: pd.DataFrame,
    ) -> int:

        if self._pool is None:
            raise RuntimeError(
                "LiveDatabaseWriter.connect() must be called first"
            )

        if rows.empty:
            return 0

        records = rows.to_dict(orient="records")

        payload = [_row_values(record, columns) for record in records]

        column_list = ", ".join(columns)
        placeholders = ", ".join(
            f"${index}" for index in range(1, len(columns) + 1)
        )

        insert_sql = (
            f"INSERT INTO {table_name} ({column_list}) "
            f"VALUES ({placeholders})"
        )

        async with self._pool.acquire() as connection:
            await connection.executemany(insert_sql, payload)

        return len(payload)

    async def insert_manufacturing_rows(
        self, rows: pd.DataFrame
    ) -> int:
        return await self._insert_rows(
            MANUFACTURING_TABLE, MANUFACTURING_COLUMNS, rows
        )

    async def insert_telematics_rows(self, rows: pd.DataFrame) -> int:
        return await self._insert_rows(
            TELEMATICS_TABLE, TELEMATICS_COLUMNS, rows
        )

    async def insert_mobility_rows(self, rows: pd.DataFrame) -> int:
        return await self._insert_rows(
            MOBILITY_TABLE, MOBILITY_COLUMNS, rows
        )
