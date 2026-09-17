
"""
Synthetic Production Batch generator for Mahindra AI Nexus.

Creates operational production batches from:
- plants
- production lines
- machines
- vehicle models
- suppliers
- supplier lots

Does NOT write CSV files. generate_all.py will persist them later.

This is separate from causal/manufacturing_timeseries.py, which will
generate the hourly sensor series used by PCMCI.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from data.generators.common.helpers import load_generation_config
from data.generators.common.ids import make_entity_id
from data.generators.common.seed import derive_seed, make_rng


PRODUCTION_DAY_START_HOUR = 6
CAPACITY_SCALE_FACTOR = 1.20
MIN_BATCH_UNITS = 70
MAX_BATCH_UNITS = 320
MIN_BATCH_DURATION_HOURS = 8.0
MAX_BATCH_DURATION_HOURS = 14.0
RECENT_SUPPLIER_LOT_DAYS = 60
DEFAULT_MACHINE_CAPACITY_UNITS_PER_HOUR = 40.0
DEFAULT_MACHINE_LOAD_PCT = 75.0

RELEASE_MIN_FINAL_YIELD = 0.975
RELEASE_MIN_QUALITY_SCORE = 0.86
REVIEW_MIN_FINAL_YIELD = 0.94
REVIEW_MIN_QUALITY_SCORE = 0.76

VALID_BATCH_STATUSES = {"RELEASED", "QUALITY_REVIEW", "REJECTED"}
VALID_SHIFTS = {"A", "B", "C"}
VALID_VARIANTS = ("SYN_BASE", "SYN_MID", "SYN_PREMIUM")
VARIANT_WEIGHTS = (0.35, 0.45, 0.20)


def _find_column(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
    dataset_name: str,
    logical_name: str,
) -> str:
    for candidate in candidates:
        if candidate in dataframe.columns:
            return candidate
    raise ValueError(
        f"{dataset_name} is missing the column required for {logical_name}. "
        f"Expected one of: {', '.join(candidates)}"
    )


def _find_optional_column(
    dataframe: pd.DataFrame,
    candidates: Sequence[str],
) -> str | None:
    for candidate in candidates:
        if candidate in dataframe.columns:
            return candidate
    return None


def _to_bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)

    true_values = {"TRUE", "1", "YES", "Y", "ACTIVE"}
    false_values = {"FALSE", "0", "NO", "N", "INACTIVE"}

    def convert(value: Any) -> bool:
        if pd.isna(value):
            return False
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer, float, np.floating)):
            return bool(value)

        text = str(value).strip().upper()
        if text in true_values:
            return True
        if text in false_values:
            return False
        return bool(text)

    return series.map(convert).astype(bool)


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    time_config = generation.get("time")
    if not isinstance(time_config, Mapping):
        time_config = generation.get("time_window")
    if not isinstance(time_config, Mapping):
        raise KeyError(
            "Missing generation time configuration. "
            "Expected generation.time or generation.time_window."
        )

    start_value = time_config.get("start", time_config.get("start_date"))
    end_value = time_config.get("end", time_config.get("end_date"))
    if start_value is None:
        raise KeyError("Missing generation start/start_date")
    if end_value is None:
        raise KeyError("Missing generation end/end_date")

    timezone = str(time_config.get("timezone", "Asia/Kolkata"))
    start = pd.Timestamp(start_value)
    end = pd.Timestamp(end_value)

    start = start.tz_localize(timezone) if start.tzinfo is None else start.tz_convert(timezone)
    end = end.tz_localize(timezone) if end.tzinfo is None else end.tz_convert(timezone)

    if end <= start:
        raise ValueError("Generation end must be later than generation start")

    return start, end, timezone


def _complexity_score(value: Any) -> float:
    if isinstance(value, str):
        mapping = {
            "LOW": 0.30,
            "MEDIUM": 0.55,
            "HIGH": 0.80,
            "VERY_HIGH": 0.95,
        }
        label = value.strip().upper()
        if label in mapping:
            return mapping[label]

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "production_complexity must be numeric or one of "
            "LOW/MEDIUM/HIGH/VERY_HIGH"
        ) from exc

    return float(np.clip(result, 0.0, 1.0))


def _normalize_load_pct(value: Any) -> float:
    try:
        load = float(value)
    except (TypeError, ValueError):
        load = DEFAULT_MACHINE_LOAD_PCT

    if load <= 1.0:
        load *= 100.0

    return float(np.clip(load, 0.0, 100.0))


def _prepare_inputs(
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    suppliers: pd.DataFrame,
    supplier_lots: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Canonicalize upstream schemas.

    Important fix:
    - plants.active is optional
    - production_lines.active is optional
    - machines.active is optional

    If missing, generated records are treated as active.
    """

    for name, df in {
        "plants": plants,
        "production_lines": production_lines,
        "machines": machines,
        "vehicle_models": vehicle_models,
        "suppliers": suppliers,
        "supplier_lots": supplier_lots,
    }.items():
        if df.empty:
            raise ValueError(f"{name} DataFrame cannot be empty")

    # Plants
    plant_id = _find_column(plants, ("plant_id",), "plants", "plant ID")
    plant_name = _find_column(plants, ("plant_name", "name"), "plants", "plant name")
    plant_active = _find_optional_column(plants, ("active", "is_active"))

    plant_cols = [plant_id, plant_name] + ([plant_active] if plant_active else [])
    p = plants[plant_cols].copy().rename(
        columns={plant_id: "plant_id", plant_name: "plant_name"}
    )
    if plant_active:
        p = p.rename(columns={plant_active: "active"})
        p["active"] = _to_bool_series(p["active"])
    else:
        p["active"] = True

    # Production lines
    line_id = _find_column(
        production_lines,
        ("production_line_id", "line_id"),
        "production_lines",
        "production-line ID",
    )
    line_plant = _find_column(
        production_lines,
        ("plant_id",),
        "production_lines",
        "plant ID",
    )
    line_name = _find_column(
        production_lines,
        ("line_name", "production_line_name", "name"),
        "production_lines",
        "line name",
    )
    line_type = _find_column(
        production_lines,
        ("line_type", "station_type", "production_line_type"),
        "production_lines",
        "line type",
    )
    line_active = _find_optional_column(production_lines, ("active", "is_active"))

    line_cols = [line_id, line_plant, line_name, line_type]
    if line_active:
        line_cols.append(line_active)

    l = production_lines[line_cols].copy().rename(
        columns={
            line_id: "production_line_id",
            line_plant: "plant_id",
            line_name: "production_line_name",
            line_type: "line_type",
        }
    )
    if line_active:
        l = l.rename(columns={line_active: "active"})
        l["active"] = _to_bool_series(l["active"])
    else:
        l["active"] = True

    # Machines
    machine_id = _find_column(machines, ("machine_id",), "machines", "machine ID")
    machine_line = _find_column(
        machines,
        ("production_line_id", "line_id"),
        "machines",
        "production-line ID",
    )
    machine_name = _find_column(
        machines,
        ("machine_name", "name"),
        "machines",
        "machine name",
    )
    machine_plant = _find_optional_column(machines, ("plant_id",))
    machine_capacity = _find_optional_column(
        machines,
        (
            "rated_capacity_units_per_hour",
            "capacity_units_per_hour",
            "hourly_capacity_units",
            "hourly_capacity",
        ),
    )
    machine_load = _find_optional_column(
        machines,
        ("baseline_load_pct", "baseline_load", "load_pct"),
    )
    machine_active = _find_optional_column(machines, ("active", "is_active"))

    machine_cols = [machine_id, machine_line, machine_name]
    for c in (machine_plant, machine_capacity, machine_load, machine_active):
        if c and c not in machine_cols:
            machine_cols.append(c)

    m = machines[machine_cols].copy().rename(
        columns={
            machine_id: "machine_id",
            machine_line: "production_line_id",
            machine_name: "machine_name",
        }
    )

    if machine_plant:
        m = m.rename(columns={machine_plant: "plant_id"})
    else:
        line_to_plant = l.set_index("production_line_id")["plant_id"]
        m["plant_id"] = m["production_line_id"].map(line_to_plant)
        if m["plant_id"].isna().any():
            raise ValueError(
                "Could not derive plant_id for one or more machines "
                "from production_line_id"
            )

    if machine_capacity:
        m = m.rename(columns={machine_capacity: "rated_capacity_units_per_hour"})
    else:
        m["rated_capacity_units_per_hour"] = DEFAULT_MACHINE_CAPACITY_UNITS_PER_HOUR

    if machine_load:
        m = m.rename(columns={machine_load: "baseline_load_pct"})
    else:
        m["baseline_load_pct"] = DEFAULT_MACHINE_LOAD_PCT

    if machine_active:
        m = m.rename(columns={machine_active: "active"})
        m["active"] = _to_bool_series(m["active"])
    else:
        m["active"] = True

    # Vehicle models
    vehicle_id = _find_column(
        vehicle_models,
        ("vehicle_model_id",),
        "vehicle_models",
        "vehicle-model ID",
    )
    vehicle_name = _find_column(
        vehicle_models,
        ("model_name", "vehicle_model_name", "name"),
        "vehicle_models",
        "model name",
    )
    vehicle_weight = _find_optional_column(
        vehicle_models,
        ("generation_weight", "interest_weight", "weight"),
    )
    vehicle_complexity = _find_optional_column(
        vehicle_models,
        ("production_complexity", "complexity"),
    )

    vehicle_cols = [vehicle_id, vehicle_name]
    if vehicle_weight:
        vehicle_cols.append(vehicle_weight)
    if vehicle_complexity and vehicle_complexity not in vehicle_cols:
        vehicle_cols.append(vehicle_complexity)

    v = vehicle_models[vehicle_cols].copy().rename(
        columns={vehicle_id: "vehicle_model_id", vehicle_name: "model_name"}
    )

    if vehicle_weight:
        v = v.rename(columns={vehicle_weight: "generation_weight"})
    else:
        v["generation_weight"] = 1.0 / len(v)

    if vehicle_complexity:
        v = v.rename(columns={vehicle_complexity: "production_complexity"})
    else:
        v["production_complexity"] = 0.50

    # Suppliers
    supplier_required = {"supplier_id", "supplier_name", "criticality", "active"}
    missing_supplier = supplier_required.difference(suppliers.columns)
    if missing_supplier:
        raise ValueError(
            "suppliers DataFrame is missing: "
            + ", ".join(sorted(missing_supplier))
        )

    s = suppliers[
        ["supplier_id", "supplier_name", "criticality", "active"]
    ].copy()
    s["active"] = _to_bool_series(s["active"])

    # Supplier lots
    lot_required = {
        "supplier_lot_id",
        "supplier_id",
        "supplier_name",
        "component_category",
        "criticality",
        "received_at",
        "lot_size_units",
        "accepted_units",
        "lot_quality_score",
        "inspection_defect_rate",
        "inspection_status",
        "usable_for_production",
    }
    missing_lot = lot_required.difference(supplier_lots.columns)
    if missing_lot:
        raise ValueError(
            "supplier_lots DataFrame is missing: "
            + ", ".join(sorted(missing_lot))
        )

    sl = supplier_lots[list(lot_required)].copy()
    sl["received_at"] = pd.to_datetime(sl["received_at"])
    sl["usable_for_production"] = _to_bool_series(sl["usable_for_production"])

    for df, column in (
        (p, "plant_id"),
        (l, "production_line_id"),
        (m, "machine_id"),
        (v, "vehicle_model_id"),
        (s, "supplier_id"),
        (sl, "supplier_lot_id"),
    ):
        if df[column].duplicated().any():
            raise ValueError(f"Duplicate {column} values found")

    return p, l, m, v, s, sl


