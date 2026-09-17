"""Deterministic minute-level connected-vehicle telemetry.

Runtime output contains observable vehicle signals and existing synthetic-world
lineage only. Hidden scenario-family assignments are generator state and are
never written to the returned DataFrame.
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import load_generation_config
from data.generators.common.seed import derive_seed, make_rng


SCENARIO_FAMILIES: tuple[str, ...] = (
    "BATTERY_DEGRADATION",
    "TRANSMISSION_DEGRADATION",
    "SUSPENSION_STEERING_DEGRADATION",
)

FORBIDDEN_RUNTIME_COLUMNS: set[str] = {
    "scenario_family",
    "scenario_name",
    "is_affected",
    "root_cause",
    "true_causal_parent",
    "true_causal_child",
    "causal_coefficient",
}

REQUIRED_COLUMNS: tuple[str, ...] = (
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


def _generation_window(
    generation: Mapping[str, Any],
) -> tuple[pd.Timestamp, pd.Timestamp, str, int, int]:
    time_config = generation.get("time", {})
    iot_config = generation.get("iot", {})
    timezone = str(time_config.get("timezone", "Asia/Kolkata"))

    start = pd.Timestamp(time_config["start_date"])
    end = pd.Timestamp(time_config["end_date"])
    start = start.tz_localize(timezone) if start.tzinfo is None else start.tz_convert(timezone)
    end = end.tz_localize(timezone) if end.tzinfo is None else end.tz_convert(timezone)

    frequency = str(iot_config.get("frequency", "1min"))
    if pd.Timedelta(frequency) != pd.Timedelta(minutes=1):
        raise ValueError("iot.frequency must be exactly 1min")

    history_days = int(iot_config.get("history_days", 7))
    vehicle_count = int(iot_config.get("vehicle_count", 24))
    if history_days <= 0 or vehicle_count <= 0:
        raise ValueError("iot history_days and vehicle_count must be positive")

    return start, end, frequency, vehicle_count, history_days


def derive_vehicle_scenario_family(
    base_seed: int,
    vehicle_id: str,
) -> str:
    """Return deterministic hidden generator state for validation/reporting."""
    position = derive_seed(
        base_seed,
        f"causal.vehicle_telematics.scenario.{vehicle_id}",
    ) % len(SCENARIO_FAMILIES)
    return SCENARIO_FAMILIES[position]


def _normalize_delivery_time(series: pd.Series, timezone: str) -> pd.Series:
    values = pd.to_datetime(series, errors="raise")
    if values.dt.tz is None:
        return values.dt.tz_localize(timezone)
    return values.dt.tz_convert(timezone)


def _validate_master_ids(
    selected: pd.DataFrame,
    production_batches: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
) -> None:
    relationships = (
        ("production_batch_id", production_batches, "production_batch_id"),
        ("primary_supplier_lot_id", supplier_lots, "supplier_lot_id"),
        ("plant_id", plants, "plant_id"),
        ("production_line_id", production_lines, "production_line_id"),
    )
    for child_column, parent, parent_column in relationships:
        invalid = set(selected[child_column].astype(str)) - set(parent[parent_column].astype(str))
        if invalid:
            raise ValueError(f"Invalid {child_column} references: {sorted(invalid)[:5]}")


def _validate_production_lineage(
    selected: pd.DataFrame,
    production_batches: pd.DataFrame,
    timezone: str,
) -> None:
    """Validate the canonical production lineage carried by each vehicle."""
    required = {
        "production_batch_id",
        "production_end",
        "vehicle_model_id",
        "primary_supplier_lot_id",
        "plant_id",
        "production_line_id",
    }
    missing = required - set(production_batches.columns)
    if missing:
        raise ValueError(
            "production_batches missing lineage columns: "
            + ", ".join(sorted(missing))
        )

    batch_rows = production_batches[
        [
            "production_batch_id",
            "production_end",
            "vehicle_model_id",
            "primary_supplier_lot_id",
            "plant_id",
            "production_line_id",
        ]
    ].copy()
    batch_rows["production_batch_id"] = batch_rows["production_batch_id"].astype(str)
    batch_rows = batch_rows.drop_duplicates("production_batch_id").set_index(
        "production_batch_id"
    )

    selected_batch_ids = selected["production_batch_id"].astype(str)
    batch_lookup = batch_rows.reindex(selected_batch_ids).reset_index(drop=True)
    selected_work = selected.reset_index(drop=True)
    if batch_lookup.isna().any().any():
        raise ValueError("Selected vehicle has an unresolved production-batch lineage")

    for column in (
        "vehicle_model_id",
        "primary_supplier_lot_id",
        "plant_id",
        "production_line_id",
    ):
        mismatch = (
            selected_work[column].astype(str).reset_index(drop=True)
            != batch_lookup[column].astype(str).reset_index(drop=True)
        )
        if mismatch.any():
            raise ValueError(
                f"Selected vehicle lineage disagrees with production batch: {column}"
            )

    production_end = _normalize_delivery_time(batch_lookup["production_end"], timezone)
    delivery_time = selected_work["delivery_timestamp"].reset_index(drop=True)
    if (production_end >= delivery_time).any():
        raise ValueError("Every selected vehicle must be delivered after production_end")


def generate_vehicle_telematics_timeseries(
    deliveries: pd.DataFrame,
    service_events: pd.DataFrame,
    warranty_claims: pd.DataFrame,
    production_batches: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    manufacturing_timeseries: pd.DataFrame | None = None,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Generate one observable telemetry row per vehicle and minute."""
    if generation is None:
        generation = load_generation_config()

    required_delivery_columns = {
        "vehicle_id",
        "vehicle_model_id",
        "vehicle_model_name",
        "variant",
        "production_batch_id",
        "primary_supplier_lot_id",
        "supplier_lot_quality_score",
        "production_quality_score",
        "plant_id",
        "production_line_id",
        "actual_delivery_date",
        "delivery_status",
    }
    missing = required_delivery_columns - set(deliveries.columns)
    if missing:
        raise ValueError("deliveries missing telematics lineage columns: " + ", ".join(sorted(missing)))

    start, default_end, frequency, vehicle_count, history_days = _generation_window(generation)
    iot_config = generation.get("iot", {})
    if "end_date" in iot_config:
        end = pd.Timestamp(iot_config["end_date"])
        timezone = str(generation.get("time", {}).get("timezone", "Asia/Kolkata"))
        end = end.tz_localize(timezone) if end.tzinfo is None else end.tz_convert(timezone)
    else:
        end = default_end

    timezone = str(generation.get("time", {}).get("timezone", "Asia/Kolkata"))
    base_seed = int(generation["seed"])

    if manufacturing_timeseries is None:
        raise ValueError(
            "manufacturing_timeseries is required to select an aligned IoT cohort"
        )
    if "production_batch_id" not in manufacturing_timeseries.columns:
        raise ValueError("manufacturing_timeseries is missing production_batch_id")

    mfg_batches = set(manufacturing_timeseries["production_batch_id"].astype(str).unique())
    if not mfg_batches:
        raise ValueError("manufacturing_timeseries contains no production batches")

    minute_count = history_days * 24 * 60
    eligible = deliveries.copy()
    eligible["production_batch_id"] = eligible["production_batch_id"].astype(str)
    eligible["delivery_timestamp"] = _normalize_delivery_time(
        eligible["actual_delivery_date"],
        timezone,
    )
    eligible = eligible[
        (eligible["delivery_status"].astype(str).str.upper() == "DELIVERED")
        & (eligible["delivery_timestamp"] >= start)
        & eligible["production_batch_id"].isin(mfg_batches)
    ].drop_duplicates("vehicle_id")

    eligible["telemetry_start_timestamp"] = eligible["delivery_timestamp"].dt.ceil(frequency)
    same_minute = eligible["telemetry_start_timestamp"] <= eligible["delivery_timestamp"]
    eligible.loc[same_minute, "telemetry_start_timestamp"] += pd.Timedelta(minutes=1)
    eligible = eligible[
        eligible["telemetry_start_timestamp"]
        + pd.Timedelta(minutes=minute_count - 1)
        < end
    ].sort_values(["telemetry_start_timestamp", "vehicle_id"])

    if len(eligible) < vehicle_count:
        raise ValueError(
            f"Only {len(eligible)} manufacturing-linked delivered vehicles fit fully inside "
            "the telemetry window; "
            f"iot.vehicle_count requests {vehicle_count}"
        )

    selected = eligible.head(vehicle_count).reset_index(drop=True)
    _validate_master_ids(
        selected,
        production_batches,
        supplier_lots,
        plants,
        production_lines,
    )
    _validate_production_lineage(selected, production_batches, timezone)

    elapsed = np.arange(minute_count, dtype=float)
    day_phase = 2.0 * math.pi * (elapsed % 1440.0) / 1440.0
    degradation_curve = np.linspace(0.0, 1.0, minute_count)

    frames: list[pd.DataFrame] = []
    for vehicle in selected.itertuples(index=False):
        vehicle_id = str(vehicle.vehicle_id)
        rng = make_rng(derive_seed(base_seed, f"causal.vehicle_telematics.{vehicle_id}"))
        scenario_family = derive_vehicle_scenario_family(base_seed, vehicle_id)
        vehicle_start = pd.Timestamp(vehicle.telemetry_start_timestamp)
        timestamps = pd.date_range(
            start=vehicle_start,
            periods=minute_count,
            freq=frequency,
        )

        supplier_quality = float(vehicle.supplier_lot_quality_score)
        production_quality = float(vehicle.production_quality_score)
        lineage_risk = float(np.clip(1.0 - 0.5 * (supplier_quality + production_quality), 0.0, 0.25))
        scenario_strength = 0.65 + 2.0 * lineage_risk
        phase = float(rng.uniform(0.0, 2.0 * math.pi))

        speed = np.zeros(minute_count, dtype=float)
        ambient = np.zeros(minute_count, dtype=float)
        roughness = np.zeros(minute_count, dtype=float)
        speed[0] = 0.0
        ambient[0] = 28.0 + float(rng.normal(0.0, 0.4))
        roughness[0] = 2.1 + float(rng.normal(0.0, 0.1))

        for index in range(1, minute_count):
            commute = max(0.0, math.sin(4.0 * math.pi * index / 1440.0 + phase))
            stopped = rng.random() < 0.015
            target_speed = 0.0 if stopped else 58.0 * commute
            speed[index] = np.clip(
                0.86 * speed[index - 1] + 0.14 * target_speed + rng.normal(0.0, 1.8),
                0.0,
                115.0,
            )
            ambient_target = 29.0 + 5.0 * math.sin(day_phase[index] - math.pi / 2.0)
            ambient[index] = np.clip(
                0.97 * ambient[index - 1] + 0.03 * ambient_target + rng.normal(0.0, 0.08),
                14.0,
                46.0,
            )
            roughness[index] = np.clip(
                0.94 * roughness[index - 1] + 0.06 * (1.8 + speed[index] / 65.0) + rng.normal(0.0, 0.06),
                0.4,
                7.5,
            )

        driving = speed > 3.0
        current = np.maximum(0.0, 8.0 + 0.75 * speed + rng.normal(0.0, 2.2, minute_count))
        current = np.where(driving, current, 1.5 + rng.normal(0.0, 0.15, minute_count))

        battery_effect = degradation_curve if scenario_family == "BATTERY_DEGRADATION" else 0.12 * degradation_curve
        battery_resistance = np.clip(
            0.021 + 0.035 * lineage_risk + 0.011 * scenario_strength * battery_effect
            + rng.normal(0.0, 0.00012, minute_count),
            0.015,
            0.060,
        )
        battery_temperature = np.clip(
            ambient + 0.055 * current + 160.0 * battery_resistance
            + 5.0 * scenario_strength * battery_effect,
            15.0,
            70.0,
        )
        battery_soc = np.clip(
            88.0 - 48.0 * ((elapsed + (derive_seed(base_seed, vehicle_id) % 500)) % 1440.0) / 1440.0
            - 0.025 * speed,
            18.0,
            96.0,
        )
        battery_voltage = np.clip(402.0 - current * battery_resistance - 0.045 * (battery_temperature - 30.0), 350.0, 410.0)

        transmission_effect = degradation_curve if scenario_family == "TRANSMISSION_DEGRADATION" else 0.10 * degradation_curve
        transmission_slip = np.clip(
            22.0 + 0.42 * speed + 48.0 * scenario_strength * transmission_effect
            + rng.normal(0.0, 1.0, minute_count),
            5.0,
            145.0,
        )
        converter_slip = np.clip(45.0 + 1.8 * speed + 2.1 * transmission_slip, 30.0, 520.0)
        transmission_temperature = np.clip(
            ambient + 20.0 + 0.31 * speed + 0.10 * transmission_slip,
            35.0,
            125.0,
        )

        impact = np.maximum(0.0, roughness * speed / 190.0 + rng.normal(0.0, 0.025, minute_count))
        # Deterministic sparse pothole impacts without exposing their hidden cause.
        impact_mask = rng.random(minute_count) < 0.0015
        impact[impact_mask] += rng.uniform(0.8, 2.2, impact_mask.sum())

        suspension_effect = degradation_curve if scenario_family == "SUSPENSION_STEERING_DEGRADATION" else 0.10 * degradation_curve
        steering_angle = np.clip(11.0 * np.sin(elapsed / 18.0 + phase) + rng.normal(0.0, 0.7, minute_count), -42.0, 42.0)
        steering_torque = np.clip(
            0.055 * steering_angle + 0.24 * roughness + 2.2 * scenario_strength * suspension_effect,
            -8.0,
            12.0,
        )
        vibration = np.clip(
            0.7 + 0.018 * speed + 0.24 * roughness + 0.012 * transmission_slip
            + 1.8 * scenario_strength * suspension_effect,
            0.2,
            9.0,
        )
        vertical_acceleration = np.clip(1.0 + 0.05 * roughness + 0.25 * impact + rng.normal(0.0, 0.015, minute_count), 0.7, 2.5)
        lateral_acceleration = np.clip(0.0025 * speed * np.abs(steering_angle) + rng.normal(0.0, 0.015, minute_count), 0.0, 1.2)

        dtc_count = (
            (battery_temperature > 45.0).astype(int)
            + (battery_resistance > 0.032).astype(int)
            + (transmission_slip > 78.0).astype(int)
            + (vibration > 4.3).astype(int)
        )
        warning_flag = dtc_count > 0
        odometer_start = 120.0 + float(derive_seed(base_seed, f"odometer.{vehicle_id}") % 3500)
        odometer = odometer_start + np.cumsum(speed / 60.0)

        frame = pd.DataFrame({
            "timestamp": timestamps,
            "vehicle_id": vehicle_id,
            "vehicle_model_id": str(vehicle.vehicle_model_id),
            "vehicle_model_name": str(vehicle.vehicle_model_name),
            "variant": str(vehicle.variant),
            "production_batch_id": str(vehicle.production_batch_id),
            "supplier_lot_id": str(vehicle.primary_supplier_lot_id),
            "plant_id": str(vehicle.plant_id),
            "production_line_id": str(vehicle.production_line_id),
            "odometer_km": np.round(odometer, 3),
            "vehicle_speed_kph": np.round(speed, 3),
            "ambient_temperature_c": np.round(ambient, 3),
            "battery_temperature_c": np.round(battery_temperature, 3),
            "battery_soc_pct": np.round(battery_soc, 3),
            "battery_voltage_v": np.round(battery_voltage, 3),
            "battery_current_a": np.round(current, 3),
            "battery_internal_resistance_ohm": np.round(battery_resistance, 6),
            "transmission_temperature_c": np.round(transmission_temperature, 3),
            "transmission_slip_ms": np.round(transmission_slip, 3),
            "torque_converter_slip_rpm": np.round(converter_slip, 3),
            "steering_torque_nm": np.round(steering_torque, 3),
            "steering_angle_deg": np.round(steering_angle, 3),
            "vehicle_vibration_mm_s": np.round(vibration, 3),
            "vertical_acceleration_g": np.round(vertical_acceleration, 4),
            "lateral_acceleration_g": np.round(lateral_acceleration, 4),
            "road_roughness_index": np.round(roughness, 3),
            "impact_g_force": np.round(impact, 4),
            "dtc_count": dtc_count.astype(int),
            "warning_flag": warning_flag.astype(bool),
            "data_origin": str(generation.get("provenance", {}).get("data_origin", "SYNTHETIC")),
            "generator_version": str(generation.get("generator_version", "1.0.0")),
        })
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True).sort_values(
        ["vehicle_id", "timestamp"]
    ).reset_index(drop=True)

    validate_vehicle_telematics_timeseries(
        result,
        selected,
        service_events,
        warranty_claims,
        production_batches,
        supplier_lots,
        plants,
        production_lines,
        start,
        end,
        minute_count,
    )
    return result


