"""
Synthetic data for Document #4 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Driving-Behavior Exclusion Clauses.

Telematics field names below match the real columns in
data/synthetic/causal/vehicle_telematics_timeseries.csv (confirmed
directly against that file, not assumed) - this document is only useful
to the eventual claim-time forensics step (section 6.3) if it references
fields that actually exist in the telematics table.

Not every supplier_component_category has a clean, derivable telematics
signal for misuse (e.g. a seat rattle or a door-seal leak has no
telematics fingerprint). Only categories with a real, traceable signal
get a specific clause here; everything else explicitly falls back to the
general misuse/accident/continued-use exclusions already in the Master
Warranty Policy, rather than inventing a false-precision threshold for a
component that has no real telematics signature.

All specific numeric thresholds below are illustrative synthetic PoC
assumptions, not real Mahindra engineering specifications - flagged
inline everywhere they appear.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviorClause:
    category: str
    telematics_signals: tuple[str, ...]
    trigger_description: str
    illustrative_threshold: str
    exclusion_text: str


BEHAVIOR_CLAUSES: tuple[BehaviorClause, ...] = (
    BehaviorClause(
        "STEERING",
        ("steering_angle_deg", "steering_torque_nm"),
        "A sustained pattern of rapid, high-magnitude steering inputs combined with elevated steering "
        "torque, consistent with repeated curb-strikes or off-road maneuvering rather than normal on-road use.",
        "Illustrative synthetic threshold, not an engineering specification: repeated events of "
        "|steering_angle_deg| exceeding roughly 450 degrees together with steering_torque_nm exceeding the "
        "model's rated peak, occurring more than a defined number of times within a rolling 30-day window "
        "before the failure.",
        "Repairs to steering system components are not covered where the vehicle's telematics history for "
        "the period leading up to the failure shows a sustained pattern of steering inputs beyond this "
        "threshold.",
    ),
    BehaviorClause(
        "SUSPENSION",
        ("vertical_acceleration_g", "impact_g_force", "road_roughness_index", "vehicle_vibration_mm_s"),
        "Sustained high road-roughness/vibration readings, or repeated vertical-acceleration or impact-g "
        "spikes, consistent with sustained off-road or harsh-impact driving beyond normal on-road use.",
        "Illustrative synthetic threshold, not an engineering specification: road_roughness_index or "
        "vehicle_vibration_mm_s remaining above the model's rated on-road range for a sustained portion of "
        "total driving time, or repeated impact_g_force spikes beyond the model's rated limit.",
        "Repairs to suspension components are not covered where telematics data indicates sustained "
        "off-road or harsh-impact driving beyond manufacturer-specified thresholds for this model.",
    ),
    BehaviorClause(
        "DRIVETRAIN_COMPONENTS",
        ("transmission_temperature_c", "transmission_slip_ms", "torque_converter_slip_rpm"),
        "Sustained elevated transmission temperature combined with abnormal transmission or torque-converter "
        "slip, consistent with towing or carrying load beyond the vehicle's rated capacity.",
        "Illustrative synthetic threshold, not an engineering specification: transmission_temperature_c "
        "sustained above the model's rated operating range together with transmission_slip_ms or "
        "torque_converter_slip_rpm outside the model's normal operating band, for a sustained duration "
        "before the failure.",
        "Repairs to drivetrain components are not covered where telematics data indicates sustained "
        "overload conditions (towing or load beyond rated capacity) in the period leading up to the failure.",
    ),
    BehaviorClause(
        "BRAKING_SYSTEM",
        ("impact_g_force", "vehicle_speed_kph"),
        "A pattern of repeated high-impact-g events correlated with rapid vehicle-speed drop, consistent "
        "with harsh or emergency braking well beyond the frequency expected from normal use.",
        "Illustrative synthetic threshold, not an engineering specification: repeated events combining an "
        "impact_g_force spike with a rapid vehicle_speed_kph drop, occurring far more often than the "
        "model's expected normal-use baseline.",
        "Repairs necessitated by accelerated brake component wear are not covered where telematics data "
        "indicates a sustained pattern of harsh braking well beyond normal-use frequency.",
    ),
    BehaviorClause(
        "EXHAUST",
        ("impact_g_force", "road_roughness_index"),
        "Impact-g spikes consistent with underbody grounding or impact while driving over rough or "
        "unsuitable terrain.",
        "Illustrative synthetic threshold, not an engineering specification: an impact_g_force spike "
        "occurring while road_roughness_index is simultaneously elevated, consistent with an underbody "
        "strike.",
        "Repairs to exhaust system components resulting from underbody impact on unsuitable terrain, as "
        "indicated by telematics data, are not covered.",
    ),
    BehaviorClause(
        "ECU_ELECTRONICS",
        ("dtc_count", "warning_flag"),
        "The vehicle continued in normal operation for a sustained period after a relevant fault code or "
        "warning flag was raised, without being brought in for inspection - the measurable form of the "
        "Master Warranty Policy's general \"continued use despite known defect\" exclusion.",
        "Illustrative synthetic threshold, not an engineering specification: warning_flag active or "
        "dtc_count elevated for a sustained period (e.g. multiple days or a defined distance driven) before "
        "the vehicle was brought in for service.",
        "Repairs are not covered where telematics data shows the vehicle continued in normal operation for "
        "a sustained period after a relevant warning flag or fault code was active, without the vehicle "
        "being brought in for inspection.",
    ),
    BehaviorClause(
        "ELECTRICAL_WIRING",
        ("dtc_count", "warning_flag"),
        "Same evidentiary basis as ECU_ELECTRONICS above - continued operation after a relevant fault code "
        "or warning flag, without inspection.",
        "Illustrative synthetic threshold, not an engineering specification: same as ECU_ELECTRONICS above.",
        "Repairs are not covered where telematics data shows the vehicle continued in normal operation for "
        "a sustained period after a relevant warning flag or fault code was active, without the vehicle "
        "being brought in for inspection.",
    ),
    BehaviorClause(
        "BATTERY",
        ("battery_temperature_c", "battery_soc_pct", "battery_current_a"),
        "Sustained exposure to battery temperature beyond the manufacturer-specified range, or repeated "
        "deep-discharge patterns, beyond what normal use would produce. This clause is evidentiary input to "
        "the separate battery manufacturer's own warranty (see the Component-Level Coverage Schedule), not "
        "Mahindra's base/extended vehicle warranty.",
        "Illustrative synthetic threshold, not an engineering specification: battery_temperature_c sustained "
        "outside the manufacturer-specified operating range, or battery_soc_pct repeatedly driven near zero, "
        "for a sustained portion of the vehicle's usage history.",
        "Evidence of sustained battery temperature or discharge conditions beyond manufacturer-specified "
        "limits is relevant input to the battery manufacturer's own warranty adjudication for this claim.",
    ),
)

NO_BEHAVIOR_SIGNAL_CATEGORIES: tuple[str, ...] = (
    "ADHESIVES",
    "FASTENERS",
    "FLUIDS",
    "GLASS",
    "HVAC",
    "LIGHTING",
    "PLASTIC_TRIM",
    "RUBBER_SEALS",
    "SEATING",
    "STEEL_BODY_PANELS",
    "TYRES",
)