def _choose_primary_line(plant_lines: pd.DataFrame) -> pd.Series:
    if plant_lines.empty:
        raise ValueError("Plant has no active production lines")

    priority = {"ASSEMBLY": 1, "QUALITY": 2, "PAINT": 3, "BODY": 4}
    work = plant_lines.copy()
    work["_priority"] = (
        work["line_type"]
        .astype(str)
        .str.upper()
        .map(priority)
        .fillna(99)
    )
    return work.sort_values(
        ["_priority", "production_line_id"]
    ).iloc[0]


def _build_plant_capacity_profile(
    plant_id: str,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
) -> dict[str, Any]:
    active_lines = production_lines[
        (production_lines["plant_id"].astype(str) == str(plant_id))
        & production_lines["active"].astype(bool)
    ].copy()

    if active_lines.empty:
        raise ValueError(
            f"Plant {plant_id} has no active production lines"
        )

    active_machines = machines[
        (machines["plant_id"].astype(str) == str(plant_id))
        & machines["active"].astype(bool)
    ].copy()

    if active_machines.empty:
        raise ValueError(
            f"Plant {plant_id} has no active machines"
        )

    line_capacities: dict[str, float] = {}

    for line in active_lines.itertuples(index=False):
        line_machines = active_machines[
            active_machines["production_line_id"].astype(str)
            == str(line.production_line_id)
        ]

        if line_machines.empty:
            raise ValueError(
                f"Production line {line.production_line_id} has no active machines"
            )

        capacities = pd.to_numeric(
            line_machines["rated_capacity_units_per_hour"],
            errors="coerce",
        ).fillna(DEFAULT_MACHINE_CAPACITY_UNITS_PER_HOUR).clip(lower=1.0)

        line_capacities[str(line.production_line_id)] = float(
            capacities.sum()
        )

    bottleneck_capacity = min(line_capacities.values())
    primary_line = _choose_primary_line(active_lines)
    primary_line_id = str(primary_line["production_line_id"])

    primary_line_machines = active_machines[
        active_machines["production_line_id"].astype(str) == primary_line_id
    ].copy()

    primary_caps = pd.to_numeric(
        primary_line_machines["rated_capacity_units_per_hour"],
        errors="coerce",
    ).fillna(DEFAULT_MACHINE_CAPACITY_UNITS_PER_HOUR)

    representative_machine = primary_line_machines.loc[
        primary_caps.idxmin()
    ]

    average_load_pct = float(
        np.mean(
            [
                _normalize_load_pct(value)
                for value in active_machines["baseline_load_pct"].tolist()
            ]
        )
    )

    daily_capacity = int(
        np.clip(
            round(bottleneck_capacity * CAPACITY_SCALE_FACTOR),
            MIN_BATCH_UNITS,
            MAX_BATCH_UNITS,
        )
    )

    return {
        "primary_line_id": primary_line_id,
        "primary_line_name": str(primary_line["production_line_name"]),
        "primary_line_type": str(primary_line["line_type"]),
        "representative_machine_id": str(representative_machine["machine_id"]),
        "representative_machine_name": str(representative_machine["machine_name"]),
        "active_line_count": int(len(active_lines)),
        "active_machine_count": int(len(active_machines)),
        "average_machine_load_pct": average_load_pct,
        "bottleneck_capacity_units_per_hour": bottleneck_capacity,
        "scaled_daily_capacity_units": daily_capacity,
    }