def validate_vehicle_telematics_timeseries(
    telemetry: pd.DataFrame,
    selected_deliveries: pd.DataFrame,
    service_events: pd.DataFrame,
    warranty_claims: pd.DataFrame,
    production_batches: pd.DataFrame,
    supplier_lots: pd.DataFrame,
    plants: pd.DataFrame,
    production_lines: pd.DataFrame,
    generation_start: pd.Timestamp,
    generation_end: pd.Timestamp,
    expected_minutes: int,
) -> None:
    missing = set(REQUIRED_COLUMNS) - set(telemetry.columns)
    if missing:
        raise ValueError("Telematics missing columns: " + ", ".join(sorted(missing)))
    leaked = FORBIDDEN_RUNTIME_COLUMNS & set(telemetry.columns)
    if leaked:
        raise ValueError("Telematics leaked hidden generator truth: " + ", ".join(sorted(leaked)))
    if telemetry.empty:
        raise ValueError("Telematics cannot be empty")
    if telemetry.duplicated(["vehicle_id", "timestamp"]).any():
        raise ValueError("Duplicate vehicle_id/timestamp telemetry rows")

    required_ids = (
        "vehicle_id",
        "vehicle_model_id",
        "production_batch_id",
        "supplier_lot_id",
        "plant_id",
        "production_line_id",
    )
    if telemetry[list(required_ids)].isna().any().any():
        raise ValueError("Telematics contains null required lineage IDs")

    expected_rows = len(selected_deliveries) * expected_minutes
    if len(telemetry) != expected_rows:
        raise ValueError(f"Telematics row mismatch: expected {expected_rows}, found {len(telemetry)}")

    timestamps = pd.to_datetime(telemetry["timestamp"])
    cadence = telemetry.groupby("vehicle_id")["timestamp"].apply(
        lambda values: pd.to_datetime(values).sort_values().diff().dropna().unique()
    )
    if any(len(values) != 1 or values[0] != pd.Timedelta(minutes=1) for values in cadence):
        raise ValueError("Telematics cadence is not exactly one minute per vehicle")
    if timestamps.min() < generation_start or timestamps.max() >= generation_end:
        raise ValueError("Telematics timestamps are outside the configured window")

    delivery_lookup = selected_deliveries.set_index("vehicle_id")["delivery_timestamp"]
    starts = telemetry.groupby("vehicle_id")["timestamp"].min()
    if any(pd.Timestamp(starts[vehicle_id]) < pd.Timestamp(delivery_lookup[vehicle_id]) for vehicle_id in starts.index):
        raise ValueError("Telemetry begins before vehicle delivery")

    telemetry_end = telemetry.groupby("vehicle_id")["timestamp"].max()
    service_work = service_events[
        service_events["vehicle_id"].astype(str).isin(telemetry_end.index.astype(str))
    ].copy()
    if not service_work.empty:
        service_work["service_started_at"] = _normalize_delivery_time(
            service_work["service_started_at"],
            str(generation_start.tz),
        )
        earliest_service = service_work.groupby("vehicle_id")["service_started_at"].min()
        if any(
            pd.Timestamp(earliest_service[vehicle_id]) <= pd.Timestamp(starts[vehicle_id])
            for vehicle_id in earliest_service.index
        ):
            raise ValueError("Telemetry does not precede the first service event")

    claim_work = warranty_claims[
        warranty_claims["vehicle_id"].astype(str).isin(telemetry_end.index.astype(str))
    ].copy()
    if not claim_work.empty:
        claim_work["claim_submitted_at"] = _normalize_delivery_time(
            claim_work["claim_submitted_at"],
            str(generation_start.tz),
        )
        earliest_claim = claim_work.groupby("vehicle_id")["claim_submitted_at"].min()
        if any(
            pd.Timestamp(earliest_claim[vehicle_id]) <= pd.Timestamp(starts[vehicle_id])
            for vehicle_id in earliest_claim.index
        ):
            raise ValueError("Warranty claim does not follow telemetry")

    _validate_master_ids(
        selected_deliveries,
        production_batches,
        supplier_lots,
        plants,
        production_lines,
    )
    if not telemetry["warning_flag"].isin([True, False]).all():
        raise ValueError("warning_flag must be boolean")


