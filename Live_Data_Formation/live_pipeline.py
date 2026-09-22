"""
Live manufacturing-timeseries, vehicle-telematics, and
mobility-timeseries pipeline.

Generates a fresh batch of manufacturing sensor rows, a fresh batch
of vehicle telematics rows (50-100 rows/minute each), AND one fresh
regional business-observation row per region (mobility_timeseries)
once every minute, and writes each domain's minute batch to its own
Parquet file under:

    Manufacturing_Timseries/Data_Parquet/<YYYY-MM-DD>/<HH>/<HH-MM>.parquet
    Vechicle_Telematics/Data_Parquet/<YYYY-MM-DD>/<HH>/<HH-MM>.parquet
    Mobility_Timeseries/Data_Parquet/<YYYY-MM-DD>/<HH>/<HH-MM>.parquet

Folders are partitioned by IST calendar date and hour so historical
minute files stay easy to browse.

Every tick also inserts that same batch of new rows directly into
the existing PostgreSQL runtime tables (manufacturing_timeseries,
vehicle_telematics_timeseries, and mobility_timeseries) via
db_writer.py, using plain INSERT statements against the schema
exactly as it already exists. If the database is unreachable, the
tick still completes and its Parquet files/log lines are still
written; only the DB insert for that tick is skipped and reported.

Every tick also appends one line per domain to pipeline.log
recording the IST timestamp and how many new rows were generated
that minute.

This script and its sibling modules (master_data.py,
live_row_generator.py, telematics_master_data.py,
live_telematics_generator.py, mobility_master_data.py,
live_mobility_generator.py, db_writer.py) are the ONLY new files
added for this feature. Nothing under Mahindra AI Nexus/data/ is
modified, and the existing database schema is not changed in any
way.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

LIVE_ROOT = Path(__file__).resolve().parent
MANUFACTURING_MODULE_DIR = LIVE_ROOT / "Manufacturing_Timseries"
TELEMATICS_MODULE_DIR = LIVE_ROOT / "Vechicle_Telematics"
MOBILITY_MODULE_DIR = LIVE_ROOT / "Mobility_Timeseries"

for module_dir in (
    MANUFACTURING_MODULE_DIR,
    TELEMATICS_MODULE_DIR,
    MOBILITY_MODULE_DIR,
):
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

from master_data import build_master_context, build_batch_context
from live_row_generator import LiveManufacturingGenerator

from telematics_master_data import build_delivered_vehicle_pool
from live_telematics_generator import LiveTelematicsGenerator

from mobility_master_data import build_region_master
from live_mobility_generator import LiveMobilityGenerator

from db_writer import (
    LiveDatabaseWriter,
    MANUFACTURING_TABLE,
    TELEMATICS_TABLE,
    MOBILITY_TABLE,
)

MANUFACTURING_DATA_ROOT = (
    LIVE_ROOT / "Manufacturing_Timseries" / "Data_Parquet"
)
TELEMATICS_DATA_ROOT = LIVE_ROOT / "Vechicle_Telematics" / "Data_Parquet"
MOBILITY_DATA_ROOT = LIVE_ROOT / "Mobility_Timeseries" / "Data_Parquet"

PIPELINE_LOG_PATH = LIVE_ROOT / "pipeline.log"

IST = pytz.timezone("Asia/Kolkata")

MIN_ROWS_PER_MINUTE = 50
MAX_ROWS_PER_MINUTE = 100

TICK_SECONDS = 60


def _select_machine_pool(machines: pd.DataFrame) -> list:
    """
    Pick a fixed, varied pool of machines to sample from every tick.

    Uses every machine so the live feed reflects all 7 plants and
    all 4 line types, giving column variety (plant_name, line_type,
    machine_type, ...) across ticks.
    """

    return machines["machine_id"].astype(str).tolist()


def _select_vehicle_pool(deliveries: pd.DataFrame) -> list:
    """
    Pick the full delivered-vehicle roster to sample from every
    tick, so the live feed reflects a wide variety of vehicle
    models, variants, and plants.
    """

    return deliveries["vehicle_id"].astype(str).tolist()


def _select_region_pool(regions: pd.DataFrame) -> list:
    """
    Mobility observations are per-region, not per-entity - there are
    only 4 regions total (unlike thousands of machines/vehicles), so
    every tick generates one row for every region rather than
    sampling a subset.
    """

    return regions["region_id"].astype(str).tolist()


def _write_minute_parquet(
    data_root: Path, rows: pd.DataFrame, tick_time_ist: datetime
) -> Path:

    date_folder = tick_time_ist.strftime("%Y-%m-%d")
    hour_folder = tick_time_ist.strftime("%H")
    minute_file = tick_time_ist.strftime("%H-%M") + ".parquet"

    out_dir = data_root / date_folder / hour_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / minute_file

    rows.to_parquet(out_path, index=False)

    return out_path


def _log_tick(
    tick_time_ist: datetime,
    dataset_name: str,
    row_count: int,
    db_status: str,
) -> None:

    timestamp_str = tick_time_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    line = (
        f"{timestamp_str} | dataset={dataset_name} | "
        f"new_rows_generated={row_count} | db_insert={db_status}\n"
    )

    with PIPELINE_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(line)

    print(line, end="")


def _log_service_event(event: str) -> None:
    """
    Append a SERVICE_STARTED / SERVICE_STOPPED line to pipeline.log
    so it's possible to confirm, just by reading the log file,
    whether the live-data-formation systemd service is currently
    running.
    """

    tick_time_ist = datetime.now(IST)
    timestamp_str = tick_time_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    line = f"{timestamp_str} | event={event}\n"

    with PIPELINE_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(line)

    print(line, end="")


async def run_manufacturing_tick(
    generator: LiveManufacturingGenerator,
    machine_pool: list,
    rng,
    tick_time_ist: datetime,
    db_writer: LiveDatabaseWriter,
) -> None:

    row_target = int(
        rng.integers(MIN_ROWS_PER_MINUTE, MAX_ROWS_PER_MINUTE + 1)
    )

    selected_machine_ids = rng.choice(
        machine_pool, size=row_target, replace=False
    ).tolist()

    timestamp = pd.Timestamp(tick_time_ist)

    rows = generator.generate_tick(selected_machine_ids, timestamp)

    _write_minute_parquet(MANUFACTURING_DATA_ROOT, rows, tick_time_ist)

    db_status = "skipped"

    try:
        inserted = await db_writer.insert_manufacturing_rows(rows)
        db_status = f"ok({inserted})"
    except Exception as exc:
        db_status = "failed"
        print(
            f"Manufacturing DB insert failed: {exc}", file=sys.stderr
        )

    _log_tick(
        tick_time_ist, "manufacturing_timeseries", len(rows), db_status
    )


async def run_telematics_tick(
    generator: LiveTelematicsGenerator,
    vehicle_pool: list,
    rng,
    tick_time_ist: datetime,
    db_writer: LiveDatabaseWriter,
) -> None:

    row_target = int(
        rng.integers(MIN_ROWS_PER_MINUTE, MAX_ROWS_PER_MINUTE + 1)
    )

    selected_vehicle_ids = rng.choice(
        vehicle_pool, size=row_target, replace=False
    ).tolist()

    timestamp = pd.Timestamp(tick_time_ist)

    rows = generator.generate_tick(selected_vehicle_ids, timestamp)

    _write_minute_parquet(TELEMATICS_DATA_ROOT, rows, tick_time_ist)

    db_status = "skipped"

    try:
        inserted = await db_writer.insert_telematics_rows(rows)
        db_status = f"ok({inserted})"
    except Exception as exc:
        db_status = "failed"
        print(f"Telematics DB insert failed: {exc}", file=sys.stderr)

    _log_tick(
        tick_time_ist,
        "vehicle_telematics_timeseries",
        len(rows),
        db_status,
    )


async def run_mobility_tick(
    generator: LiveMobilityGenerator,
    region_pool: list,
    tick_time_ist: datetime,
    db_writer: LiveDatabaseWriter,
) -> None:

    timestamp = pd.Timestamp(tick_time_ist)

    rows = generator.generate_tick(region_pool, timestamp)

    _write_minute_parquet(MOBILITY_DATA_ROOT, rows, tick_time_ist)

    db_status = "skipped"

    try:
        inserted = await db_writer.insert_mobility_rows(rows)
        db_status = f"ok({inserted})"
    except Exception as exc:
        db_status = "failed"
        print(f"Mobility DB insert failed: {exc}", file=sys.stderr)

    _log_tick(tick_time_ist, "mobility_timeseries", len(rows), db_status)


async def main() -> None:

    import numpy as np

    _log_service_event("SERVICE_STARTED")

    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # add_signal_handler is unavailable on some platforms
            # (e.g. Windows); fall back to the default signal module.
            signal.signal(sig, _request_stop)

    db_writer = LiveDatabaseWriter()

    try:
        await db_writer.connect()
        print(
            "Connected to PostgreSQL for live inserts "
            f"({MANUFACTURING_TABLE}, {TELEMATICS_TABLE}, {MOBILITY_TABLE})."
        )
    except Exception as exc:
        print(
            "Could not connect to PostgreSQL; ticks will continue "
            f"writing Parquet/log output only. Error: {exc}",
            file=sys.stderr,
        )

    print("Building manufacturing master data (plants, lines, machines, batches)...")

    manufacturing_context = build_master_context()

    manufacturing_batch_context = build_batch_context(
        manufacturing_context["production_batches"]
    )

    manufacturing_generator = LiveManufacturingGenerator(
        machines=manufacturing_context["machines"],
        plants=manufacturing_context["plants"],
        production_lines=manufacturing_context["production_lines"],
        batch_context=manufacturing_batch_context,
        generation=manufacturing_context["generation"],
    )

    machine_pool = _select_machine_pool(manufacturing_context["machines"])

    print(
        f"Manufacturing master data ready: "
        f"{len(manufacturing_context['plants'])} plants, "
        f"{len(manufacturing_context['production_lines'])} production lines, "
        f"{len(machine_pool)} machines available for sampling."
    )

    print("Building vehicle-telematics master data (delivered vehicle roster)...")

    telematics_context = build_delivered_vehicle_pool()

    telematics_generator = LiveTelematicsGenerator(
        deliveries=telematics_context["deliveries"],
        generation=telematics_context["generation"],
    )

    vehicle_pool = _select_vehicle_pool(telematics_context["deliveries"])

    print(
        f"Vehicle-telematics master data ready: "
        f"{len(vehicle_pool)} delivered vehicles available for sampling."
    )

    print("Building mobility master data (region roster + calibration)...")

    mobility_master = build_region_master()

    generation_provenance = telematics_context["generation"].get("provenance", {})

    mobility_generator = LiveMobilityGenerator(
        regions=mobility_master["regions"],
        calibration=mobility_master["calibration"],
        seed=int(telematics_context["generation"]["seed"]),
        data_origin=str(generation_provenance.get("data_origin", "SYNTHETIC")),
        generator_version=str(
            telematics_context["generation"].get("generator_version", "1.0.0")
        ),
    )

    region_pool = _select_region_pool(mobility_master["regions"])

    print(
        f"Mobility master data ready: "
        f"{len(region_pool)} regions available (one row/region/tick)."
    )

    print(
        f"Starting live pipeline: 1 tick every {TICK_SECONDS}s, "
        f"{MIN_ROWS_PER_MINUTE}-{MAX_ROWS_PER_MINUTE} rows/tick for "
        f"manufacturing/telematics, {len(region_pool)} rows/tick for mobility."
    )

    rng = np.random.default_rng()

    try:
        while not stop_event.is_set():

            tick_start = time.monotonic()

            tick_time_ist = datetime.now(IST)

            try:
                await run_manufacturing_tick(
                    manufacturing_generator,
                    machine_pool,
                    rng,
                    tick_time_ist,
                    db_writer,
                )
            except Exception as exc:
                print(
                    f"Manufacturing tick failed: {exc}", file=sys.stderr
                )

            try:
                await run_telematics_tick(
                    telematics_generator,
                    vehicle_pool,
                    rng,
                    tick_time_ist,
                    db_writer,
                )
            except Exception as exc:
                print(f"Telematics tick failed: {exc}", file=sys.stderr)

            try:
                await run_mobility_tick(
                    mobility_generator,
                    region_pool,
                    tick_time_ist,
                    db_writer,
                )
            except Exception as exc:
                print(f"Mobility tick failed: {exc}", file=sys.stderr)

            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, TICK_SECONDS - elapsed)

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=sleep_for
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await db_writer.close()
        _log_service_event("SERVICE_STOPPED")


if __name__ == "__main__":
    asyncio.run(main())