def _select_supplier_lot(
    rng: np.random.Generator,
    supplier_lots: pd.DataFrame,
    lot_remaining_units: dict[str, int],
    batch_start: pd.Timestamp,
    required_units: int,
) -> pd.Series:
    eligible = supplier_lots[
        (supplier_lots["received_at"] <= batch_start)
        & supplier_lots["usable_for_production"].astype(bool)
    ].copy()

    if eligible.empty:
        raise ValueError(
            f"No usable supplier lot exists before {batch_start}"
        )

    eligible["_remaining"] = (
        eligible["supplier_lot_id"]
        .astype(str)
        .map(lot_remaining_units)
        .fillna(0)
        .astype(int)
    )

    full_supply = eligible[
        eligible["_remaining"] >= required_units
    ].copy()

    eligible = (
        full_supply
        if not full_supply.empty
        else eligible[eligible["_remaining"] > 0].copy()
    )

    if eligible.empty:
        raise ValueError("All eligible supplier lots are exhausted")

    lot_age_days = (
        (batch_start - eligible["received_at"]).dt.total_seconds()
        / 86400.0
    )

    recent = eligible[
        lot_age_days <= RECENT_SUPPLIER_LOT_DAYS
    ].copy()

    if not recent.empty:
        eligible = recent

    criticality_weight = (
        eligible["criticality"]
        .astype(str)
        .str.upper()
        .map({"HIGH": 1.40, "MEDIUM": 1.15, "LOW": 1.00})
        .fillna(1.0)
        .to_numpy(dtype=float)
    )

    quality = pd.to_numeric(
        eligible["lot_quality_score"],
        errors="raise",
    ).to_numpy(dtype=float)

    quality_weight = 0.65 + 0.35 * quality
    remaining_weight = np.sqrt(
        np.maximum(
            eligible["_remaining"].to_numpy(dtype=float),
            1.0,
        )
    )

    weights = criticality_weight * quality_weight * remaining_weight
    if float(weights.sum()) <= 0:
        weights = np.ones(len(eligible), dtype=float)

    weights = weights / weights.sum()

    selected_position = int(
        rng.choice(
            np.arange(len(eligible)),
            p=weights,
        )
    )

    return eligible.iloc[selected_position]


