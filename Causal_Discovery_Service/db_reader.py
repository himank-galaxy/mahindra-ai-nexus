"""
Read-only PostgreSQL access for the Causal Discovery Service.

This module never runs INSERT, UPDATE, or DELETE. Every function here only
ever issues SELECT statements against manufacturing_timeseries and
vehicle_telematics_timeseries.

Written independently of data-Mahindra_AI_Opportunity/.../Live_Data_Formation/db_writer.py
and of any backend/app/database module: no import from either.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from config import resolve_database_url


class ReadOnlyDatabaseReader:
    """
    Thin, read-only asyncpg wrapper. Holds a small connection pool and
    exposes exactly the queries this service needs.
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

    async def _fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        if self._pool is None:
            raise RuntimeError(
                "ReadOnlyDatabaseReader.connect() must be called first"
            )
        async with self._pool.acquire() as connection:
            return await connection.fetch(query, *args)

    # -----------------------------------------------------------------
    # Manufacturing
    # -----------------------------------------------------------------

    async def manufacturing_row_counts(
        self, window_start: datetime, window_end: datetime
    ) -> dict[str, int]:
        """
        Raw row count per machine_id inside [window_start, window_end),
        used for entity selection (§6 of the implementation plan: pick the
        entities with the most data).
        """

        rows = await self._fetch(
            """
            SELECT machine_id, COUNT(*) AS row_count
            FROM manufacturing_timeseries
            WHERE timestamp >= $1 AND timestamp < $2
            GROUP BY machine_id
            """,
            window_start,
            window_end,
        )
        return {row["machine_id"]: int(row["row_count"]) for row in rows}

    async def manufacturing_rows(
        self,
        machine_ids: list[str],
        window_start: datetime,
        window_end: datetime,
        columns: tuple[str, ...],
    ) -> list[asyncpg.Record]:
        """
        Fetch the requested columns for the given machines inside the
        window. `columns` must already exclude anything not present in the
        table; the caller (panel_builder) is responsible for that.
        """

        if not machine_ids:
            return []

        column_list = ", ".join(columns)
        rows = await self._fetch(
            f"""
            SELECT {column_list}
            FROM manufacturing_timeseries
            WHERE machine_id = ANY($1::text[])
              AND timestamp >= $2 AND timestamp < $3
            ORDER BY timestamp
            """,
            machine_ids,
            window_start,
            window_end,
        )
        return rows

    # -----------------------------------------------------------------
    # Telematics
    # -----------------------------------------------------------------

    async def telematics_row_counts(
        self, window_start: datetime, window_end: datetime
    ) -> dict[str, int]:

        rows = await self._fetch(
            """
            SELECT vehicle_id, COUNT(*) AS row_count
            FROM vehicle_telematics_timeseries
            WHERE timestamp >= $1 AND timestamp < $2
            GROUP BY vehicle_id
            """,
            window_start,
            window_end,
        )
        return {row["vehicle_id"]: int(row["row_count"]) for row in rows}

    async def telematics_rows(
        self,
        vehicle_ids: list[str],
        window_start: datetime,
        window_end: datetime,
        columns: tuple[str, ...],
    ) -> list[asyncpg.Record]:

        if not vehicle_ids:
            return []

        column_list = ", ".join(columns)
        rows = await self._fetch(
            f"""
            SELECT {column_list}
            FROM vehicle_telematics_timeseries
            WHERE vehicle_id = ANY($1::text[])
              AND timestamp >= $2 AND timestamp < $3
            ORDER BY timestamp
            """,
            vehicle_ids,
            window_start,
            window_end,
        )
        return rows

    # -----------------------------------------------------------------
    # Shared helper
    # -----------------------------------------------------------------

    async def latest_timestamp(self, table_name: str) -> datetime | None:
        """
        Newest row currently in the given table. Used to anchor a rolling
        window on "now" as understood by the data itself, not the wall
        clock of the machine running this script.
        """

        if table_name not in ("manufacturing_timeseries", "vehicle_telematics_timeseries"):
            raise ValueError(f"Unsupported table_name: {table_name}")

        rows = await self._fetch(f"SELECT MAX(timestamp) AS latest FROM {table_name}")
        value = rows[0]["latest"] if rows else None
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def compute_window(
    window_end: datetime, window_hours: int
) -> tuple[datetime, datetime]:
    """
    Small shared helper: [window_end - window_hours, window_end).
    """

    window_start = window_end - timedelta(hours=window_hours)
    return window_start, window_end
