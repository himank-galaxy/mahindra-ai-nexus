"""Synthetic vehicle service-event generator.

Dependency chain:

Production -> Allocation -> Delivery -> Service Events -> Warranty Claims

Service issues are generated from delivery quality and exposure evidence. This
module does not write CSV files; callers own persistence and import.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from data.generators.common.helpers import load_generation_config
from data.generators.common.ids import make_entity_id
from data.generators.common.seed import derive_seed, make_rng

FIRST_INSPECTION_ATTENDANCE_PROBABILITY = 0.78
MIN_FIRST_INSPECTION_DAYS = 20
MAX_FIRST_INSPECTION_DAYS = 45
BASE_UNSCHEDULED_REPAIR_PROBABILITY = 0.08
MAX_ISSUE_EXPOSURE_DAYS = 120.0
QUALITY_REFERENCE = 0.96
SUPPLIER_QUALITY_REFERENCE = 0.92
MIN_DAILY_KM = 18.0
MAX_DAILY_KM = 65.0
FIRST_INSPECTION_MIN_HOURS = 1.0
FIRST_INSPECTION_MAX_HOURS = 5.0
REPAIR_MIN_HOURS = 2.0
REPAIR_MAX_HOURS = 72.0

VALID_SERVICE_TYPES = {"FIRST_INSPECTION", "UNSCHEDULED_REPAIR"}
VALID_SERVICE_STATUSES = {"COMPLETED"}
VALID_SEVERITIES = {"NONE", "LOW", "MEDIUM", "HIGH"}

# ============================================================
# ACCIDENT / COLLISION EVENTS
#
# Kept separate from the ordinary defect-driven UNSCHEDULED_REPAIR path
# above (generate_service_events) - accidents are a different cause
# entirely (external event, not a manufacturing/supplier-quality issue),
# so they get their own independent RNG stream and are appended after
# ordinary service events are generated, rather than interleaved into
# that loop. This means adding accidents does not shift the random
# sequence - and therefore the resulting rows - for any already-existing
# non-accident service event.
#
# service_type stays "UNSCHEDULED_REPAIR" for an accident (it genuinely
# is unscheduled) - is_accident_caused is what actually distinguishes
# "why", and is what downstream code must check before treating a row
# as warranty-eligible. warranty_candidate is always forced to False for
# these rows: an accident is not Mahindra's manufacturing liability, and
# must never be picked up by warranty.py's claim-candidate filter.
#
# All numbers below (annual probability, severity mix, g-force ranges)
# are illustrative synthetic PoC assumptions, not real accident-rate
# statistics or crash-test data.
# ============================================================

ACCIDENT_ISSUE_CATEGORY = "ACCIDENT_DAMAGE"
ACCIDENT_ANNUAL_PROBABILITY = 0.04
ACCIDENT_COMPONENT_CATEGORIES = (
    "STEEL_BODY_PANELS",
    "GLASS",
    "LIGHTING",
    "SUSPENSION",
    "BRAKING_SYSTEM",
)
ACCIDENT_SEVERITY_WEIGHTS = {"LOW": 0.35, "MEDIUM": 0.45, "HIGH": 0.20}
ACCIDENT_IMPACT_G_FORCE_RANGE_BY_SEVERITY = {
    "LOW": (1.5, 3.0),
    "MEDIUM": (3.0, 6.0),
    "HIGH": (6.0, 12.0),
}

COMPONENT_ISSUE_MAP = {
    "STEEL_BODY_PANELS": ["BODY_ALIGNMENT", "PANEL_NOISE"],
    "PAINT_COATINGS": ["PAINT_FINISH", "SURFACE_DEFECT"],
    "ELECTRICAL_WIRING": ["ELECTRICAL_WARNING", "INTERMITTENT_ELECTRICAL"],
    "ECU_ELECTRONICS": ["ECU_WARNING", "ELECTRONIC_CONTROL"],
    "BRAKING_SYSTEM": ["BRAKE_NOISE", "BRAKE_FEEL"],
    "SUSPENSION": ["SUSPENSION_NOISE", "RIDE_QUALITY"],
    "STEERING": ["STEERING_FEEL", "STEERING_NOISE"],
    "TYRES": ["TYRE_VIBRATION", "TYRE_WEAR"],
    "SEATING": ["SEAT_ADJUSTMENT", "SEAT_NOISE"],
    "GLASS": ["GLASS_ALIGNMENT", "WATER_SEALING"],
    "LIGHTING": ["LIGHTING_FAULT", "LIGHT_ALIGNMENT"],
    "HVAC": ["HVAC_COOLING", "HVAC_NOISE"],
    "BATTERY": ["BATTERY_WARNING", "STARTING_ISSUE"],
    "FASTENERS": ["RATTLE_NOISE", "FASTENER_LOOSENESS"],
    "PLASTIC_TRIM": ["INTERIOR_RATTLE", "TRIM_ALIGNMENT"],
    "RUBBER_SEALS": ["WATER_SEALING", "WIND_NOISE"],
    "ADHESIVES": ["BONDING_DEFECT", "TRIM_SEPARATION"],
    "FLUIDS": ["FLUID_LEVEL", "FLUID_LEAK"],
    "EXHAUST": ["EXHAUST_NOISE", "EXHAUST_WARNING"],
    "DRIVETRAIN_COMPONENTS": ["DRIVETRAIN_NOISE", "POWER_DELIVERY"],
}
DEFAULT_ISSUES = ["GENERAL_NOISE", "CUSTOMER_REPORTED_ISSUE"]

SERVICE_COLUMNS = [
    "service_event_id", "delivery_id", "allocation_id", "booking_id",
    "customer_id", "vehicle_id", "vehicle_model_id", "vehicle_model_name",
    "variant", "service_dealer_id", "service_dealer_name", "region_id",
    "region_name", "city_id", "city_name", "production_batch_id", "plant_id",
    "plant_name", "production_line_id", "production_line_name",
    "representative_machine_id", "representative_machine_name",
    "primary_supplier_id", "primary_supplier_name", "primary_supplier_lot_id",
    "supplier_component_category", "supplier_lot_quality_score",
    "production_quality_score", "service_type", "service_started_at",
    "service_completed_at", "days_since_delivery", "odometer_km",
    "complaint_reported", "issue_category", "severity", "diagnosis",
    "repair_required", "is_accident_caused", "accident_impact_g_force",
    "service_duration_hours", "service_score",
    "warranty_candidate", "service_status", "data_origin", "generator_version",
]


def _get_generation_end(generation: Mapping[str, Any]) -> pd.Timestamp:
    time_config = generation.get("time", generation.get("time_window", {}))
    iot_config = generation.get("iot", {})
    end_value = iot_config.get(
        "end_date",
        time_config.get("end", time_config.get("end_date")),
    )
    if end_value is None:
        raise KeyError("Missing generation end/end_date")
    timezone = str(time_config.get("timezone", "Asia/Kolkata"))
    timestamp = pd.Timestamp(end_value)
    return (
        timestamp.tz_localize(timezone)
        if timestamp.tzinfo is None
        else timestamp.tz_convert(timezone)
    )


def _validate_inputs(deliveries: pd.DataFrame) -> None:
    required = {
        "delivery_id", "allocation_id", "booking_id", "lead_id", "customer_id",
        "vehicle_id", "vehicle_model_id", "vehicle_model_name", "variant",
        "dealer_id", "dealer_name", "region_id", "region_name", "city_id",
        "city_name", "production_batch_id", "plant_id", "plant_name",
        "production_line_id", "production_line_name", "representative_machine_id",
        "representative_machine_name", "primary_supplier_id",
        "primary_supplier_name", "primary_supplier_lot_id",
        "supplier_lot_quality_score", "production_quality_score",
        "actual_delivery_date", "handover_score", "delivery_status",
    }
    missing = required.difference(deliveries.columns)
    if missing:
        raise ValueError(
            "Deliveries DataFrame is missing columns required by service.py: "
            + ", ".join(sorted(missing))
        )
    if deliveries.empty:
        raise ValueError("Deliveries DataFrame cannot be empty")
    if deliveries["delivery_id"].duplicated().any():
        raise ValueError("Duplicate delivery_id values found")
    delivered = deliveries[deliveries["delivery_status"] == "DELIVERED"]
    if delivered.empty:
        raise ValueError("No delivered vehicles available for service generation")
    if delivered["actual_delivery_date"].isna().any():
        raise ValueError("Delivered vehicles must have actual_delivery_date")


def _calculate_issue_probability(
    production_quality: float,
    supplier_quality: float,
    exposure_days: float,
) -> float:
    production_quality = float(np.clip(production_quality, 0.0, 1.0))
    supplier_quality = float(np.clip(supplier_quality, 0.0, 1.0))
    exposure_factor = float(np.clip(exposure_days / MAX_ISSUE_EXPOSURE_DAYS, 0.0, 1.0))
    production_gap = max(QUALITY_REFERENCE - production_quality, 0.0)
    supplier_gap = max(SUPPLIER_QUALITY_REFERENCE - supplier_quality, 0.0)
    probability = (
        BASE_UNSCHEDULED_REPAIR_PROBABILITY * exposure_factor
        + production_gap * 1.15 * exposure_factor
        + supplier_gap * 0.65 * exposure_factor
    )
    return float(np.clip(probability, 0.0, 0.35))


def _choose_issue_category(rng: np.random.Generator, component_category: str) -> str:
    candidates = COMPONENT_ISSUE_MAP.get(
        str(component_category).strip().upper(),
        DEFAULT_ISSUES,
    )
    return str(rng.choice(candidates))


def _derive_issue_severity(
    rng: np.random.Generator,
    production_quality: float,
    supplier_quality: float,
) -> str:
    quality = 0.65 * float(production_quality) + 0.35 * float(supplier_quality)
    risk = float(np.clip(1.0 - quality, 0.0, 1.0))
    high_probability = 0.03 + risk * 0.55
    medium_probability = 0.25 + risk * 0.60
    random_value = float(rng.random())
    if random_value < high_probability:
        return "HIGH"
    if random_value < high_probability + medium_probability:
        return "MEDIUM"
    return "LOW"


def _generate_service_duration_hours(
    rng: np.random.Generator,
    service_type: str,
    severity: str,
) -> float:
    if service_type == "FIRST_INSPECTION":
        return float(rng.uniform(FIRST_INSPECTION_MIN_HOURS, FIRST_INSPECTION_MAX_HOURS))
    if severity == "HIGH":
        low, high = 18.0, REPAIR_MAX_HOURS
    elif severity == "MEDIUM":
        low, high = 6.0, 36.0
    else:
        low, high = REPAIR_MIN_HOURS, 14.0
    return float(rng.uniform(low, high))


def _generate_service_score(
    rng: np.random.Generator,
    service_type: str,
    severity: str,
    duration_hours: float,
) -> float:
    score = float(rng.normal(4.35, 0.38))
    if service_type == "UNSCHEDULED_REPAIR":
        score -= 0.20
    if severity == "MEDIUM":
        score -= 0.15
    elif severity == "HIGH":
        score -= 0.35
    if duration_hours > 24:
        score -= 0.20
    if duration_hours > 48:
        score -= 0.25
    return round(float(np.clip(score, 1.0, 5.0)), 2)


def _derive_warranty_candidate(
    service_type: str,
    severity: str,
    production_quality: float,
    supplier_quality: float,
) -> bool:
    if service_type != "UNSCHEDULED_REPAIR":
        return False
    if severity in {"MEDIUM", "HIGH"}:
        return True
    if production_quality < 0.94:
        return True
    return supplier_quality < 0.88


def _build_service_event(
    *, service_counter: int, delivery: Any, service_type: str,
    service_date: pd.Timestamp, delivery_date: pd.Timestamp, daily_km: float,
    rng: np.random.Generator, component_category: str,
    issue_category: str | None, severity: str,
    is_accident_caused: bool = False, accident_impact_g_force: float = 0.0,
    warranty_candidate_override: bool | None = None,
) -> dict[str, Any]:
    production_quality = float(delivery.production_quality_score)
    supplier_quality = float(delivery.supplier_lot_quality_score)
    days_since_delivery = max(
        0.0,
        (service_date - delivery_date).total_seconds() / 86400.0,
    )
    odometer_km = max(round(daily_km * days_since_delivery), 1)
    duration_hours = _generate_service_duration_hours(rng, service_type, severity)
    completed_at = service_date + timedelta(hours=duration_hours)
    score = _generate_service_score(rng, service_type, severity, duration_hours)
    warranty_candidate = (
        warranty_candidate_override
        if warranty_candidate_override is not None
        else _derive_warranty_candidate(
            service_type, severity, production_quality, supplier_quality
        )
    )
    if service_type == "FIRST_INSPECTION":
        complaint_reported = False
        issue_category = None
        diagnosis = "ROUTINE_INSPECTION_OK"
        repair_required = False
    else:
        complaint_reported = True
        diagnosis = "ISSUE_CONFIRMED"
        repair_required = True
    return {
        "service_event_id": make_entity_id("service_event", service_counter, width=6),
        "delivery_id": delivery.delivery_id,
        "allocation_id": delivery.allocation_id,
        "booking_id": delivery.booking_id,
        "customer_id": delivery.customer_id,
        "vehicle_id": delivery.vehicle_id,
        "vehicle_model_id": delivery.vehicle_model_id,
        "vehicle_model_name": delivery.vehicle_model_name,
        "variant": delivery.variant,
        "service_dealer_id": delivery.dealer_id,
        "service_dealer_name": delivery.dealer_name,
        "region_id": delivery.region_id,
        "region_name": delivery.region_name,
        "city_id": delivery.city_id,
        "city_name": delivery.city_name,
        "production_batch_id": delivery.production_batch_id,
        "plant_id": delivery.plant_id,
        "plant_name": delivery.plant_name,
        "production_line_id": delivery.production_line_id,
        "production_line_name": delivery.production_line_name,
        "representative_machine_id": delivery.representative_machine_id,
        "representative_machine_name": delivery.representative_machine_name,
        "primary_supplier_id": delivery.primary_supplier_id,
        "primary_supplier_name": delivery.primary_supplier_name,
        "primary_supplier_lot_id": delivery.primary_supplier_lot_id,
        "supplier_component_category": component_category,
        "supplier_lot_quality_score": round(supplier_quality, 6),
        "production_quality_score": round(production_quality, 6),
        "service_type": service_type,
        "service_started_at": service_date,
        "service_completed_at": completed_at,
        "days_since_delivery": round(days_since_delivery, 3),
        "odometer_km": odometer_km,
        "complaint_reported": complaint_reported,
        "issue_category": issue_category,
        "severity": severity,
        "diagnosis": diagnosis,
        "repair_required": repair_required,
        "is_accident_caused": bool(is_accident_caused),
        "accident_impact_g_force": round(float(accident_impact_g_force), 3),
        "service_duration_hours": round(duration_hours, 3),
        "service_score": score,
        "warranty_candidate": warranty_candidate,
        "service_status": "COMPLETED",
    }


def _infer_component_category(supplier_name: str) -> str:
    name = str(supplier_name).upper()
    mapping = {
        "BODYSTEEL": "STEEL_BODY_PANELS", "COATPRO": "PAINT_COATINGS",
        "WIRELINK": "ELECTRICAL_WIRING", "ECU LOGIC": "ECU_ELECTRONICS",
        "BRAKESAFE": "BRAKING_SYSTEM", "RIDETECH": "SUSPENSION",
        "STEERRIGHT": "STEERING", "ROADGRIP": "TYRES",
        "COMFORTSEAT": "SEATING", "CLEARVIEW": "GLASS",
        "LUMADRIVE": "LIGHTING", "CLIMATECORE": "HVAC",
        "VOLTEDGE": "BATTERY", "FASTENPRO": "FASTENERS",
        "TRIMFORM": "PLASTIC_TRIM", "SEALFLEX": "RUBBER_SEALS",
        "BONDTECH": "ADHESIVES", "AUTOFLUID": "FLUIDS",
        "CLEANFLOW": "EXHAUST", "DRIVECORE": "DRIVETRAIN_COMPONENTS",
    }
    for token, category in mapping.items():
        if token in name:
            return category
    return "GENERAL"


def generate_service_events(
    deliveries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    if generation is None:
        generation = load_generation_config()
    _validate_inputs(deliveries)
    generation_end = _get_generation_end(generation)
    base_seed = int(generation["seed"])
    rng = make_rng(derive_seed(base_seed, "auto.service"))
    provenance = generation.get("provenance", {})
    data_origin = str(provenance.get("data_origin", "SYNTHETIC"))
    generator_version = str(generation.get("generator_version", "1.0.0"))
    delivered = deliveries[deliveries["delivery_status"] == "DELIVERED"].copy()
    delivered["actual_delivery_date"] = pd.to_datetime(delivered["actual_delivery_date"])
    rows: list[dict[str, Any]] = []
    service_counter = 1
    for delivery in delivered.itertuples(index=False):
        delivery_date = pd.Timestamp(delivery.actual_delivery_date)
        exposure_days = max(0.0, (generation_end - delivery_date).total_seconds() / 86400.0)
        if exposure_days <= 0:
            continue
        daily_km = float(rng.uniform(MIN_DAILY_KM, MAX_DAILY_KM))
        production_quality = float(delivery.production_quality_score)
        supplier_quality = float(delivery.supplier_lot_quality_score)
        component_category = _infer_component_category(delivery.primary_supplier_name)
        if exposure_days >= MIN_FIRST_INSPECTION_DAYS:
            attended = bool(float(rng.random()) < FIRST_INSPECTION_ATTENDANCE_PROBABILITY)
            if attended:
                maximum_day = min(MAX_FIRST_INSPECTION_DAYS, exposure_days)
                first_day = float(rng.uniform(MIN_FIRST_INSPECTION_DAYS, maximum_day))
                service_date = delivery_date + timedelta(days=first_day)
                if service_date < generation_end:
                    event = _build_service_event(
                        service_counter=service_counter, delivery=delivery,
                        service_type="FIRST_INSPECTION", service_date=service_date,
                        delivery_date=delivery_date, daily_km=daily_km, rng=rng,
                        component_category=component_category, issue_category=None,
                        severity="NONE",
                    )
                    if event["service_completed_at"] <= generation_end:
                        event["data_origin"] = data_origin
                        event["generator_version"] = generator_version
                        rows.append(event)
                        service_counter += 1
        issue_probability = _calculate_issue_probability(
            production_quality, supplier_quality, exposure_days
        )
        issue_occurs = bool(float(rng.random()) < issue_probability)
        if issue_occurs:
            maximum_issue_day = max(4.0, min(exposure_days, MAX_ISSUE_EXPOSURE_DAYS))
            if maximum_issue_day > 3.0:
                issue_day = float(rng.uniform(3.0, maximum_issue_day))
                service_date = delivery_date + timedelta(days=issue_day)
                if service_date < generation_end:
                    issue_category = _choose_issue_category(rng, component_category)
                    severity = _derive_issue_severity(rng, production_quality, supplier_quality)
                    event = _build_service_event(
                        service_counter=service_counter, delivery=delivery,
                        service_type="UNSCHEDULED_REPAIR", service_date=service_date,
                        delivery_date=delivery_date, daily_km=daily_km, rng=rng,
                        component_category=component_category, issue_category=issue_category,
                        severity=severity,
                    )
                    if event["service_completed_at"] <= generation_end:
                        event["data_origin"] = data_origin
                        event["generator_version"] = generator_version
                        rows.append(event)
                        service_counter += 1
    service_events = pd.DataFrame(rows, columns=SERVICE_COLUMNS)
    validate_service_events(service_events, deliveries, generation_end)
    return service_events


def _choose_accident_severity(rng: np.random.Generator) -> str:
    severities = list(ACCIDENT_SEVERITY_WEIGHTS.keys())
    weights = list(ACCIDENT_SEVERITY_WEIGHTS.values())
    return str(rng.choice(severities, p=weights))


def _generate_accident_impact_g_force(rng: np.random.Generator, severity: str) -> float:
    low, high = ACCIDENT_IMPACT_G_FORCE_RANGE_BY_SEVERITY[severity]
    return round(float(rng.uniform(low, high)), 3)


def generate_accident_service_events(
    deliveries: pd.DataFrame,
    service_events: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Append a small set of accident/collision-caused service events -
    independent of, and generated after, the ordinary defect-driven
    events in generate_service_events, so adding this feature does not
    shift the random sequence (and therefore the resulting rows) for any
    already-existing non-accident service event.

    Each accident event is tagged is_accident_caused=True and forced to
    warranty_candidate=False, so warranty.py's existing claim-candidate
    filter automatically excludes it without needing any change there -
    these events are meant to be picked up by a separate insurance-claim
    generator instead (see data/generators/auto/insurance.py).
    """
    if generation is None:
        generation = load_generation_config()
    _validate_inputs(deliveries)
    if service_events.empty:
        raise ValueError("service_events cannot be empty - generate ordinary service events first")
    generation_end = _get_generation_end(generation)
    base_seed = int(generation["seed"])
    rng = make_rng(derive_seed(base_seed, "auto.service.accidents"))
    provenance = generation.get("provenance", {})
    data_origin = str(provenance.get("data_origin", "SYNTHETIC"))
    generator_version = str(generation.get("generator_version", "1.0.0"))

    service_ids = service_events["service_event_id"].astype(str)
    numeric_ids = pd.to_numeric(service_ids.str.extract(r"_(\d+)$", expand=False), errors="coerce")
    service_counter = int(numeric_ids.max()) + 1

    delivered = deliveries[deliveries["delivery_status"] == "DELIVERED"].copy()
    delivered["actual_delivery_date"] = pd.to_datetime(delivered["actual_delivery_date"])

    new_rows: list[dict[str, Any]] = []
    for delivery in delivered.itertuples(index=False):
        delivery_date = pd.Timestamp(delivery.actual_delivery_date)
        exposure_days = max(0.0, (generation_end - delivery_date).total_seconds() / 86400.0)
        if exposure_days <= 0:
            continue
        accident_probability = float(
            np.clip(ACCIDENT_ANNUAL_PROBABILITY * (exposure_days / 365.0), 0.0, 1.0)
        )
        if float(rng.random()) >= accident_probability:
            continue
        daily_km = float(rng.uniform(MIN_DAILY_KM, MAX_DAILY_KM))
        accident_day = float(rng.uniform(0.0, exposure_days))
        service_date = delivery_date + timedelta(days=accident_day)
        if service_date >= generation_end:
            continue
        severity = _choose_accident_severity(rng)
        impact_g_force = _generate_accident_impact_g_force(rng, severity)
        component_category = str(rng.choice(ACCIDENT_COMPONENT_CATEGORIES))
        event = _build_service_event(
            service_counter=service_counter, delivery=delivery,
            service_type="UNSCHEDULED_REPAIR", service_date=service_date,
            delivery_date=delivery_date, daily_km=daily_km, rng=rng,
            component_category=component_category, issue_category=ACCIDENT_ISSUE_CATEGORY,
            severity=severity, is_accident_caused=True,
            accident_impact_g_force=impact_g_force, warranty_candidate_override=False,
        )
        if event["service_completed_at"] > generation_end:
            continue
        event["data_origin"] = data_origin
        event["generator_version"] = generator_version
        new_rows.append(event)
        service_counter += 1

    if not new_rows:
        return service_events.copy()

    enriched = pd.concat(
        [service_events, pd.DataFrame(new_rows, columns=service_events.columns)],
        ignore_index=True,
    )
    enriched["service_started_at"] = pd.to_datetime(enriched["service_started_at"])
    enriched["service_completed_at"] = pd.to_datetime(enriched["service_completed_at"])
    validate_service_events(enriched, deliveries, generation_end)
    return enriched