def _calculate_defect_probability(
    supplier_quality: float,
    supplier_inspection_defect_rate: float,
    production_complexity: float,
    utilization: float,
    machine_load_pct: float,
) -> float:
    supplier_quality = float(np.clip(supplier_quality, 0.0, 1.0))
    supplier_inspection_defect_rate = float(
        np.clip(supplier_inspection_defect_rate, 0.0, 1.0)
    )
    production_complexity = float(
        np.clip(production_complexity, 0.0, 1.0)
    )
    utilization = float(np.clip(utilization, 0.0, 1.25))
    machine_load = float(np.clip(machine_load_pct / 100.0, 0.0, 1.0))

    probability = (
        0.006
        + 0.060 * (1.0 - supplier_quality)
        + 0.35 * supplier_inspection_defect_rate
        + 0.010 * production_complexity
        + 0.035 * max(utilization - 0.90, 0.0)
        + 0.012 * max(machine_load - 0.85, 0.0)
    )

    return float(np.clip(probability, 0.003, 0.12))


def _derive_batch_status(
    final_yield: float,
    quality_score: float,
) -> str:
    if (
        final_yield >= RELEASE_MIN_FINAL_YIELD
        and quality_score >= RELEASE_MIN_QUALITY_SCORE
    ):
        return "RELEASED"

    if (
        final_yield >= REVIEW_MIN_FINAL_YIELD
        and quality_score >= REVIEW_MIN_QUALITY_SCORE
    ):
        return "QUALITY_REVIEW"

    return "REJECTED"


