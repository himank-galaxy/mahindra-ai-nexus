"""
Data-joining helpers for Document #12 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Surveyor/Claim Investigation Report.

Reads the real, live insurance_claims/service_events/telematics data at
generation time - one report per real claim, not a template with
placeholder claim numbers. Telematics cross-reference is only included
where it genuinely exists: this fleet's telematics only covers a small
24-vehicle cohort (see boundary_guidelines.py's "A Note On Scope"), so
most claims will honestly report no telematics coverage rather than
fabricate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from data.generators.common.helpers import SYNTHETIC_DIR

INSURANCE_CLAIMS_PATH = SYNTHETIC_DIR / "auto" / "insurance_claims.csv"
SERVICE_EVENTS_PATH = SYNTHETIC_DIR / "auto" / "service_events.csv"
TELEMATICS_PATH = SYNTHETIC_DIR / "causal" / "vehicle_telematics_timeseries.csv"

TELEMATICS_WINDOW_MINUTES_BEFORE = 2
TELEMATICS_WINDOW_MINUTES_AFTER = 4


@dataclass(frozen=True)
class ClaimInvestigation:
    claim: dict
    accident_at: pd.Timestamp | None
    telematics_window: pd.DataFrame | None  # None if this vehicle has no telematics coverage at all


def load_claim_investigations() -> list[ClaimInvestigation]:
    claims = pd.read_csv(INSURANCE_CLAIMS_PATH)
    service_events = pd.read_csv(SERVICE_EVENTS_PATH)[
        ["service_event_id", "service_started_at"]
    ]
    telematics = pd.read_csv(TELEMATICS_PATH)
    telematics["timestamp"] = pd.to_datetime(telematics["timestamp"])
    telematics_vehicle_ids = set(telematics["vehicle_id"].unique())

    merged = claims.merge(service_events, on="service_event_id", how="left")

    investigations: list[ClaimInvestigation] = []
    for _, row in merged.iterrows():
        claim = row.to_dict()
        accident_at = pd.Timestamp(row["service_started_at"]) if pd.notna(row["service_started_at"]) else None

        telematics_window = None
        if accident_at is not None and claim["vehicle_id"] in telematics_vehicle_ids:
            floor_at = accident_at.floor("min")
            window_start = floor_at - timedelta(minutes=TELEMATICS_WINDOW_MINUTES_BEFORE)
            window_end = floor_at + timedelta(minutes=TELEMATICS_WINDOW_MINUTES_AFTER)
            window = telematics[
                (telematics["vehicle_id"] == claim["vehicle_id"])
                & (telematics["timestamp"] >= window_start)
                & (telematics["timestamp"] <= window_end)
            ].sort_values("timestamp")
            if not window.empty:
                telematics_window = window

        investigations.append(ClaimInvestigation(claim=claim, accident_at=accident_at, telematics_window=telematics_window))

    return investigations
