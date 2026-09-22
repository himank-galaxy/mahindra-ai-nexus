"""
Live, minute-by-minute manufacturing sensor row generator.

Schema-compatible with:
    data/generators/causal/manufacturing_timeseries.py

This module produces exactly ONE row per selected machine per call
to generate_tick(), instead of a whole historical batch at once.

Unlike a batch re-run, each machine's autoregressive state
(temperature, load, vibration, ...) is kept in memory across calls
so consecutive minutes move smoothly instead of resetting to the
baseline every tick.

Database / output schema (columns, dtypes, ranges, clipping,
formulas) intentionally mirrors the original generator so downstream
consumers see an identical row shape. No file in data/ is imported
for its DataFrame-producing side effects beyond read-only config
and master-data helpers.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from data.generators.common.helpers import load_distribution_config
from data.generators.common.seed import derive_seed, make_rng

from master_data import lookup_batch_context


STEP_HOURS = 1.0 / 60.0


def _clip(value: float, minimum: float, maximum: float) -> float:
    return float(np.clip(value, minimum, maximum))


def _normal_config(
    config: dict,
    default_mean: float,
    default_std: float,
    default_min: float,
    default_max: float,
) -> tuple[float, float, float, float]:
    return (
        float(config.get("mean", default_mean)),
        float(config.get("std", default_std)),
        float(config.get("min", default_min)),
        float(config.get("max", default_max)),
    )


def _is_paint_line(line_type: str) -> bool:
    return "PAINT" in str(line_type).strip().upper()


class MachineState:
    """
    Per-machine persistent state carried between minute ticks.
    """

    __slots__ = (
        "rng",
        "baseline_load",
        "machine_temperature_baseline",
        "vibration_baseline",
        "power_baseline",
        "line_speed_baseline",
        "maintenance_interval",
        "hours_since_maintenance",
        "previous_machine_temperature",
        "previous_ambient_temperature",
        "previous_machine_load",
        "previous_vibration",
        "previous_ambient_humidity",
        "previous_defect_rate",
        "previous_rework_rate",
        "lagged_machine_load",
        "lagged_machine_temperature",
        "lagged_ambient_humidity",
    )


class LiveManufacturingGenerator:
    """
    Holds sensor-distribution configuration and per-machine state,
    and produces one DataFrame of new rows per tick.
    """

    def __init__(
        self,
        machines: pd.DataFrame,
        plants: pd.DataFrame,
        production_lines: pd.DataFrame,
        batch_context: dict,
        generation: dict,
        distributions: dict | None = None,
    ) -> None:

        if distributions is None:
            distributions = load_distribution_config()

        self.machines = machines.set_index(
            "machine_id", drop=False
        )
        self.plants = plants.set_index("plant_id", drop=False)
        self.production_lines = production_lines.set_index(
            "production_line_id", drop=False
        )
        self.batch_context = batch_context

        self.base_seed = int(generation["seed"])

        provenance = generation.get("provenance", {})
        self.data_origin = str(
            provenance.get("data_origin", "SYNTHETIC")
        )
        self.generator_version = str(
            generation.get("generator_version", "1.0.0")
        )

        sensor_config = distributions["manufacturing"]["sensors"]

        (
            self.ambient_temp_mean,
            self.ambient_temp_std,
            self.ambient_temp_min,
            self.ambient_temp_max,
        ) = _normal_config(
            sensor_config.get("ambient_temperature", {}),
            30.0, 4.0, 15.0, 45.0,
        )

        (
            self.ambient_humidity_mean,
            self.ambient_humidity_std,
            self.ambient_humidity_min,
            self.ambient_humidity_max,
        ) = _normal_config(
            sensor_config.get("humidity", sensor_config.get("ambient_humidity", {})),
            60.0, 12.0, 25.0, 95.0,
        )

        (
            self.machine_temp_mean,
            self.machine_temp_std,
            self.machine_temp_min,
            self.machine_temp_max,
        ) = _normal_config(
            sensor_config.get("machine_temperature", {}),
            64.0, 5.0, 45.0, 90.0,
        )

        (
            self.vibration_mean,
            self.vibration_std,
            self.vibration_min,
            self.vibration_max,
        ) = _normal_config(
            sensor_config.get("vibration", {}),
            2.3, 0.45, 0.5, 8.0,
        )

        (
            self.power_mean,
            self.power_std,
            self.power_min,
            self.power_max,
        ) = _normal_config(
            sensor_config.get("power", {}),
            120.0, 15.0, 70.0, 200.0,
        )

        (
            self.line_speed_mean,
            self.line_speed_std,
            self.line_speed_min,
            self.line_speed_max,
        ) = _normal_config(
            sensor_config.get("line_speed", {}),
            42.0, 4.0, 25.0, 60.0,
        )

        (
            self.cycle_time_mean,
            self.cycle_time_std,
            self.cycle_time_min,
            self.cycle_time_max,
        ) = _normal_config(
            sensor_config.get("cycle_time", {}),
            85.0, 10.0, 50.0, 140.0,
        )

        (
            self.paint_temp_mean,
            self.paint_temp_std,
            self.paint_temp_min,
            self.paint_temp_max,
        ) = _normal_config(
            sensor_config.get("paint_temperature", {}),
            26.0, 2.0, 18.0, 35.0,
        )

        (
            self.paint_humidity_mean,
            self.paint_humidity_std,
            self.paint_humidity_min,
            self.paint_humidity_max,
        ) = _normal_config(
            sensor_config.get("paint_humidity", {}),
            58.0, 8.0, 30.0, 90.0,
        )

        (
            self.torque_mean,
            self.torque_std,
            self.torque_min,
            self.torque_max,
        ) = _normal_config(
            sensor_config.get("torque_deviation", {}),
            0.0, 0.8, -5.0, 5.0,
        )

        self.supplier_quality_fallback = 0.90

        self._states: dict[str, MachineState] = {}

    def _get_or_init_state(self, machine_id: str) -> MachineState:

        state = self._states.get(machine_id)

        if state is not None:
            return state

        machine = self.machines.loc[machine_id]

        rng = make_rng(
            derive_seed(
                self.base_seed,
                f"live.manufacturing_timeseries.{machine_id}",
            )
        )

        state = MachineState()
        state.rng = rng

        load = float(machine.baseline_load_pct)
        if load > 1.0:
            load /= 100.0
        state.baseline_load = _clip(load, 0.20, 1.00)

        state.machine_temperature_baseline = (
            self.machine_temp_mean + float(rng.normal(0.0, 1.5))
        )
        state.vibration_baseline = (
            self.vibration_mean + float(rng.normal(0.0, 0.15))
        )

        rated_capacity = float(machine.rated_capacity_units_per_hour)
        capacity_factor = float(
            np.clip(rated_capacity / 50.0, 0.60, 1.40)
        )

        state.power_baseline = self.power_mean * (
            0.85 + 0.20 * capacity_factor
        )
        state.line_speed_baseline = self.line_speed_mean * (
            0.90 + 0.10 * capacity_factor
        )

        state.maintenance_interval = max(
            7 * 24,
            int(14 * 24 + rng.integers(-48, 49)),
        )
        state.hours_since_maintenance = float(
            rng.integers(0, state.maintenance_interval // 2 + 1)
        )

        state.previous_machine_temperature = (
            state.machine_temperature_baseline
        )
        state.previous_ambient_temperature = self.ambient_temp_mean
        state.previous_machine_load = state.baseline_load
        state.previous_vibration = state.vibration_baseline
        state.previous_ambient_humidity = self.ambient_humidity_mean
        state.previous_defect_rate = 0.012
        state.previous_rework_rate = 0.006

        state.lagged_machine_load = state.previous_machine_load
        state.lagged_machine_temperature = (
            state.previous_machine_temperature
        )
        state.lagged_ambient_humidity = (
            state.previous_ambient_humidity
        )

        self._states[machine_id] = state

        return state

    def generate_row(
        self, machine_id: str, timestamp: pd.Timestamp
    ) -> dict[str, Any]:
        """
        Generate exactly one new sensor observation for one machine
        at one timestamp, continuing on from that machine's
        previous state.
        """

        state = self._get_or_init_state(machine_id)
        rng = state.rng

        machine = self.machines.loc[machine_id]
        line = self.production_lines.loc[machine.production_line_id]
        plant = self.plants.loc[machine.plant_id]

        hour = float(timestamp.hour) + float(timestamp.minute) / 60.0
        day_of_week = int(timestamp.dayofweek)
        calendar_day = timestamp.date()

        batch = lookup_batch_context(
            self.batch_context, str(machine.plant_id), calendar_day
        )

        if batch is None:
            production_batch_id = None
            vehicle_model_id = None
            vehicle_model_name = None
            supplier_lot_id = None
            supplier_quality = self.supplier_quality_fallback
            batch_quality_score = 0.96
            batch_status = None
        else:
            production_batch_id = batch["production_batch_id"]
            vehicle_model_id = batch["vehicle_model_id"]
            vehicle_model_name = batch["vehicle_model_name"]
            supplier_lot_id = batch["supplier_lot_id"]
            supplier_quality = float(
                batch["supplier_lot_quality_score"]
            )
            batch_quality_score = float(batch["batch_quality_score"])
            batch_status = batch["batch_status"]

        supplier_quality = _clip(supplier_quality, 0.50, 1.00)

        daily_wave = math.sin(
            2.0 * math.pi * (hour - 6) / 24.0
        )
        second_daily_wave = math.sin(
            2.0 * math.pi * (hour - 14) / 24.0
        )
        weekend_factor = -0.05 if day_of_week >= 5 else 0.0

        ambient_temperature_target = (
            self.ambient_temp_mean + 3.0 * daily_wave
        )
        ambient_temperature = (
            (0.55 ** STEP_HOURS) * state.previous_ambient_temperature
            + (1.0 - 0.55 ** STEP_HOURS) * ambient_temperature_target
            + float(
                rng.normal(
                    0.0,
                    self.ambient_temp_std * 0.35 * math.sqrt(STEP_HOURS),
                )
            )
        )
        ambient_temperature = _clip(
            ambient_temperature, self.ambient_temp_min, self.ambient_temp_max
        )

        humidity_target = (
            self.ambient_humidity_mean
            - 6.0 * daily_wave
            + float(
                rng.normal(
                    0.0,
                    self.ambient_humidity_std * 0.30 * math.sqrt(STEP_HOURS),
                )
            )
        )
        ambient_humidity = (
            (0.55 ** STEP_HOURS) * state.previous_ambient_humidity
            + (1.0 - 0.55 ** STEP_HOURS) * humidity_target
        )
        ambient_humidity = _clip(
            ambient_humidity,
            self.ambient_humidity_min,
            self.ambient_humidity_max,
        )

        machine_load_target = (
            state.baseline_load
            + 0.07 * second_daily_wave
            + weekend_factor
        )
        machine_load = (
            (0.85 ** STEP_HOURS) * state.previous_machine_load
            + (1.0 - 0.85 ** STEP_HOURS) * machine_load_target
            + float(rng.normal(0.0, 0.035 * math.sqrt(STEP_HOURS)))
        )
        machine_load = _clip(machine_load, 0.20, 1.00)

        lagged_machine_load = state.lagged_machine_load
        lagged_machine_temperature = state.lagged_machine_temperature
        lagged_ambient_humidity = state.lagged_ambient_humidity

        line_speed = (
            state.line_speed_baseline
            + 16.0 * (machine_load - state.baseline_load)
            + float(rng.normal(0.0, self.line_speed_std * 0.40))
        )
        line_speed = _clip(
            line_speed, self.line_speed_min, self.line_speed_max
        )

        temperature_target = (
            state.machine_temperature_baseline
            + 17.0 * (lagged_machine_load - state.baseline_load)
            + 0.18 * (ambient_temperature - self.ambient_temp_mean)
        )
        machine_temperature = (
            (0.65 ** STEP_HOURS) * state.previous_machine_temperature
            + (1.0 - 0.65 ** STEP_HOURS) * temperature_target
            + float(
                rng.normal(
                    0.0,
                    self.machine_temp_std * 0.12 * math.sqrt(STEP_HOURS),
                )
            )
        )
        machine_temperature = _clip(
            machine_temperature,
            self.machine_temp_min,
            self.machine_temp_max,
        )

        temperature_stress = max(
            0.0,
            (
                lagged_machine_temperature
                - state.machine_temperature_baseline
            )
            / 15.0,
        )
        vibration_target = (
            state.vibration_baseline
            + 1.50 * temperature_stress
            + 1.30 * max(machine_load - 0.78, 0.0)
        )
        vibration = (
            (0.65 ** STEP_HOURS) * state.previous_vibration
            + (1.0 - 0.65 ** STEP_HOURS) * vibration_target
            + float(
                rng.normal(
                    0.0, self.vibration_std * 0.18 * math.sqrt(STEP_HOURS)
                )
            )
        )
        vibration = _clip(
            vibration, self.vibration_min, self.vibration_max
        )

        power = (
            state.power_baseline
            + 78.0 * (machine_load - 0.50)
            + 0.65 * (line_speed - state.line_speed_baseline)
            + float(rng.normal(0.0, self.power_std * 0.25))
        )
        power = _clip(power, self.power_min, self.power_max)

        speed_ratio = state.line_speed_baseline / max(line_speed, 1.0)
        cycle_time = (
            self.cycle_time_mean * speed_ratio
            + float(rng.normal(0.0, self.cycle_time_std * 0.20))
        )
        cycle_time = _clip(
            cycle_time, self.cycle_time_min, self.cycle_time_max
        )

        state.hours_since_maintenance += STEP_HOURS

        if state.hours_since_maintenance > state.maintenance_interval:
            maintenance_completion_probability = (
                0.20 if machine_load > 0.85 else 0.45
            )
            if (
                float(rng.random())
                < 1.0
                - (1.0 - maintenance_completion_probability) ** STEP_HOURS
            ):
                state.hours_since_maintenance = 0.0
                state.maintenance_interval = max(
                    7 * 24,
                    int(14 * 24 + rng.integers(-48, 49)),
                )

        maintenance_overdue_hours = max(
            0.0, state.hours_since_maintenance - state.maintenance_interval
        )

        torque_deviation = (
            self.torque_mean
            + float(rng.normal(0.0, self.torque_std * 0.60))
            + 1.10 * max(machine_load - 0.82, 0.0)
            + 0.20 * max(vibration - self.vibration_mean, 0.0)
            + 0.60 * (0.90 - supplier_quality)
        )
        torque_deviation = _clip(
            torque_deviation, self.torque_min, self.torque_max
        )

        paint_line = _is_paint_line(str(line.line_type))

        if paint_line:
            paint_booth_temperature = (
                self.paint_temp_mean
                + 0.22 * (ambient_temperature - self.ambient_temp_mean)
                + float(rng.normal(0.0, self.paint_temp_std * 0.25))
            )
            paint_booth_temperature = _clip(
                paint_booth_temperature,
                self.paint_temp_min,
                self.paint_temp_max,
            )

            paint_humidity_target = (
                self.paint_humidity_mean
                + 0.40
                * (lagged_ambient_humidity - self.ambient_humidity_mean)
                + float(rng.normal(0.0, self.paint_humidity_std * 0.20))
            )
            paint_booth_humidity = _clip(
                paint_humidity_target,
                self.paint_humidity_min,
                self.paint_humidity_max,
            )
        else:
            paint_booth_temperature = np.nan
            paint_booth_humidity = np.nan

        supplier_quality_risk = max(0.0, 0.94 - supplier_quality)
        torque_risk = min(abs(torque_deviation) / 5.0, 1.0)
        speed_pressure = max(0.0, (line_speed - 48.0) / 12.0)
        vibration_risk = max(0.0, (vibration - 2.7) / 4.0)
        maintenance_risk = min(maintenance_overdue_hours / 96.0, 1.0)

        defect_target = (
            0.007
            + 0.34 * supplier_quality_risk
            + 0.025 * torque_risk
            + 0.030 * speed_pressure
            + 0.035 * vibration_risk
            + 0.025 * maintenance_risk
            + float(rng.normal(0.0, 0.0025))
        )
        defect_rate = (
            (0.30 ** STEP_HOURS) * state.previous_defect_rate
            + (1.0 - 0.30 ** STEP_HOURS) * defect_target
        )
        defect_rate = _clip(defect_rate, 0.0, 0.22)

        if paint_line:
            paint_humidity_risk = max(
                0.0, (float(paint_booth_humidity) - 65.0) / 25.0
            )
            paint_speed_risk = max(0.0, (line_speed - 46.0) / 14.0)

            paint_defect_rate = (
                0.004
                + 0.035 * paint_humidity_risk
                + 0.022 * paint_speed_risk
                + 0.22 * supplier_quality_risk
                + float(rng.normal(0.0, 0.0020))
            )
            paint_defect_rate = _clip(paint_defect_rate, 0.0, 0.18)
        else:
            paint_defect_rate = np.nan

        rework_target = 0.55 * defect_rate
        if paint_line:
            rework_target += 0.35 * float(paint_defect_rate)
        rework_target += float(rng.normal(0.0, 0.0018))

        rework_rate = (
            (0.35 ** STEP_HOURS) * state.previous_rework_rate
            + (1.0 - 0.35 ** STEP_HOURS) * rework_target
        )
        rework_rate = _clip(rework_rate, 0.0, 0.25)

        temperature_risk = max(0.0, (machine_temperature - 70.0) / 20.0)
        downtime_expected = (
            0.40
            + 11.0 * temperature_risk
            + 13.0 * vibration_risk
            + 15.0 * maintenance_risk
        )

        if downtime_expected <= 0.5:
            downtime_minutes = 0.0
        else:
            downtime_probability = _clip(
                1.0
                - (1.0 - min(downtime_expected / 40.0, 0.75)) ** STEP_HOURS,
                0.0,
                0.75,
            )
            if float(rng.random()) < downtime_probability:
                downtime_minutes = float(
                    rng.gamma(
                        shape=2.0,
                        scale=max(downtime_expected / 2.0, 0.5),
                    )
                )
            else:
                downtime_minutes = 0.0

        downtime_minutes = _clip(downtime_minutes, 0.0, 1.0)

        quality_score = (
            1.0
            - 2.10 * defect_rate
            - 1.15 * rework_rate
            - 0.030 * torque_risk
            - 0.08 * (1.0 - supplier_quality)
        )
        quality_score = (
            0.78 * quality_score + 0.22 * batch_quality_score
        )
        quality_score += float(rng.normal(0.0, 0.004))
        quality_score = _clip(quality_score, 0.50, 1.00)

        row = {
            "timestamp": timestamp,
            "plant_id": str(machine.plant_id),
            "plant_name": str(plant.plant_name),
            "production_line_id": str(machine.production_line_id),
            "production_line_name": str(line.line_name),
            "line_type": str(line.line_type),
            "machine_id": str(machine_id),
            "machine_name": str(machine.machine_name),
            "production_batch_id": production_batch_id,
            "vehicle_model_id": vehicle_model_id,
            "vehicle_model_name": vehicle_model_name,
            "supplier_lot_id": supplier_lot_id,
            "batch_status": batch_status,
            "ambient_temperature_c": round(ambient_temperature, 4),
            "ambient_humidity_pct": round(ambient_humidity, 4),
            "machine_load": round(machine_load, 6),
            "machine_temperature_c": round(machine_temperature, 4),
            "vibration_mm_s": round(vibration, 4),
            "power_kw": round(power, 4),
            "line_speed_units_per_hour": round(line_speed, 4),
            "cycle_time_seconds": round(cycle_time, 4),
            "hours_since_maintenance": round(
                state.hours_since_maintenance, 3
            ),
            "maintenance_overdue_hours": round(
                maintenance_overdue_hours, 3
            ),
            "supplier_lot_quality_score": round(supplier_quality, 6),
            "torque_deviation_nm": round(torque_deviation, 4),
            "paint_booth_temperature_c": (
                round(float(paint_booth_temperature), 4)
                if paint_line
                else np.nan
            ),
            "paint_booth_humidity_pct": (
                round(float(paint_booth_humidity), 4)
                if paint_line
                else np.nan
            ),
            "paint_defect_rate": (
                round(float(paint_defect_rate), 6)
                if paint_line
                else np.nan
            ),
            "defect_rate": round(defect_rate, 6),
            "rework_rate": round(rework_rate, 6),
            "downtime_minutes": round(downtime_minutes, 4),
            "quality_score": round(quality_score, 6),
            "data_origin": self.data_origin,
            "generator_version": self.generator_version,
        }

        state.previous_machine_temperature = machine_temperature
        state.previous_ambient_temperature = ambient_temperature
        state.previous_machine_load = machine_load
        state.previous_vibration = vibration
        state.previous_ambient_humidity = ambient_humidity
        state.previous_defect_rate = defect_rate
        state.previous_rework_rate = rework_rate
        state.lagged_machine_load = machine_load
        state.lagged_machine_temperature = machine_temperature
        state.lagged_ambient_humidity = ambient_humidity

        return row

    def generate_tick(
        self, machine_ids: list, timestamp: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Generate one row per machine_id for the given timestamp.
        """

        rows = [
            self.generate_row(machine_id, timestamp)
            for machine_id in machine_ids
        ]

        return pd.DataFrame(rows)
