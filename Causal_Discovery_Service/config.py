"""
Configuration for the Causal Discovery Service.

Every tunable setting lives here, in one place, as two independent
dataclasses (one per domain) so that changing manufacturing's tau_max can
never accidentally change telematics' tau_max or either domain's pc_alpha.

All defaults can be overridden independently via environment variables,
using the CDS_ (Causal Discovery Service) prefix so these variables can
never collide with anything read by the existing causal service or by
Live_Data_Formation.

This module has no imports from backend/ or Live_Data_Formation/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class DomainCausalConfig:
    """
    All settings needed to run one domain's causal-discovery pipeline.

    tau_min / tau_max / pc_alpha are passed straight through to
    LPCMCI.run_lpcmci(tau_min=..., tau_max=..., pc_alpha=...).
    """

    domain: str

    # --- LPCMCI parameters (independently configurable per domain) ---
    tau_min: int
    tau_max: int
    pc_alpha: float

    # --- Rolling-window / resampling parameters ---
    window_hours: int
    resample_minutes: int

    # --- Entity-selection parameters ---
    min_raw_rows: int
    max_entities: int

    # --- Preprocessing parameters ---
    max_gap_bins_to_interpolate: int
    near_constant_std_threshold: float
    stationarity_pvalue_threshold: float
    auto_difference_nonstationary: bool


def _load_manufacturing_config() -> DomainCausalConfig:
    return DomainCausalConfig(
        domain="manufacturing",
        tau_min=_env_int("CDS_MANUFACTURING_TAU_MIN", 0),
        tau_max=_env_int("CDS_MANUFACTURING_TAU_MAX", 6),
        pc_alpha=_env_float("CDS_MANUFACTURING_PC_ALPHA", 0.05),
        window_hours=_env_int("CDS_MANUFACTURING_WINDOW_HOURS", 24),
        resample_minutes=_env_int("CDS_MANUFACTURING_RESAMPLE_MINUTES", 5),
        min_raw_rows=_env_int("CDS_MANUFACTURING_MIN_RAW_ROWS", 300),
        max_entities=_env_int("CDS_MANUFACTURING_MAX_ENTITIES", 15),
        max_gap_bins_to_interpolate=_env_int(
            "CDS_MANUFACTURING_MAX_GAP_BINS", 3
        ),
        near_constant_std_threshold=_env_float(
            "CDS_MANUFACTURING_NEAR_CONSTANT_STD", 1e-6
        ),
        stationarity_pvalue_threshold=_env_float(
            "CDS_MANUFACTURING_STATIONARITY_PVALUE", 0.05
        ),
        auto_difference_nonstationary=(
            _env_str("CDS_MANUFACTURING_AUTO_DIFFERENCE", "false").lower()
            == "true"
        ),
    )


def _load_telematics_config() -> DomainCausalConfig:
    return DomainCausalConfig(
        domain="telematics",
        tau_min=_env_int("CDS_TELEMATICS_TAU_MIN", 0),
        tau_max=_env_int("CDS_TELEMATICS_TAU_MAX", 4),
        pc_alpha=_env_float("CDS_TELEMATICS_PC_ALPHA", 0.05),
        window_hours=_env_int("CDS_TELEMATICS_WINDOW_HOURS", 168),
        resample_minutes=_env_int("CDS_TELEMATICS_RESAMPLE_MINUTES", 15),
        min_raw_rows=_env_int("CDS_TELEMATICS_MIN_RAW_ROWS", 100),
        max_entities=_env_int("CDS_TELEMATICS_MAX_ENTITIES", 15),
        max_gap_bins_to_interpolate=_env_int(
            "CDS_TELEMATICS_MAX_GAP_BINS", 3
        ),
        near_constant_std_threshold=_env_float(
            "CDS_TELEMATICS_NEAR_CONSTANT_STD", 1e-6
        ),
        stationarity_pvalue_threshold=_env_float(
            "CDS_TELEMATICS_STATIONARITY_PVALUE", 0.05
        ),
        auto_difference_nonstationary=(
            _env_str("CDS_TELEMATICS_AUTO_DIFFERENCE", "false").lower()
            == "true"
        ),
    )


MANUFACTURING_CONFIG = _load_manufacturing_config()
TELEMATICS_CONFIG = _load_telematics_config()


# ---------------------------------------------------------------------------
# Column selections (see IMPLEMENTATION_PLAN.md section 7 for the reasoning)
# ---------------------------------------------------------------------------

MANUFACTURING_CONTEXT_COLUMNS: tuple[str, ...] = (
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
    "data_origin",
    "generator_version",
)

MANUFACTURING_ENTITY_COLUMN = "machine_id"

MANUFACTURING_PAINT_ONLY_COLUMNS: tuple[str, ...] = (
    "paint_booth_temperature_c",
    "paint_booth_humidity_pct",
    "paint_defect_rate",
)

MANUFACTURING_NUMERIC_COLUMNS: tuple[str, ...] = (
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
    "defect_rate",
    "rework_rate",
    "downtime_minutes",
    "quality_score",
)

TELEMATICS_CONTEXT_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "vehicle_id",
    "vehicle_model_id",
    "vehicle_model_name",
    "variant",
    "production_batch_id",
    "supplier_lot_id",
    "plant_id",
    "production_line_id",
    "data_origin",
    "generator_version",
)

TELEMATICS_ENTITY_COLUMN = "vehicle_id"

TELEMATICS_EXCLUDED_COLUMNS: tuple[str, ...] = ("odometer_km",)

TELEMATICS_NUMERIC_COLUMNS: tuple[str, ...] = (
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
)

TELEMATICS_BOOLEAN_COLUMNS: tuple[str, ...] = ("warning_flag",)


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

DEFAULT_DATABASE_URL = (
    "postgresql://mahindra:mahindra@127.0.0.1:5432/mahindra_ai"
)


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql://" + value[len("postgresql+asyncpg://") :]
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


def resolve_database_url() -> str:
    """
    Same resolution order used elsewhere in this project
    (MAHINDRA_DATABASE_URL, then DATABASE_URL, then a local default), but
    this function is defined independently here rather than imported from
    any other module, so this service has no code dependency on either the
    old causal service or Live_Data_Formation.
    """

    raw = (
        os.getenv("MAHINDRA_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    return _normalize_database_url(raw)


RUNS_OUTPUT_ROOT = os.path.join(os.path.dirname(__file__), "runs")