def generate_production_batches(
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    suppliers: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    if generation is None:
        generation = load_generation_config()

    (
        plants,
        production_lines,
        machines,
        vehicle_models,
        suppliers,
        supplier_lots,
    ) = _prepare_inputs(
        plants=plants,
        production_lines=production_lines,
        machines=machines,
        vehicle_models=vehicle_models,
        suppliers=suppliers,
        supplier_lots=supplier_lots,
    )

    active_plant_ids = set(
        plants.loc[
            plants["active"].astype(bool),
            "plant_id",
        ].astype(str)
    )

    if not active_plant_ids:
        raise ValueError("No active plants available")

    if set(production_lines["plant_id"].astype(str)) - set(
        plants["plant_id"].astype(str)
    ):
        raise ValueError("Production lines reference invalid plant IDs")

    if set(machines["plant_id"].astype(str)) - set(
        plants["plant_id"].astype(str)
    ):
        raise ValueError("Machines reference invalid plant IDs")

    if set(machines["production_line_id"].astype(str)) - set(
        production_lines["production_line_id"].astype(str)
    ):
        raise ValueError(
            "Machines reference invalid production-line IDs"
        )

    if set(supplier_lots["supplier_id"].astype(str)) - set(
        suppliers["supplier_id"].astype(str)
    ):
        raise ValueError("Supplier lots reference invalid supplier IDs")

    generation_start, generation_end, _ = _get_generation_window(
        generation
    )

    try:
        base_seed = int(generation["seed"])
    except KeyError as exc:
        raise KeyError("Missing generation.seed") from exc

    rng = make_rng(
        derive_seed(
            base_seed,
            "auto.production",
        )
    )

    model_weights = pd.to_numeric(
        vehicle_models["generation_weight"],
        errors="coerce",
    ).fillna(0.0).to_numpy(dtype=float)

    if (model_weights < 0).any():
        raise ValueError("Vehicle generation weights cannot be negative")

    if model_weights.sum() <= 0:
        model_weights = np.ones(len(vehicle_models), dtype=float)

    model_weights = model_weights / model_weights.sum()

    plant_profiles = {
        plant_id: _build_plant_capacity_profile(
            plant_id=plant_id,
            production_lines=production_lines,
            machines=machines,
        )
        for plant_id in sorted(active_plant_ids)
    }

    lot_remaining_units = {
        str(row.supplier_lot_id): int(row.accepted_units)
        for row in supplier_lots.itertuples(index=False)
    }

    provenance = generation.get("provenance", {})
    data_origin = str(
        provenance.get("data_origin", "SYNTHETIC")
    )
    generator_version = str(
        generation.get("generator_version", "1.0.0")
    )

    production_days = pd.date_range(
        start=generation_start.normalize(),
        end=generation_end.normalize(),
        freq="D",
        inclusive="left",
    )

    if len(production_days) == 0:
        raise ValueError(
            "No production days in configured generation window"
        )

    active_plants = plants[
        plants["active"].astype(bool)
    ].copy()

    active_plants["plant_id"] = active_plants["plant_id"].astype(str)
    active_plants = (
        active_plants
        .sort_values("plant_id")
        .reset_index(drop=True)
    )

    rows: list[dict[str, Any]] = []
    batch_counter = 1

    for day_index, production_day in enumerate(production_days):
        for plant_position, plant in active_plants.iterrows():
            plant_id = str(plant["plant_id"])
            profile = plant_profiles[plant_id]

            production_start = production_day + timedelta(
                hours=PRODUCTION_DAY_START_HOUR
            )
            if production_start >= generation_end:
                continue

            production_end = min(
                production_start
                + timedelta(
                    hours=float(
                        rng.uniform(
                            MIN_BATCH_DURATION_HOURS,
                            MAX_BATCH_DURATION_HOURS,
                        )
                    )
                ),
                generation_end,
            )

            dominant_shift = ("A", "B", "C")[
                (day_index + plant_position) % 3
            ]

            model_position = int(
                rng.choice(
                    np.arange(len(vehicle_models)),
                    p=model_weights,
                )
            )
            vehicle = vehicle_models.iloc[model_position]
            complexity = _complexity_score(
                vehicle["production_complexity"]
            )
            variant = str(
                rng.choice(
                    VALID_VARIANTS,
                    p=VARIANT_WEIGHTS,
                )
            )

            capacity_units = int(
                profile["scaled_daily_capacity_units"]
            )
            complexity_factor = 1.0 - 0.22 * complexity
            daily_variation = float(rng.uniform(0.88, 1.08))

            planned_units = int(
                np.clip(
                    round(
                        capacity_units
                        * complexity_factor
                        * daily_variation
                    ),
                    MIN_BATCH_UNITS,
                    MAX_BATCH_UNITS,
                )
            )

            lot = _select_supplier_lot(
                rng=rng,
                supplier_lots=supplier_lots,
                lot_remaining_units=lot_remaining_units,
                batch_start=production_start,
                required_units=planned_units,
            )

            supplier_lot_id = str(lot["supplier_lot_id"])
            supplier_quality = float(lot["lot_quality_score"])
            supplier_defect_rate = float(
                lot["inspection_defect_rate"]
            )

            utilization = planned_units / max(capacity_units, 1)
            machine_load_pct = float(
                profile["average_machine_load_pct"]
            )

            load_factor = (
                1.0
                - 0.08
                * abs(
                    machine_load_pct / 100.0 - 0.75
                )
            )
            supplier_factor = 0.94 + 0.06 * supplier_quality

            production_efficiency = float(
                np.clip(
                    load_factor
                    * supplier_factor
                    * float(rng.normal(0.985, 0.018)),
                    0.84,
                    1.02,
                )
            )

            units_produced = max(
                int(round(planned_units * production_efficiency)),
                1,
            )

            defect_probability = _calculate_defect_probability(
                supplier_quality=supplier_quality,
                supplier_inspection_defect_rate=supplier_defect_rate,
                production_complexity=complexity,
                utilization=utilization,
                machine_load_pct=machine_load_pct,
            )

            defect_units = int(
                rng.binomial(
                    units_produced,
                    defect_probability,
                )
            )

            rework_units = (
                int(rng.binomial(defect_units, 0.72))
                if defect_units > 0
                else 0
            )
            rework_success_units = (
                int(rng.binomial(rework_units, 0.86))
                if rework_units > 0
                else 0
            )

            scrap_units = defect_units - rework_success_units
            first_pass_good_units = units_produced - defect_units
            final_good_units = units_produced - scrap_units

            first_pass_yield = (
                first_pass_good_units / units_produced
            )
            final_yield = final_good_units / units_produced
            quality_inspection_rate = float(
                rng.uniform(0.92, 1.00)
            )

            quality_score = float(
                np.clip(
                    0.30 * supplier_quality
                    + 0.45 * first_pass_yield
                    + 0.25 * final_yield,
                    0.0,
                    1.0,
                )
            )

            batch_status = _derive_batch_status(
                final_yield,
                quality_score,
            )

            available_for_allocation_units = (
                final_good_units
                if batch_status == "RELEASED"
                else 0
            )

            available_lot_units = int(
                lot_remaining_units[supplier_lot_id]
            )
            supplier_lot_units_consumed = min(
                units_produced,
                available_lot_units,
            )
            lot_remaining_units[supplier_lot_id] = (
                available_lot_units
                - supplier_lot_units_consumed
            )

            supplier_lot_age_days = (
                production_start
                - pd.Timestamp(lot["received_at"])
            ).total_seconds() / 86400.0

            rows.append(
                {
                    "production_batch_id": make_entity_id(
                        "production_batch",
                        batch_counter,
                        width=6,
                    ),
                    "plant_id": plant_id,
                    "plant_name": str(plant["plant_name"]),
                    "production_line_id": profile["primary_line_id"],
                    "production_line_name": profile["primary_line_name"],
                    "production_line_type": profile["primary_line_type"],
                    "representative_machine_id": profile[
                        "representative_machine_id"
                    ],
                    "representative_machine_name": profile[
                        "representative_machine_name"
                    ],
                    "active_line_count": profile["active_line_count"],
                    "active_machine_count": profile["active_machine_count"],
                    "average_machine_load_pct": round(
                        machine_load_pct,
                        3,
                    ),
                    "bottleneck_capacity_units_per_hour": round(
                        float(
                            profile[
                                "bottleneck_capacity_units_per_hour"
                            ]
                        ),
                        3,
                    ),
                    "vehicle_model_id": str(
                        vehicle["vehicle_model_id"]
                    ),
                    "vehicle_model_name": str(vehicle["model_name"]),
                    "variant": variant,
                    "production_complexity": round(complexity, 4),
                    "primary_supplier_id": str(lot["supplier_id"]),
                    "primary_supplier_name": str(lot["supplier_name"]),
                    "primary_supplier_lot_id": supplier_lot_id,
                    "supplier_component_category": str(
                        lot["component_category"]
                    ),
                    "supplier_criticality": str(lot["criticality"]),
                    "supplier_lot_quality_score": round(
                        supplier_quality,
                        6,
                    ),
                    "supplier_lot_inspection_defect_rate": round(
                        supplier_defect_rate,
                        6,
                    ),
                    "supplier_lot_age_days": round(
                        supplier_lot_age_days,
                        3,
                    ),
                    "supplier_lot_units_consumed":
                        supplier_lot_units_consumed,
                    "supplier_lot_remaining_units_after_batch": int(
                        lot_remaining_units[supplier_lot_id]
                    ),
                    "production_date": production_start.date(),
                    "production_start": production_start,
                    "production_end": production_end,
                    "dominant_shift": dominant_shift,
                    "scaled_daily_capacity_units": capacity_units,
                    "planned_units": planned_units,
                    "production_efficiency": round(
                        production_efficiency,
                        6,
                    ),
                    "units_produced": units_produced,
                    "defect_probability": round(
                        defect_probability,
                        6,
                    ),
                    "defect_units": defect_units,
                    "rework_units": rework_units,
                    "rework_success_units": rework_success_units,
                    "scrap_units": scrap_units,
                    "first_pass_good_units": first_pass_good_units,
                    "final_good_units": final_good_units,
                    "first_pass_yield": round(first_pass_yield, 6),
                    "final_yield": round(final_yield, 6),
                    "quality_inspection_rate": round(
                        quality_inspection_rate,
                        6,
                    ),
                    "quality_score": round(quality_score, 6),
                    "batch_status": batch_status,
                    "available_for_allocation_units":
                        available_for_allocation_units,
                    "data_origin": data_origin,
                    "generator_version": generator_version,
                }
            )

            batch_counter += 1

    production_batches = pd.DataFrame(rows)

    validate_production_batches(
        production_batches=production_batches,
        plants=plants,
        production_lines=production_lines,
        machines=machines,
        vehicle_models=vehicle_models,
        suppliers=suppliers,
        supplier_lots=supplier_lots,
        generation_start=generation_start,
        generation_end=generation_end,
    )

    return production_batches


def validate_production_batches(
    production_batches: pd.DataFrame,
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    suppliers: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> None:
    if production_batches.empty:
        raise ValueError("No production batches generated")

    if production_batches["production_batch_id"].duplicated().any():
        raise ValueError(
            "Duplicate production_batch_id values found"
        )

    fk_checks = (
        (
            "plant_id",
            set(plants["plant_id"].astype(str)),
            "plant IDs",
        ),
        (
            "production_line_id",
            set(production_lines["production_line_id"].astype(str)),
            "production-line IDs",
        ),
        (
            "representative_machine_id",
            set(machines["machine_id"].astype(str)),
            "machine IDs",
        ),
        (
            "vehicle_model_id",
            set(vehicle_models["vehicle_model_id"].astype(str)),
            "vehicle-model IDs",
        ),
        (
            "primary_supplier_id",
            set(suppliers["supplier_id"].astype(str)),
            "supplier IDs",
        ),
        (
            "primary_supplier_lot_id",
            set(supplier_lots["supplier_lot_id"].astype(str)),
            "supplier-lot IDs",
        ),
    )

    for child_column, valid_values, description in fk_checks:
        invalid = (
            set(
                production_batches[
                    child_column
                ].astype(str)
            )
            -
            valid_values
        )
        if invalid:
            raise ValueError(
                f"Production batches reference invalid {description}"
            )

    if (
        set(production_batches["batch_status"])
        -
        VALID_BATCH_STATUSES
    ):
        raise ValueError("Invalid production batch statuses")

    if (
        set(production_batches["dominant_shift"])
        -
        VALID_SHIFTS
    ):
        raise ValueError("Invalid production shift values")

    if (
        set(production_batches["variant"])
        -
        set(VALID_VARIANTS)
    ):
        raise ValueError("Invalid synthetic variants")

    count_columns = (
        "planned_units",
        "units_produced",
        "defect_units",
        "rework_units",
        "rework_success_units",
        "scrap_units",
        "first_pass_good_units",
        "final_good_units",
        "available_for_allocation_units",
        "supplier_lot_units_consumed",
    )

    values = {
        column: pd.to_numeric(
            production_batches[column],
            errors="raise",
        )
        for column in count_columns
    }

    for column, series in values.items():
        if (series < 0).any():
            raise ValueError(
                f"{column} cannot be negative"
            )

    if (values["planned_units"] <= 0).any():
        raise ValueError("planned_units must be > 0")

    if (values["units_produced"] <= 0).any():
        raise ValueError("units_produced must be > 0")

    if (
        values["defect_units"]
        >
        values["units_produced"]
    ).any():
        raise ValueError(
            "defect_units cannot exceed units_produced"
        )

    if (
        values["rework_units"]
        >
        values["defect_units"]
    ).any():
        raise ValueError(
            "rework_units cannot exceed defect_units"
        )

    if (
        values["rework_success_units"]
        >
        values["rework_units"]
    ).any():
        raise ValueError(
            "rework_success_units cannot exceed rework_units"
        )

    if not (
        values["scrap_units"]
        ==
        (
            values["defect_units"]
            -
            values["rework_success_units"]
        )
    ).all():
        raise ValueError(
            "scrap_units consistency check failed"
        )

    if not (
        values["first_pass_good_units"]
        ==
        (
            values["units_produced"]
            -
            values["defect_units"]
        )
    ).all():
        raise ValueError(
            "first_pass_good_units consistency check failed"
        )

    if not (
        values["final_good_units"]
        ==
        (
            values["units_produced"]
            -
            values["scrap_units"]
        )
    ).all():
        raise ValueError(
            "final_good_units consistency check failed"
        )

    for column in (
        "first_pass_yield",
        "final_yield",
        "quality_score",
        "supplier_lot_quality_score",
        "defect_probability",
        "quality_inspection_rate",
    ):
        series = pd.to_numeric(
            production_batches[column],
            errors="raise",
        )
        if (
            (series < 0)
            |
            (series > 1)
        ).any():
            raise ValueError(
                f"{column} must be between 0 and 1"
            )

    released = (
        production_batches["batch_status"]
        ==
        "RELEASED"
    )

    if not (
        production_batches.loc[
            released,
            "available_for_allocation_units",
        ]
        ==
        production_batches.loc[
            released,
            "final_good_units",
        ]
    ).all():
        raise ValueError(
            "Released batches must expose all final-good units"
        )

    if not (
        production_batches.loc[
            ~released,
            "available_for_allocation_units",
        ]
        ==
        0
    ).all():
        raise ValueError(
            "Non-released batches cannot be available for allocation"
        )

    production_start = pd.to_datetime(
        production_batches["production_start"]
    )
    production_end = pd.to_datetime(
        production_batches["production_end"]
    )

    if (production_start < generation_start).any():
        raise ValueError(
            "Production starts before generation window"
        )

    if (production_end > generation_end).any():
        raise ValueError(
            "Production ends after generation window"
        )

    if (production_end <= production_start).any():
        raise ValueError(
            "production_end must be after production_start"
        )

    line_lookup = {
        str(row.production_line_id): row
        for row in production_lines.itertuples(index=False)
    }
    machine_lookup = {
        str(row.machine_id): row
        for row in machines.itertuples(index=False)
    }
    lot_lookup = {
        str(row.supplier_lot_id): row
        for row in supplier_lots.itertuples(index=False)
    }

    for batch in production_batches.itertuples(index=False):
        line = line_lookup[
            str(batch.production_line_id)
        ]
        if str(line.plant_id) != str(batch.plant_id):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "production line belongs to another plant"
            )

        machine = machine_lookup[
            str(batch.representative_machine_id)
        ]
        if str(machine.plant_id) != str(batch.plant_id):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "machine belongs to another plant"
            )

        if (
            str(machine.production_line_id)
            !=
            str(batch.production_line_id)
        ):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "machine belongs to another production line"
            )

        lot = lot_lookup[
            str(batch.primary_supplier_lot_id)
        ]
        if str(lot.supplier_id) != str(batch.primary_supplier_id):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "supplier and supplier-lot mismatch"
            )

        if not bool(lot.usable_for_production):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "uses a supplier lot not approved for production"
            )

        if (
            pd.Timestamp(lot.received_at)
            >
            pd.Timestamp(batch.production_start)
        ):
            raise ValueError(
                f"{batch.production_batch_id}: "
                "supplier lot arrived after production started"
            )

    lot_usage = (
        production_batches
        .groupby("primary_supplier_lot_id")[
            "supplier_lot_units_consumed"
        ]
        .sum()
    )

    accepted_lookup = (
        supplier_lots
        .assign(
            supplier_lot_id=
                supplier_lots["supplier_lot_id"].astype(str)
        )
        .set_index("supplier_lot_id")[
            "accepted_units"
        ]
    )

    for supplier_lot_id, consumed in lot_usage.items():
        if (
            int(consumed)
            >
            int(
                accepted_lookup[
                    str(supplier_lot_id)
                ]
            )
        ):
            raise ValueError(
                f"Supplier lot {supplier_lot_id} was consumed "
                "beyond accepted inventory"
            )