MAX_TELEMATICS_LINKED_ACCIDENTS_DEFAULT = 3
TELEMATICS_WINDOW_EDGE_BUFFER_MINUTES = 30


def generate_telematics_linked_accident_events(
    deliveries: pd.DataFrame,
    service_events: pd.DataFrame,
    telematics_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    max_events: int = MAX_TELEMATICS_LINKED_ACCIDENTS_DEFAULT,
) -> pd.DataFrame:
    """
    Add a small, deterministic set of accident events whose timing falls
    strictly inside a vehicle's *existing* telematics coverage window -
    unlike generate_accident_service_events (which samples a timing
    across a vehicle's whole life, matching real accident risk, and is
    not constrained to line up with the small 24-vehicle telematics
    cohort's 7-day windows) this is deliberately small and targeted, so
    the resulting accident actually has a matching telematics moment to
    inject a genuine collision signature into (see
    data/generators/causal/vehicle_telematics_timeseries.py's
    inject_accident_evidence). Mirrors the existing
    generate_telemetry_evidence_service_events's max_repairs-style cap -
    a deliberately small, capped, deterministic set, not a probability
    draw over the whole fleet.
    """
    if generation is None:
        generation = load_generation_config()
    _validate_inputs(deliveries)
    if max_events < 0:
        raise ValueError("max_events must be >= 0")
    if service_events.empty or telematics_timeseries.empty or max_events == 0:
        return service_events.copy()

    generation_end = _get_generation_end(generation)
    base_seed = int(generation["seed"])
    rng = make_rng(derive_seed(base_seed, "auto.service.telematics_linked_accidents"))
    provenance = generation.get("provenance", {})
    data_origin = str(provenance.get("data_origin", "SYNTHETIC"))
    generator_version = str(generation.get("generator_version", "1.0.0"))

    telemetry = telematics_timeseries[["vehicle_id", "timestamp"]].copy()
    telemetry["timestamp"] = pd.to_datetime(telemetry["timestamp"])
    windows = telemetry.groupby("vehicle_id")["timestamp"].agg(["min", "max"])
    eligible_vehicle_ids = sorted(str(v) for v in windows.index)[:max_events]

    delivered = deliveries[deliveries["delivery_status"] == "DELIVERED"].copy()
    delivered["actual_delivery_date"] = pd.to_datetime(delivered["actual_delivery_date"])
    delivery_by_vehicle = {row.vehicle_id: row for row in delivered.itertuples(index=False)}

    service_ids = service_events["service_event_id"].astype(str)
    numeric_ids = pd.to_numeric(service_ids.str.extract(r"_(\d+)$", expand=False), errors="coerce")
    service_counter = int(numeric_ids.max()) + 1

    new_rows: list[dict[str, Any]] = []
    for vehicle_id in eligible_vehicle_ids:
        delivery = delivery_by_vehicle.get(vehicle_id)
        if delivery is None:
            continue
        window_start = pd.Timestamp(windows.loc[vehicle_id, "min"]) + timedelta(minutes=TELEMATICS_WINDOW_EDGE_BUFFER_MINUTES)
        window_end = pd.Timestamp(windows.loc[vehicle_id, "max"]) - timedelta(minutes=TELEMATICS_WINDOW_EDGE_BUFFER_MINUTES)
        if window_end <= window_start:
            continue
        delivery_date = pd.Timestamp(delivery.actual_delivery_date)
        span_minutes = (window_end - window_start).total_seconds() / 60.0
        service_date = window_start + timedelta(minutes=float(rng.uniform(0.0, span_minutes)))
        if service_date >= generation_end:
            continue
        daily_km = float(rng.uniform(MIN_DAILY_KM, MAX_DAILY_KM))
        severity = _choose_accident_severity(rng)
        impact_g_force = _generate_accident_impact_g_force(rng, severity)
        component_category = str(rng.choice(ACCIDENT_COMPONENT_CATEGORIES))
        event = _build_service_event(
            service_counter=service_counter, delivery=delivery,
            service_type="UNSCHEDULED_REPAIR", service_date=service_date,
            delivery_date=delivery_date, daily_km=daily_km, rng=rng,
            component_category=component_category, issue_category=ACCIDENT_ISSUE_CATEGORY,
            severity=severity, is_accident_caused=True,
            accident_impact_g_force=impact_g_force, warranty_candidate_override=False,
        )
        if event["service_completed_at"] > generation_end:
            continue
        event["data_origin"] = data_origin
        event["generator_version"] = generator_version
        new_rows.append(event)
        service_counter += 1

    if not new_rows:
        return service_events.copy()

    # The accident "moment" used for telematics injection downstream is
    # exactly service_started_at for these rows - the sampled timestamp
    # was already chosen to fall inside the vehicle's telematics window.
    new_frame = pd.DataFrame(new_rows, columns=service_events.columns)
    enriched = pd.concat([service_events, new_frame], ignore_index=True)
    enriched["service_started_at"] = pd.to_datetime(enriched["service_started_at"])
    enriched["service_completed_at"] = pd.to_datetime(enriched["service_completed_at"])
    validate_service_events(enriched, deliveries, generation_end)
    return enriched


