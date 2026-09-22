"""
Live, minute-by-minute vehicle-telematics row generator.

Schema-compatible with:
    data/generators/causal/vehicle_telematics_timeseries.py

This module produces exactly ONE row per selected vehicle per call
to generate_tick(), instead of a whole historical batch at once.

Unlike a batch re-run, each vehicle's autoregressive state (speed,
ambient temperature, road roughness, odometer, ...) is kept in
memory across calls so consecutive minutes move smoothly instead of
resetting to a cold start every tick.

Column names, formulas, clipping ranges, and scenario-degradation
logic intentionally mirror the original generator so downstream
consumers see an identical row shape.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from data.generators.common.seed import derive_seed, make_rng

SCENARIO_FAMILIES: tuple[str, ...] = (
    "BATTERY_DEGRADATION",
    "TRANSMISSION_DEGRADATION",
    "SUSPENSION_STEERING_DEGRADATION",
)

# Matches the original generator's degradation_curve, which ramps
# linearly from 0.0 to 1.0 across one full historical run
# (history_days * 24 * 60 minutes). Live ticks keep advancing this
# same counter per vehicle so degradation keeps progressing smoothly
# instead of resetting every tick.
DEGRADATION_RAMP_MINUTES = 7 * 24 * 60


def _derive_vehicle_scenario_family(base_seed: int, vehicle_id: str) -> str:
    position = derive_seed(
        base_seed, f"causal.vehicle_telematics.scenario.{vehicle_id}"
    ) % len(SCENARIO_FAMILIES)
    return SCENARIO_FAMILIES[position]


def _clip(value: float, minimum: float, maximum: float) -> float:
    return float(np.clip(value, minimum, maximum))


class VehicleState:
    """
    Per-vehicle persistent state carried between minute ticks.
    """

    __slots__ = (
        "rng",
        "scenario_family",
        "scenario_strength",
        "phase",
        "minute_index",
        "odometer_km",
        "previous_speed",
        "previous_ambient",
        "previous_roughness",
    )


class LiveTelematicsGenerator:
    """
    Holds the delivered-vehicle roster and per-vehicle state, and
    produces one DataFrame of new telemetry rows per tick.
    """

    def __init__(
        self,
        deliveries: pd.DataFrame,
        generation: dict,
    ) -> None:

        self.deliveries = deliveries.set_index("vehicle_id", drop=False)

        self.base_seed = int(generation["seed"])

        provenance = generation.get("provenance", {})
        self.data_origin = str(
            provenance.get("data_origin", "SYNTHETIC")
        )
        self.generator_version = str(
            generation.get("generator_version", "1.0.0")
        )

        self._states: dict[str, VehicleState] = {}

    def _get_or_init_state(self, vehicle_id: str) -> VehicleState:

        state = self._states.get(vehicle_id)

        if state is not None:
            return state

        vehicle = self.deliveries.loc[vehicle_id]

        rng = make_rng(
            derive_seed(
                self.base_seed,
                f"live.vehicle_telematics.{vehicle_id}",
            )
        )

        state = VehicleState()
        state.rng = rng
        state.scenario_family = _derive_vehicle_scenario_family(
            self.base_seed, vehicle_id
        )

        supplier_quality = float(vehicle.supplier_lot_quality_score)
        production_quality = float(vehicle.production_quality_score)
        lineage_risk = _clip(
            1.0 - 0.5 * (supplier_quality + production_quality),
            0.0,
            0.25,
        )
        state.scenario_strength = 0.65 + 2.0 * lineage_risk
        state.phase = float(rng.uniform(0.0, 2.0 * math.pi))

        state.minute_index = 0
        state.odometer_km = 120.0 + float(
            derive_seed(self.base_seed, f"odometer.{vehicle_id}") % 3500
        )

        state.previous_speed = 0.0
        state.previous_ambient = 28.0 + float(rng.normal(0.0, 0.4))
        state.previous_roughness = 2.1 + float(rng.normal(0.0, 0.1))

        self._states[vehicle_id] = state

        return state

    def generate_row(
        self, vehicle_id: str, timestamp: pd.Timestamp
    ) -> dict[str, Any]:
        """
        Generate exactly one new telemetry observation for one
        vehicle at one timestamp, continuing on from that vehicle's
        previous state.
        """

        state = self._get_or_init_state(vehicle_id)
        rng = state.rng

        vehicle = self.deliveries.loc[vehicle_id]

        index = state.minute_index
        day_phase = 2.0 * math.pi * (index % 1440.0) / 1440.0
        degradation = min(
            1.0, index / float(DEGRADATION_RAMP_MINUTES)
        )

        commute = max(
            0.0, math.sin(4.0 * math.pi * index / 1440.0 + state.phase)
        )
        stopped = rng.random() < 0.015
        target_speed = 0.0 if stopped else 58.0 * commute
        speed = _clip(
            0.86 * state.previous_speed
            + 0.14 * target_speed
            + float(rng.normal(0.0, 1.8)),
            0.0,
            115.0,
        )

        ambient_target = 29.0 + 5.0 * math.sin(day_phase - math.pi / 2.0)
        ambient = _clip(
            0.97 * state.previous_ambient
            + 0.03 * ambient_target
            + float(rng.normal(0.0, 0.08)),
            14.0,
            46.0,
        )

        roughness = _clip(
            0.94 * state.previous_roughness
            + 0.06 * (1.8 + speed / 65.0)
            + float(rng.normal(0.0, 0.06)),
            0.4,
            7.5,
        )

        driving = speed > 3.0
        current = max(0.0, 8.0 + 0.75 * speed + float(rng.normal(0.0, 2.2)))
        if not driving:
            current = max(0.0, 1.5 + float(rng.normal(0.0, 0.15)))

        battery_effect = (
            degradation
            if state.scenario_family == "BATTERY_DEGRADATION"
            else 0.12 * degradation
        )
        battery_resistance = _clip(
            0.021
            + 0.035 * (state.scenario_strength - 0.65) / 2.0
            + 0.011 * state.scenario_strength * battery_effect
            + float(rng.normal(0.0, 0.00012)),
            0.015,
            0.060,
        )
        battery_temperature = _clip(
            ambient
            + 0.055 * current
            + 160.0 * battery_resistance
            + 5.0 * state.scenario_strength * battery_effect,
            15.0,
            70.0,
        )
        battery_soc = _clip(
            88.0
            - 48.0
            * (
                (index + (derive_seed(self.base_seed, vehicle_id) % 500))
                % 1440.0
            )
            / 1440.0
            - 0.025 * speed,
            18.0,
            96.0,
        )
        battery_voltage = _clip(
            402.0
            - current * battery_resistance
            - 0.045 * (battery_temperature - 30.0),
            350.0,
            410.0,
        )

        transmission_effect = (
            degradation
            if state.scenario_family == "TRANSMISSION_DEGRADATION"
            else 0.10 * degradation
        )
        transmission_slip = _clip(
            22.0
            + 0.42 * speed
            + 48.0 * state.scenario_strength * transmission_effect
            + float(rng.normal(0.0, 1.0)),
            5.0,
            145.0,
        )
        converter_slip = _clip(
            45.0 + 1.8 * speed + 2.1 * transmission_slip, 30.0, 520.0
        )
        transmission_temperature = _clip(
            ambient + 20.0 + 0.31 * speed + 0.10 * transmission_slip,
            35.0,
            125.0,
        )

        impact = max(
            0.0,
            roughness * speed / 190.0 + float(rng.normal(0.0, 0.025)),
        )
        if rng.random() < 0.0015:
            impact += float(rng.uniform(0.8, 2.2))

        suspension_effect = (
            degradation
            if state.scenario_family == "SUSPENSION_STEERING_DEGRADATION"
            else 0.10 * degradation
        )
        steering_angle = _clip(
            11.0 * math.sin(index / 18.0 + state.phase)
            + float(rng.normal(0.0, 0.7)),
            -42.0,
            42.0,
        )
        steering_torque = _clip(
            0.055 * steering_angle
            + 0.24 * roughness
            + 2.2 * state.scenario_strength * suspension_effect,
            -8.0,
            12.0,
        )
        vibration = _clip(
            0.7
            + 0.018 * speed
            + 0.24 * roughness
            + 0.012 * transmission_slip
            + 1.8 * state.scenario_strength * suspension_effect,
            0.2,
            9.0,
        )
        vertical_acceleration = _clip(
            1.0
            + 0.05 * roughness
            + 0.25 * impact
            + float(rng.normal(0.0, 0.015)),
            0.7,
            2.5,
        )
        lateral_acceleration = _clip(
            0.0025 * speed * abs(steering_angle)
            + float(rng.normal(0.0, 0.015)),
            0.0,
            1.2,
        )

        dtc_count = (
            int(battery_temperature > 45.0)
            + int(battery_resistance > 0.032)
            + int(transmission_slip > 78.0)
            + int(vibration > 4.3)
        )
        warning_flag = dtc_count > 0

        odometer_km = state.odometer_km + speed / 60.0

        row = {
            "timestamp": timestamp,
            "vehicle_id": str(vehicle_id),
            "vehicle_model_id": str(vehicle.vehicle_model_id),
            "vehicle_model_name": str(vehicle.vehicle_model_name),
            "variant": str(vehicle.variant),
            "production_batch_id": str(vehicle.production_batch_id),
            "supplier_lot_id": str(vehicle.primary_supplier_lot_id),
            "plant_id": str(vehicle.plant_id),
            "production_line_id": str(vehicle.production_line_id),
            "odometer_km": round(odometer_km, 3),
            "vehicle_speed_kph": round(speed, 3),
            "ambient_temperature_c": round(ambient, 3),
            "battery_temperature_c": round(battery_temperature, 3),
            "battery_soc_pct": round(battery_soc, 3),
            "battery_voltage_v": round(battery_voltage, 3),
            "battery_current_a": round(current, 3),
            "battery_internal_resistance_ohm": round(
                battery_resistance, 6
            ),
            "transmission_temperature_c": round(
                transmission_temperature, 3
            ),
            "transmission_slip_ms": round(transmission_slip, 3),
            "torque_converter_slip_rpm": round(converter_slip, 3),
            "steering_torque_nm": round(steering_torque, 3),
            "steering_angle_deg": round(steering_angle, 3),
            "vehicle_vibration_mm_s": round(vibration, 3),
            "vertical_acceleration_g": round(vertical_acceleration, 4),
            "lateral_acceleration_g": round(lateral_acceleration, 4),
            "road_roughness_index": round(roughness, 3),
            "impact_g_force": round(impact, 4),
            "dtc_count": int(dtc_count),
            "warning_flag": bool(warning_flag),
            "data_origin": self.data_origin,
            "generator_version": self.generator_version,
        }

        state.minute_index += 1
        state.odometer_km = odometer_km
        state.previous_speed = speed
        state.previous_ambient = ambient
        state.previous_roughness = roughness

        return row

    def generate_tick(
        self, vehicle_ids: list, timestamp: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Generate one row per vehicle_id for the given timestamp.
        """

        rows = [
            self.generate_row(vehicle_id, timestamp)
            for vehicle_id in vehicle_ids
        ]

        return pd.DataFrame(rows)