def generate_production_batch_master(
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    machines: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    suppliers: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    return generate_production_batches(
        plants=plants,
        production_lines=production_lines,
        machines=machines,
        vehicle_models=vehicle_models,
        suppliers=suppliers,
        supplier_lots=supplier_lots,
        generation=generation,
    )


if __name__ == "__main__":
    from data.generators.master.geography import generate_geography
    from data.generators.master.vehicle_models import generate_vehicle_models
    from data.generators.master.plants import generate_plant_master
    from data.generators.master.machines import generate_machine_master
    from data.generators.auto.suppliers import generate_supplier_master

    regions_df, cities_df = generate_geography()
    vehicle_models_df = generate_vehicle_models()

    plants_df, production_lines_df = generate_plant_master(
        cities_df
    )

    machines_df = generate_machine_master(
        production_lines_df
    )

    suppliers_df, supplier_lots_df = generate_supplier_master(
        cities=cities_df
    )

    production_batches_df = generate_production_batch_master(
        plants=plants_df,
        production_lines=production_lines_df,
        machines=machines_df,
        vehicle_models=vehicle_models_df,
        suppliers=suppliers_df,
        supplier_lots=supplier_lots_df,
    )

    print("\\n=== PRODUCTION BATCH SAMPLE ===\\n")

    display_columns = [
        "production_batch_id",
        "plant_name",
        "production_line_name",
        "vehicle_model_name",
        "variant",
        "primary_supplier_name",
        "primary_supplier_lot_id",
        "supplier_lot_quality_score",
        "planned_units",
        "units_produced",
        "defect_units",
        "rework_units",
        "scrap_units",
        "final_good_units",
        "quality_score",
        "batch_status",
        "available_for_allocation_units",
    ]

    print(
        production_batches_df[
            display_columns
        ]
        .head(30)
        .to_string(index=False)
    )

    print("\\n=== PRODUCTION BATCH STATUS ===\\n")

    print(
        production_batches_df
        .groupby("batch_status")
        .size()
        .reset_index(name="batch_count")
        .sort_values(
            "batch_count",
            ascending=False,
        )
        .to_string(index=False)
    )

    print("\\n=== PRODUCTION BY VEHICLE MODEL ===\\n")

    model_summary = (
        production_batches_df
        .groupby(
            "vehicle_model_name",
            as_index=False,
        )
        .agg(
            batches=("production_batch_id", "count"),
            units_produced=("units_produced", "sum"),
            final_good_units=("final_good_units", "sum"),
            available_units=(
                "available_for_allocation_units",
                "sum",
            ),
        )
    )

    print(
        model_summary.to_string(index=False)
    )

    print("\\n=== PRODUCTION BY PLANT ===\\n")

    plant_summary = (
        production_batches_df
        .groupby(
            "plant_name",
            as_index=False,
        )
        .agg(
            batches=("production_batch_id", "count"),
            units_produced=("units_produced", "sum"),
            defects=("defect_units", "sum"),
            rework=("rework_units", "sum"),
            scrap=("scrap_units", "sum"),
            allocation_ready_units=(
                "available_for_allocation_units",
                "sum",
            ),
        )
    )

    print(
        plant_summary.to_string(index=False)
    )

    print("\\n=== PRODUCTION QUALITY CHECK ===\\n")

    print(
        "Average first-pass yield:",
        round(
            production_batches_df[
                "first_pass_yield"
            ].mean(),
            4,
        ),
    )

    print(
        "Average final yield:",
        round(
            production_batches_df[
                "final_yield"
            ].mean(),
            4,
        ),
    )

    print(
        "Average quality score:",
        round(
            production_batches_df[
                "quality_score"
            ].mean(),
            4,
        ),
    )

    print(
        "Total produced units:",
        int(
            production_batches_df[
                "units_produced"
            ].sum()
        ),
    )

    print(
        "Total allocation-ready units:",
        int(
            production_batches_df[
                "available_for_allocation_units"
            ].sum()
        ),
    )

    print(
        "\\nGenerated "
        f"{len(production_batches_df)} "
        "synthetic production batches successfully."
    )