def generate_telemetry_evidence_service_events(
    deliveries: pd.DataFrame,
    service_events: pd.DataFrame,
    telemetry_timeseries: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Add a small deterministic set of warning/DTC-backed repair events."""
    if generation is None:
        generation = load_generation_config()
    _validate_inputs(deliveries)
    required = {"vehicle_id", "timestamp", "warning_flag", "dtc_count"}
    missing = required.difference(telemetry_timeseries.columns)
    if missing:
        raise ValueError("Telemetry DataFrame is missing: " + ", ".join(sorted(missing)))
    if service_events.empty or telemetry_timeseries.empty:
        return service_events.copy()
    generation_end = _get_generation_end(generation)
    base_seed = int(generation["seed"])
    max_repairs = int(generation.get("auto", {}).get("telemetry_evidence_repair_max", 3))
    if max_repairs < 0:
        raise ValueError("auto.telemetry_evidence_repair_max must be >= 0")
    telemetry = telemetry_timeseries[["vehicle_id", "timestamp", "warning_flag", "dtc_count"]].copy()
    telemetry["timestamp"] = pd.to_datetime(telemetry["timestamp"])
    warning = telemetry["warning_flag"].astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})
    dtc = pd.to_numeric(telemetry["dtc_count"], errors="coerce").fillna(0).gt(0)
    evidence = telemetry.loc[warning | dtc]
    if evidence.empty:
        return service_events.copy()
    first_evidence = evidence.groupby("vehicle_id")["timestamp"].min().to_dict()
    service_started = pd.to_datetime(service_events["service_started_at"])
    first_service = service_events.assign(_started=service_started).groupby("vehicle_id")["_started"].min().to_dict()
    eligible = [v for v, at in first_evidence.items() if v in first_service and first_service[v] > at]
    eligible.sort(key=lambda v: (first_evidence[v], str(v)))
    eligible = eligible[:max_repairs]
    delivered = deliveries[deliveries["delivery_status"] == "DELIVERED"].copy()
    delivered["actual_delivery_date"] = pd.to_datetime(delivered["actual_delivery_date"])
    delivery_by_vehicle = {row.vehicle_id: row for row in delivered.itertuples(index=False)}
    service_ids = service_events["service_event_id"].astype(str)
    numeric_ids = pd.to_numeric(service_ids.str.extract(r"_(\d+)$", expand=False), errors="coerce")
    service_counter = int(numeric_ids.max()) + 1
    provenance = generation.get("provenance", {})
    data_origin = str(provenance.get("data_origin", "SYNTHETIC"))
    generator_version = str(generation.get("generator_version", "1.0.0"))
    new_rows=[]
    for vehicle_id in eligible:
        delivery=delivery_by_vehicle.get(vehicle_id)
        if delivery is None:
            continue
        service_at=max(pd.Timestamp(first_evidence[vehicle_id])+timedelta(days=1), pd.Timestamp(delivery.actual_delivery_date)+timedelta(days=3))
        if service_at >= generation_end:
            continue
        local_rng=make_rng(derive_seed(base_seed, f"auto.service.telemetry_evidence.{vehicle_id}"))
        daily_km=float(local_rng.uniform(MIN_DAILY_KM, MAX_DAILY_KM))
        component=_infer_component_category(delivery.primary_supplier_name)
        issue=_choose_issue_category(local_rng, component)
        severity=_derive_issue_severity(local_rng, float(delivery.production_quality_score), float(delivery.supplier_lot_quality_score))
        event=_build_service_event(service_counter=service_counter, delivery=delivery, service_type="UNSCHEDULED_REPAIR", service_date=service_at, delivery_date=pd.Timestamp(delivery.actual_delivery_date), daily_km=daily_km, rng=local_rng, component_category=component, issue_category=issue, severity=severity)
        if event["service_completed_at"] > generation_end:
            continue
        event["data_origin"]=data_origin; event["generator_version"]=generator_version; new_rows.append(event); service_counter += 1
    if not new_rows:
        return service_events.copy()
    enriched=pd.concat([service_events, pd.DataFrame(new_rows, columns=service_events.columns)], ignore_index=True)
    enriched["service_started_at"]=pd.to_datetime(enriched["service_started_at"]); enriched["service_completed_at"]=pd.to_datetime(enriched["service_completed_at"])
    validate_service_events(enriched, deliveries, generation_end)
    return enriched


def validate_service_events(
    service_events: pd.DataFrame,
    deliveries: pd.DataFrame,
    generation_end: pd.Timestamp,
) -> None:
    missing=set(SERVICE_COLUMNS).difference(service_events.columns)
    if missing:
        raise ValueError("Service-events DataFrame is missing required columns: " + ", ".join(sorted(missing)))
    if service_events.empty:
        return
    if service_events["service_event_id"].duplicated().any():
        raise ValueError("Duplicate service_event_id values found")
    if not service_events["service_type"].isin(VALID_SERVICE_TYPES).all():
        raise ValueError("Invalid service_type in service events")
    if not service_events["service_status"].isin(VALID_SERVICE_STATUSES).all():
        raise ValueError("Invalid service_status in service events")
    if not service_events["severity"].isin(VALID_SEVERITIES).all():
        raise ValueError("Invalid service severity in service events")
    started=pd.to_datetime(service_events["service_started_at"]); completed=pd.to_datetime(service_events["service_completed_at"])
    if (completed < started).any() or (completed > generation_end).any():
        raise ValueError("Service completion chronology is invalid")
    delivery_dates=deliveries.set_index("delivery_id")["actual_delivery_date"].copy(); delivery_dates=pd.to_datetime(delivery_dates)
    joined=service_events["delivery_id"].map(delivery_dates)
    if joined.isna().any() or (started < joined).any():
        raise ValueError("Service occurs before delivery or references unknown delivery")
    repairs=service_events["service_type"].eq("UNSCHEDULED_REPAIR")
    if service_events.loc[repairs, "issue_category"].isna().any():
        raise ValueError("Unscheduled repairs require issue_category")
    routines=service_events["service_type"].eq("FIRST_INSPECTION")
    if service_events.loc[routines, "issue_category"].notna().any():
        raise ValueError("First inspections must not have issue_category")
    if not service_events["is_accident_caused"].isin([True, False]).all():
        raise ValueError("is_accident_caused must be boolean")
    if (pd.to_numeric(service_events["accident_impact_g_force"]) < 0).any():
        raise ValueError("accident_impact_g_force cannot be negative")
    accidents = service_events["is_accident_caused"].astype(bool)
    if service_events.loc[accidents, "warranty_candidate"].astype(bool).any():
        raise ValueError("Accident-caused service events must never be warranty candidates")
    if (service_events.loc[accidents, "issue_category"] != ACCIDENT_ISSUE_CATEGORY).any():
        raise ValueError(f"Accident-caused service events must have issue_category={ACCIDENT_ISSUE_CATEGORY!r}")
    if (service_events.loc[~accidents, "accident_impact_g_force"] != 0.0).any():
        raise ValueError("Non-accident service events must have accident_impact_g_force == 0.0")


# Compatibility entry point retained for older ground-truth modules.
def generate_service_master(*args: Any, **kwargs: Any) -> pd.DataFrame:
    deliveries = kwargs.get("deliveries")
    if deliveries is None and args:
        deliveries = args[0]
    if deliveries is None:
        raise TypeError("generate_service_master requires deliveries")
    return generate_service_events(deliveries=deliveries, generation=kwargs.get("generation"))