ACCIDENT_INJECTION_DECAY: tuple[tuple[int, float], ...] = (
    (0, 1.0),
    (1, 0.7),
    (2, 0.4),
    (3, 0.15),
)


def inject_accident_evidence(
    telematics: pd.DataFrame,
    accident_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Purely additive post-processing step - does not touch
    generate_vehicle_telematics_timeseries or change which
    vehicles/timestamps exist in `telematics`. It only overwrites the
    values of a short (impact minute + 3 following minutes, decaying)
    window of already-generated rows for each given accident event, so
    that specific vehicle's telemetry shows a genuine collision-
    consistent signature (impact-g spike, a sharp speed drop, elevated
    vertical/lateral acceleration) at the moment the accident-caused
    service event says it happened.

    `accident_events` must have vehicle_id, service_started_at, and
    accident_impact_g_force columns (a filtered slice of service_events
    where is_accident_caused is True) - see
    data/generators/auto/service.py's generate_telematics_linked_accident_events,
    which deliberately samples accident timing to fall inside a
    telematics-covered vehicle's existing window, so there is always a
    real row here to overwrite. Any accident event whose vehicle/minute
    is not present in `telematics` is silently skipped (e.g. an ordinary
    generate_accident_service_events accident for a vehicle outside the
    small telematics cohort) - this function never adds or removes rows.
    """
    result = telematics.copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"])

    for accident in accident_events.itertuples(index=False):
        vehicle_id = str(accident.vehicle_id)
        accident_at = pd.Timestamp(accident.service_started_at).floor("min")
        impact_peak = float(accident.accident_impact_g_force)

        for offset_minutes, decay in ACCIDENT_INJECTION_DECAY:
            minute = accident_at + timedelta(minutes=offset_minutes)
            mask = (result["vehicle_id"] == vehicle_id) & (result["timestamp"] == minute)
            if not mask.any():
                continue
            idx = result.index[mask]
            result.loc[idx, "impact_g_force"] = round(impact_peak * decay, 4)
            current_speed = result.loc[idx, "vehicle_speed_kph"].astype(float)
            result.loc[idx, "vehicle_speed_kph"] = (current_speed * (1.0 - 0.85 * decay)).round(3)
            result.loc[idx, "vertical_acceleration_g"] = np.round(
                np.clip(1.0 + 0.6 * impact_peak * decay, 0.7, 2.5), 4
            )
            result.loc[idx, "lateral_acceleration_g"] = np.round(
                np.clip(0.15 * impact_peak * decay, 0.0, 1.2), 4
            )
            result.loc[idx, "dtc_count"] = result.loc[idx, "dtc_count"].astype(int).clip(lower=1)
            result.loc[idx, "warning_flag"] = True

    return result
