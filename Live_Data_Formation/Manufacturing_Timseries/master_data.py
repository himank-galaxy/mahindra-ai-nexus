"""
Master-data bootstrap for the live manufacturing-timeseries pipeline.

Reuses the existing, unmodified Synthetic Data Factory generators
(plants, production lines, machines, vehicle models, suppliers,
production batches) to build the static context that manufacturing
sensor readings are attached to.

This module does NOT modify anything under Mahindra AI Nexus/data/.
It only imports and calls the already-existing generator functions.

Master data (plants/lines/machines/batches) does not change minute
to minute in real manufacturing operations, so it is built once per
process start and reused for every live tick.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ------------------------------------------------------------------
# Make the existing "Mahindra AI Nexus" package importable without
# modifying it. Its generators are written as `data.generators...`
# absolute imports, so its own directory must be on sys.path.
# ------------------------------------------------------------------

NEXUS_ROOT = Path(__file__).resolve().parents[2]

if str(NEXUS_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXUS_ROOT))

from data.generators.common.helpers import load_generation_config
from data.generators.master.geography import generate_geography
from data.generators.master.plants import generate_plant_master
from data.generators.master.machines import generate_machine_master
from data.generators.master.vehicle_models import generate_vehicle_models
from data.generators.auto.suppliers import generate_supplier_master
from data.generators.auto.production import generate_production_batches


def build_master_context() -> dict[str, Any]:
    """
    Build the full static master-data context needed to attach
    production-batch context to manufacturing sensor readings.

    Returns a dict with:
        plants, production_lines, machines, production_batches,
        generation, distributions
    """

    generation = load_generation_config()

    _, cities = generate_geography()

    plants, production_lines = generate_plant_master(
        geography_cities=cities,
        generation=generation,
    )

    machines = generate_machine_master(
        production_lines=production_lines,
        generation=generation,
    )

    vehicle_models = generate_vehicle_models(
        generation=generation,
    )

    suppliers, supplier_lots = generate_supplier_master(
        cities=cities,
        generation=generation,
    )

    production_batches = generate_production_batches(
        plants=plants,
        production_lines=production_lines,
        machines=machines,
        vehicle_models=vehicle_models,
        suppliers=suppliers,
        supplier_lots=supplier_lots,
        generation=generation,
    )

    return {
        "plants": plants,
        "production_lines": production_lines,
        "machines": machines,
        "production_batches": production_batches,
        "generation": generation,
    }


def build_batch_context(production_batches: pd.DataFrame) -> dict:
    """
    Build a (plant_id, calendar_day) -> batch context lookup,
    mirroring the logic in data/generators/causal/manufacturing_timeseries.py
    so batch-linked fields (vehicle model, supplier lot, supplier
    quality) stay consistent with the rest of the synthetic factory.

    The underlying production_batches only cover the historical
    generation window (2026-01-01 .. 2026-07-31). The live pipeline
    runs on the real current date, which falls outside that window,
    so each plant's historical batch calendar is additionally keyed
    by "day position within that plant's own batch history" (0, 1,
    2, ...) and the live pipeline looks up
    day_index % plant_batch_day_count. This keeps every live tick
    linked to a real, varied batch/vehicle/supplier context instead
    of silently falling back to defaults every day.
    """

    lookup: dict[tuple[str, Any], dict[str, Any]] = {}
    day_index_lookup: dict[str, dict[int, dict[str, Any]]] = {}

    batches = production_batches.sort_values(
        ["plant_id", "production_date", "production_batch_id"]
    )

    production_dates = pd.to_datetime(
        batches["production_date"]
    ).dt.date

    for (batch, calendar_day) in zip(
        batches.itertuples(index=False),
        production_dates,
    ):

        plant_id = str(batch.plant_id)

        context = {
            "production_batch_id": str(batch.production_batch_id),
            "vehicle_model_id": str(batch.vehicle_model_id),
            "vehicle_model_name": str(batch.vehicle_model_name),
            "supplier_lot_id": str(batch.primary_supplier_lot_id),
            "supplier_lot_quality_score": float(
                batch.supplier_lot_quality_score
            ),
            "batch_quality_score": float(batch.quality_score),
            "batch_status": str(batch.batch_status),
        }

        lookup[(plant_id, calendar_day)] = context

        plant_days = day_index_lookup.setdefault(plant_id, {})
        plant_days[len(plant_days)] = context

    lookup["__day_index__"] = day_index_lookup

    return lookup


def lookup_batch_context(
    batch_context: dict, plant_id: str, calendar_day: Any
) -> dict | None:
    """
    Resolve batch context for a plant/day, falling back to that
    plant's historical batch calendar (cycled by day-of-year) when
    the exact calendar day has no synthetic production batch, which
    is always true for live/current dates.
    """

    exact = batch_context.get((str(plant_id), calendar_day))

    if exact is not None:
        return exact

    plant_days = batch_context.get("__day_index__", {}).get(
        str(plant_id)
    )

    if not plant_days:
        return None

    day_of_year = calendar_day.timetuple().tm_yday
    cycled_index = day_of_year % len(plant_days)

    return plant_days[cycled_index]
