"""
Configuration for the Predictive Early-Warning Service.

Warning-type definitions, thresholds, and window sizes are data-derived
(see IMPLEMENTATION_PLAN.md) rather than copied from the README's
illustrative example numbers. Every value is overridable via environment
variables, prefixed PEWS_ (Predictive Early-Warning Service) so these can
never collide with Causal_Discovery_Service's CDS_ variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Loads Predictive_Early_Warning_Service/.env (gitignored - see .env.example
# for the documented variable names without real values) so the Copilot's
# LLM credentials are available via os.getenv() without needing them
# exported manually in every shell. Safe to call even if .env doesn't
# exist - load_dotenv() then simply does nothing.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


@dataclass(frozen=True)
class WarningTypeConfig:
    warning_type: str
    cluster: str  # supplier_component_category-aligned name - see WARNING_CLUSTERS below
    target_metric: str
    threshold: float
    direction: str  # "above" or "below" - which side of the threshold is risky
    severity_label: str


# Clusters beyond BATTERY are new - one shared multi-label model per
# cluster (see warranty_train_model.py's proven multi-label
# RandomForestClassifier pattern, applied here to telematics instead of
# warranty/service data). Every new threshold below is the 95th
# percentile of that metric's REAL live distribution (queried directly:
# 1,346 vehicles / 7 days / 754,286 rows), the same self-calibration
# principle already used and proven in eligibility.py's driving-behavior
# check - not invented numbers.
#
# ECU_ELECTRONICS and ELECTRICAL_WIRING were considered and deliberately
# EXCLUDED from this live set: their only candidate telematics signals
# (dtc_count, warning_flag) are not independent evidence in this
# dataset - warning_flag is literally `dtc_count > 0` (confirmed in
# data/generators/causal/vehicle_telematics_timeseries.py), and
# dtc_count itself is a composite of thresholds on battery_temperature_c,
# battery_internal_resistance_ohm, transmission_slip_ms, and
# vehicle_vibration_mm_s - all already covered by other clusters below.
# A live warning type built on either would just be a redundant
# re-statement of an existing cluster's own signal, not new information.
# These two categories remain covered by the batch warranty model only,
# the same honest treatment already given to issues with no telematics
# signal at all.
WARNING_TYPES: tuple[WarningTypeConfig, ...] = (
    # --- BATTERY (unchanged - real Li-ion reference thresholds) ---
    WarningTypeConfig(
        warning_type="BATTERY_OVERHEATING",
        cluster="BATTERY",
        target_metric="battery_temperature_c",
        # 55.0C: realistic critical threshold for a Li-ion EV pack, not
        # this dataset's normal-operating p97 (33.0C) - see changes.md for
        # why that data-derived value fired far too often to be useful.
        threshold=_env_float("PEWS_BATTERY_OVERHEATING_THRESHOLD", 55.0),
        direction="above",
        severity_label="HIGH",
    ),
    WarningTypeConfig(
        warning_type="LOW_BATTERY_VOLTAGE",
        cluster="BATTERY",
        target_metric="battery_voltage_v",
        # 315.0V: ~10-15% SoC (~3.28V/cell) on a standard 96-cell 400V
        # pack, not this dataset's p07 (400.8V, ~98% SoC) - see changes.md.
        threshold=_env_float("PEWS_LOW_BATTERY_VOLTAGE_THRESHOLD", 315.0),
        direction="below",
        severity_label="HIGH",
    ),
    WarningTypeConfig(
        warning_type="BATTERY_DEGRADATION",
        cluster="BATTERY",
        target_metric="battery_internal_resistance_ohm",
        threshold=_env_float("PEWS_BATTERY_DEGRADATION_THRESHOLD", 0.0258),
        direction="above",
        severity_label="MEDIUM",
    ),
    # --- STEERING (new - p95 self-calibrated) ---
    WarningTypeConfig(
        warning_type="STEERING_STRESS",
        cluster="STEERING",
        target_metric="steering_torque_nm",
        threshold=_env_float("PEWS_STEERING_STRESS_THRESHOLD", 1.20),
        direction="above",
        severity_label="MEDIUM",
    ),
    # --- SUSPENSION (new - p95 self-calibrated) ---
    WarningTypeConfig(
        warning_type="SUSPENSION_STRAIN",
        cluster="SUSPENSION",
        target_metric="vehicle_vibration_mm_s",
        threshold=_env_float("PEWS_SUSPENSION_STRAIN_THRESHOLD", 2.97),
        direction="above",
        severity_label="MEDIUM",
    ),
    # --- DRIVETRAIN_COMPONENTS (new - p95 self-calibrated, 2 signals) ---
    WarningTypeConfig(
        warning_type="DRIVETRAIN_SLIP",
        cluster="DRIVETRAIN_COMPONENTS",
        target_metric="transmission_slip_ms",
        threshold=_env_float("PEWS_DRIVETRAIN_SLIP_THRESHOLD", 47.3),
        direction="above",
        severity_label="MEDIUM",
    ),
    WarningTypeConfig(
        warning_type="TRANSMISSION_OVERHEATING",
        cluster="DRIVETRAIN_COMPONENTS",
        target_metric="transmission_temperature_c",
        threshold=_env_float("PEWS_TRANSMISSION_OVERHEATING_THRESHOLD", 75.4),
        direction="above",
        severity_label="HIGH",
    ),
    # --- BRAKING_SYSTEM (new - p95 self-calibrated) ---
    WarningTypeConfig(
        warning_type="HARSH_BRAKING_PATTERN",
        cluster="BRAKING_SYSTEM",
        target_metric="impact_g_force",
        threshold=_env_float("PEWS_HARSH_BRAKING_PATTERN_THRESHOLD", 0.81),
        direction="above",
        severity_label="MEDIUM",
    ),
    # --- EXHAUST (new - p95 self-calibrated) ---
    WarningTypeConfig(
        warning_type="UNDERBODY_IMPACT_RISK",
        cluster="EXHAUST",
        target_metric="road_roughness_index",
        threshold=_env_float("PEWS_UNDERBODY_IMPACT_RISK_THRESHOLD", 2.75),
        direction="above",
        severity_label="LOW",
    ),
)

WARNING_TYPES_BY_NAME = {w.warning_type: w for w in WARNING_TYPES}

WARNING_CLUSTERS: dict[str, tuple[WarningTypeConfig, ...]] = {}
for _warning in WARNING_TYPES:
    WARNING_CLUSTERS[_warning.cluster] = WARNING_CLUSTERS.get(_warning.cluster, ()) + (_warning,)
del _warning

# --- Window sizes (see IMPLEMENTATION_PLAN.md for why these differ from
# the README's 48h/24h example) ---

FEATURE_WINDOW_HOURS = _env_int("PEWS_FEATURE_WINDOW_HOURS", 12)

# The label window no longer starts exactly at "now" - it starts
# LABEL_GAP_HOURS ahead, so a positive prediction genuinely means "not
# happening yet, but predicted to happen in this future window," not
# "already happening right now." Without this gap, a model that also sees
# the target metric's current value (excluded below, but even without that,
# a metric already AT the threshold trivially satisfies "crosses it in the
# next few hours") has very little real forecasting to do.
LABEL_GAP_HOURS = _env_int("PEWS_LABEL_GAP_HOURS", 3)
LABEL_WINDOW_HOURS = _env_int("PEWS_LABEL_WINDOW_HOURS", 12)

# --- Live scoring ---

RISK_THRESHOLD = _env_float("PEWS_RISK_THRESHOLD", 0.60)
SCHEDULER_TICK_SECONDS = _env_int("PEWS_SCHEDULER_TICK_SECONDS", 60)  # minute cadence, matching Live_Data_Formation's own tick
# Live_Data_Formation samples ~5.6% of the vehicle fleet per minute on
# average, so a 12h trailing window (FEATURE_WINDOW_HOURS) yields ~40 rows
# per vehicle on AVERAGE - meaning a threshold at or above 40 fails most
# vehicles purely from sampling variance, not genuine data sparsity.
# Measured directly against live data: a threshold of 60 let only 1 of 100
# actively-sampled vehicles through per tick. 20 comfortably sits below the
# real average while still requiring enough history for compute_features()
# to be meaningful.
MIN_RAW_ROWS_TO_SCORE = _env_int("PEWS_MIN_RAW_ROWS_TO_SCORE", 20)

# --- Causal investigation (the "explain" step) ---

CAUSAL_LOOKBACK_HOURS = _env_int("PEWS_CAUSAL_LOOKBACK_HOURS", 24)
CAUSAL_RESAMPLE_MINUTES = _env_int("PEWS_CAUSAL_RESAMPLE_MINUTES", 15)
CAUSAL_TAU_MAX = _env_int("PEWS_CAUSAL_TAU_MAX", 3)
CAUSAL_PC_ALPHA = _env_float("PEWS_CAUSAL_PC_ALPHA", 0.05)

# --- Feature metrics: the raw telemetry columns features are computed from ---
#
# Expanded from the original 9 (battery-only era) to the full real
# telematics field set - the same TELEMATICS_NUMERIC_COLUMNS
# investigate.py's LPCMCI step already reads from
# Causal_Discovery_Service/config.py, so every cluster's model can see
# every other cluster's signals as context (compute_features()'s
# exclude_metrics still removes a warning's own target metric from its
# own feature set, so this stays genuine forecasting, not current-state
# detection).

FEATURE_METRICS: tuple[str, ...] = (
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
)

# --- Paths ---

SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SERVICE_ROOT, "models")
WARNINGS_DIR = os.path.join(SERVICE_ROOT, "warnings")
# Deliberately NOT inside WARNINGS_DIR - list_warnings() scans every
# *.json file there and parses it as a Warning; a ranking-cache file
# with a different shape dropped in that directory would crash it.
IMPACT_RANKING_PATH = os.path.join(SERVICE_ROOT, "impact_ranking.json")

# --- Copilot LLM (see copilot/README.md) ---
# Read from the environment (.env, loaded above) - never hardcoded here.

OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_NAME = os.getenv("LLM_NAME")

COPILOT_TEMPERATURE = _env_float("PEWS_COPILOT_TEMPERATURE", 0.2)
COPILOT_MAX_HISTORY_TURNS = _env_int("PEWS_COPILOT_MAX_HISTORY_TURNS", 10)
COPILOT_MAX_RESPONSE_TOKENS = _env_int("PEWS_COPILOT_MAX_RESPONSE_TOKENS", 700)

COPILOT_CONVERSATIONS_DIR = os.path.join(SERVICE_ROOT, "copilot", "copilot_conversations")
