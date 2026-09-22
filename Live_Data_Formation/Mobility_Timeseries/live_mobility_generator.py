"""
Live, minute-by-minute mobility (regional sales/service business) row
generator.

Schema-compatible with:
    data/generators/causal/mobility_timeseries.py

This module produces exactly ONE row per region per call to
generate_tick(), instead of a whole historical batch at once - the same
relationship live_row_generator.py has to manufacturing_timeseries.py, and
live_telematics_generator.py has to vehicle_telematics_timeseries.py.

Each region's business volume is kept as persistent rolling state across
calls (a maxlen=720 rolling window of per-minute increments per metric,
matching the batch generator's own 12-hour/720-minute rolling window
exactly - see BUSINESS_WINDOW_HOURS in mobility_timeseries.py) so the live
12h "trailing window" columns move smoothly minute to minute instead of
resetting to a baseline every tick, mirroring how MachineState/VehicleState
carry sensor state forward in the other two live generators.

Important difference from the other two live generators: the batch
generator (data/generators/causal/mobility_timeseries.py) derives every KPI
deterministically by aggregating real Auto-domain event records (leads,
followups, bookings, finance applications, ...). Reproducing that entire
event pipeline live, minute by minute, is out of scope for this pipeline.
Instead, this module samples small per-minute event counts directly around
each region's REAL, measured historical per-minute rate (see
mobility_master_data.py's REGION_CALIBRATION, measured against the actual
mobility_timeseries database table), then rolls those counts up with the
same rolling-sum / rolling-mean-of-nonzero-minutes logic the batch
generator uses. The result is schema-identical to, and statistically
consistent with, the real historical dataset - not a re-simulation of the
underlying lead-to-warranty funnel.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NEXUS_ROOT = Path(__file__).resolve().parents[2]

if str(NEXUS_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXUS_ROOT))

from data.generators.causal.mobility_timeseries import (
    COUNT_COLUMNS,
    MEAN_COLUMNS,
    SUM_COLUMNS,
)
from data.generators.common.seed import derive_seed, make_rng

# 12h rolling window at 1-minute cadence - matches BUSINESS_WINDOW_HOURS in
# the batch generator exactly.
ROLLING_STEPS = 12 * 60

# Which count column each SUM_COLUMN's per-minute rupee amount is tied to:
# one new booking carries one booking_value_inr amount, one new warranty
# claim carries one warranty_claim_amount_inr amount.
SUM_COLUMN_EVENT_COUNT: dict[str, str] = {
    "booking_value_inr": "booking_count",
    "warranty_claim_amount_inr": "warranty_claim_count",
}

# Which count column(s) gate a MEAN_COLUMN's per-minute sample - mirrors
# the batch generator's own linkage in generate_mobility_timeseries()
# (e.g. avg_finance_approval_tat_hours is only meaningful in a minute
# where a finance decision - approved, rejected, or manual review -
# actually happened).
MEAN_COLUMN_TRIGGER_COUNTS: dict[str, tuple[str, ...]] = {
    "avg_lead_engagement_score": ("lead_count",),
    "avg_followup_response_minutes": ("customer_response_count",),
    "avg_finance_approval_tat_hours": (
        "finance_approved_count",
        "finance_rejected_count",
        "finance_manual_review_count",
    ),
    "avg_allocation_wait_hours": ("allocated_vehicle_count",),
    "avg_delivery_delay_days": ("delayed_delivery_count",),
}

# Rounding precision per MEAN_COLUMN, matching the batch generator's own
# per-column .round() calls.
MEAN_COLUMN_ROUNDING: dict[str, int] = {
    "avg_lead_engagement_score": 6,
    "avg_followup_response_minutes": 3,
    "avg_finance_approval_tat_hours": 3,
    "avg_allocation_wait_hours": 3,
    "avg_delivery_delay_days": 3,
}


class _RollingSum:
    """O(1) rolling sum over the last `maxlen` per-minute increments."""

    __slots__ = ("values", "total")

    def __init__(self, maxlen: int) -> None:
        self.values: deque[float] = deque(maxlen=maxlen)
        self.total = 0.0

    def push(self, value: float) -> float:
        if len(self.values) == self.values.maxlen:
            self.total -= self.values[0]
        self.values.append(value)
        self.total += value
        return self.total


class _RollingMeanOfNonzero:
    """
    O(1) rolling mean over only the non-zero per-minute samples in the
    last `maxlen` minutes - mirrors the batch generator's own
    `.where(column > 0.0).rolling(...).mean()` behaviour, which excludes
    minutes with no relevant event from the average rather than treating
    them as a zero observation.
    """

    __slots__ = ("values", "sum_nonzero", "count_nonzero")

    def __init__(self, maxlen: int) -> None:
        self.values: deque[float] = deque(maxlen=maxlen)
        self.sum_nonzero = 0.0
        self.count_nonzero = 0

    def push(self, value: float) -> float:
        if len(self.values) == self.values.maxlen:
            popped = self.values[0]
            if popped > 0.0:
                self.sum_nonzero -= popped
                self.count_nonzero -= 1
        self.values.append(value)
        if value > 0.0:
            self.sum_nonzero += value
            self.count_nonzero += 1
        return self.sum_nonzero / self.count_nonzero if self.count_nonzero > 0 else 0.0


class RegionState:
    """Per-region persistent rolling state carried between minute ticks."""

    __slots__ = ("rng", "calibration", "count_rollups", "sum_rollups", "mean_rollups")

    def __init__(self, rng: np.random.Generator, calibration: dict[str, Any]) -> None:
        self.rng = rng
        self.calibration = calibration
        self.count_rollups = {
            column: _RollingSum(ROLLING_STEPS) for column in COUNT_COLUMNS
        }
        self.sum_rollups = {
            column: _RollingSum(ROLLING_STEPS) for column in SUM_COLUMNS
        }
        self.mean_rollups = {
            column: _RollingMeanOfNonzero(ROLLING_STEPS) for column in MEAN_COLUMNS
        }


class LiveMobilityGenerator:
    """
    Holds per-region calibration and rolling state, and produces one
    DataFrame of new rows (one per region) per tick.
    """

    def __init__(
        self,
        regions: pd.DataFrame,
        calibration: dict[str, dict[str, Any]],
        seed: int,
        data_origin: str = "SYNTHETIC",
        generator_version: str = "1.0.0",
    ) -> None:

        self.regions = regions.set_index("region_id", drop=False)
        self.calibration = calibration
        self.base_seed = int(seed)
        self.data_origin = data_origin
        self.generator_version = generator_version

        self._states: dict[str, RegionState] = {}

    def _get_or_init_state(self, region_id: str) -> RegionState:

        state = self._states.get(region_id)
        if state is not None:
            return state

        rng = make_rng(
            derive_seed(self.base_seed, f"live.mobility_timeseries.{region_id}")
        )
        state = RegionState(rng, self.calibration[region_id])
        self._states[region_id] = state

        return state

    def generate_row(self, region_id: str, timestamp: pd.Timestamp) -> dict[str, Any]:
        """
        Generate exactly one new trailing-12h business observation for one
        region at one minute, continuing on from that region's previous
        rolling state.
        """

        state = self._get_or_init_state(region_id)
        rng = state.rng
        region = self.regions.loc[region_id]
        calibration = state.calibration

        row: dict[str, Any] = {
            "region_id": str(region_id),
            "region_name": str(region.region_name),
            "window_start": timestamp,
            "window_end": timestamp + pd.Timedelta(minutes=1),
        }

        # New event counts this minute, sampled around each metric's real
        # measured per-minute rate (avg(rolling_12h_count) / 720).
        new_counts: dict[str, int] = {}
        for column in COUNT_COLUMNS:
            rate = calibration["count_avg"].get(column, 0.0) / ROLLING_STEPS
            new_count = int(rng.poisson(rate)) if rate > 0.0 else 0
            new_counts[column] = new_count
            row[column] = int(state.count_rollups[column].push(float(new_count)))

        # Rupee-value columns: one amount per new event this minute,
        # scaled by the region's real average value per event.
        for column, event_count_column in SUM_COLUMN_EVENT_COUNT.items():
            new_events = new_counts.get(event_count_column, 0)
            new_amount = 0.0

            if new_events > 0:
                trigger_avg = calibration["count_avg"].get(event_count_column, 0.0)
                per_event_value = (
                    calibration["sum_avg"].get(column, 0.0) / trigger_avg
                    if trigger_avg > 0.0
                    else 0.0
                )
                if per_event_value > 0.0:
                    new_amount = float(
                        max(
                            0.0,
                            rng.normal(
                                per_event_value * new_events,
                                per_event_value * 0.25 * (new_events**0.5),
                            ),
                        )
                    )

            row[column] = round(state.sum_rollups[column].push(new_amount), 2)

        # "Average_*" columns: sample one instantaneous value only in a
        # minute where the relevant underlying event actually happened,
        # then roll a mean over the non-zero minutes in the trailing 12h.
        for column, trigger_columns in MEAN_COLUMN_TRIGGER_COUNTS.items():
            mean_value, std_value = calibration["mean_stats"].get(column, (0.0, 0.0))
            triggered = any(new_counts.get(c, 0) > 0 for c in trigger_columns)

            sample = 0.0
            if triggered and mean_value > 0.0:
                sample = float(rng.normal(mean_value, std_value))
                lower = 0.0 if column != "avg_lead_engagement_score" else 0.0
                upper = 1.0 if column == "avg_lead_engagement_score" else None
                sample = max(lower, sample)
                if upper is not None:
                    sample = min(upper, sample)

            row[column] = round(
                state.mean_rollups[column].push(sample),
                MEAN_COLUMN_ROUNDING.get(column, 3),
            )

        row["data_origin"] = self.data_origin
        row["generator_version"] = self.generator_version

        return row

    def generate_tick(
        self, region_ids: list, timestamp: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Generate one row per region_id for the given minute timestamp.
        """

        rows = [
            self.generate_row(region_id, timestamp) for region_id in region_ids
        ]

        return pd.DataFrame(rows)
