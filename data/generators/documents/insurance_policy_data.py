"""
Real, per-vehicle insurance policy data for Documents #8 and #11
(docs/data_required_for_warranty_predictive_model.md section 6.5):
Motor Insurance Policy Certificate and Claims History/NCB Statement.

No policy master table existed anywhere in this project before this -
only claims existed (an insurance_claims row references a policy_number
string, but nothing defined what that policy actually covers: IDV,
premium, deductible, period). This module computes those real per-
vehicle values from data already in this project (each model's real
base_price in data/generators/master/vehicle_models.py, and each
vehicle's real delivery date), using the standard IRDAI-published IDV
depreciation schedule (a real, citable industry standard, not invented)
and a simplified, clearly-flagged synthetic premium/deductible model.

Scope: policies are only generated for vehicles that actually have an
insurance claim in this fleet's data (22 today) - not the full ~1,349-
vehicle fleet. This project has no "is this vehicle insured" concept at
all; generating ~1,349 certificates for a concept the rest of the data
doesn't model would overstate what exists. Claims are where insurance
is actually "activated" as a concept here, so that is the scope.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data.generators.common.helpers import SYNTHETIC_DIR
from data.generators.master.vehicle_models import VEHICLE_MODEL_METADATA

INSURANCE_CLAIMS_PATH = SYNTHETIC_DIR / "auto" / "insurance_claims.csv"
DELIVERIES_PATH = SYNTHETIC_DIR / "auto" / "deliveries.csv"

# Standard IRDAI-published IDV depreciation schedule for private cars -
# a real industry standard, not a synthetic assumption.
IDV_DEPRECIATION_SCHEDULE: tuple[tuple[float, float], ...] = (
    (0.5, 0.05),   # up to 6 months: 5%
    (1.0, 0.15),   # 6 months - 1 year: 15%
    (2.0, 0.20),   # 1 - 2 years: 20%
    (3.0, 0.30),   # 2 - 3 years: 30%
    (4.0, 0.40),   # 3 - 4 years: 40%
    (5.0, 0.50),   # 4 - 5 years: 50%
)
IDV_DEPRECIATION_BEYOND_5_YEARS = 0.50  # negotiated between insurer/insured in practice; floor used here

# Synthetic PoC assumptions - not real insurer pricing.
OWN_DAMAGE_PREMIUM_RATE = 0.028  # ~2.8% of IDV/year, a realistic comprehensive-cover ballpark
THIRD_PARTY_PREMIUM_FLAT_INR = 2_850.0  # rough single-slab approximation (real TP premium is cc-slab-based)
DEDUCTIBLE_BY_SEGMENT_INR = {
    "SUV": 2_000.0,
    "Compact SUV": 1_000.0,
}
DEDUCTIBLE_DEFAULT_INR = 1_000.0


def _idv_depreciation_rate(vehicle_age_years: float) -> float:
    for max_years, rate in IDV_DEPRECIATION_SCHEDULE:
        if vehicle_age_years <= max_years:
            return rate
    return IDV_DEPRECIATION_BEYOND_5_YEARS


@dataclass(frozen=True)
class VehiclePolicy:
    policy_number: str
    vehicle_id: str
    vehicle_model_name: str
    variant: str
    policy_start_date: pd.Timestamp
    policy_end_date: pd.Timestamp
    base_price_inr: float
    idv_inr: float
    depreciation_rate: float
    own_damage_premium_inr: float
    third_party_premium_inr: float
    total_premium_inr: float
    deductible_inr: float
    cover_type: str


def _segment_for_model(vehicle_model_name: str) -> str:
    metadata = VEHICLE_MODEL_METADATA.get(vehicle_model_name, {})
    return str(metadata.get("segment", ""))


def build_vehicle_policy(vehicle_id: str, vehicle_model_name: str, variant: str, delivery_date: pd.Timestamp, as_of: pd.Timestamp) -> VehiclePolicy:
    metadata = VEHICLE_MODEL_METADATA.get(vehicle_model_name)
    if metadata is None:
        raise KeyError(f"No vehicle model metadata for {vehicle_model_name!r}")
    base_price = float(metadata["base_price"])

    vehicle_age_years = max(0.0, (as_of - delivery_date).days / 365.25)
    depreciation_rate = _idv_depreciation_rate(vehicle_age_years)
    idv = round(base_price * (1.0 - depreciation_rate), 2)

    own_damage_premium = round(idv * OWN_DAMAGE_PREMIUM_RATE, 2)
    third_party_premium = THIRD_PARTY_PREMIUM_FLAT_INR
    total_premium = round(own_damage_premium + third_party_premium, 2)

    segment = _segment_for_model(vehicle_model_name)
    deductible = DEDUCTIBLE_BY_SEGMENT_INR.get(segment, DEDUCTIBLE_DEFAULT_INR)

    policy_start = delivery_date
    policy_end = delivery_date + pd.DateOffset(years=1)

    return VehiclePolicy(
        policy_number=f"POLICY_SYN_{vehicle_id.split('_')[-1]}",
        vehicle_id=vehicle_id,
        vehicle_model_name=vehicle_model_name,
        variant=variant,
        policy_start_date=policy_start,
        policy_end_date=policy_end,
        base_price_inr=base_price,
        idv_inr=idv,
        depreciation_rate=depreciation_rate,
        own_damage_premium_inr=own_damage_premium,
        third_party_premium_inr=third_party_premium,
        total_premium_inr=total_premium,
        deductible_inr=deductible,
        cover_type="Comprehensive",
    )


def load_insured_vehicle_policies(as_of: pd.Timestamp | None = None) -> list[tuple[VehiclePolicy, list[dict]]]:
    """
    Returns one (policy, claims) pair per insured vehicle (scope: only
    vehicles with a real insurance claim - see module docstring), where
    `claims` is that vehicle's real insurance_claims rows.
    """
    claims = pd.read_csv(INSURANCE_CLAIMS_PATH)
    deliveries = pd.read_csv(DELIVERIES_PATH)[["vehicle_id", "actual_delivery_date"]]
    deliveries["actual_delivery_date"] = pd.to_datetime(deliveries["actual_delivery_date"])

    if as_of is None:
        as_of = pd.Timestamp.now(tz=deliveries["actual_delivery_date"].dt.tz)

    merged = claims.merge(deliveries, on="vehicle_id", how="left")
    results: list[tuple[VehiclePolicy, list[dict]]] = []
    for vehicle_id, group in merged.groupby("vehicle_id"):
        first = group.iloc[0]
        policy = build_vehicle_policy(
            vehicle_id=str(vehicle_id),
            vehicle_model_name=str(first["vehicle_model_name"]),
            variant=str(first["variant"]),
            delivery_date=pd.Timestamp(first["actual_delivery_date"]),
            as_of=as_of,
        )
        vehicle_claims = group.sort_values("claim_submitted_at").to_dict("records")
        results.append((policy, vehicle_claims))

    return sorted(results, key=lambda item: item[0].vehicle_id)
