"""
Master-data + calibration bootstrap for the live mobility-timeseries
pipeline.

Reuses the existing, unmodified Synthetic Data Factory geography generator
(data/generators/master/geography.py) to get the canonical region roster -
the same 4 regions (REG_EAST, REG_NORTH, REG_SOUTH, REG_WEST) already used
by data/generators/causal/mobility_timeseries.py and already present in the
mobility_timeseries database table. This module does NOT modify anything
under Mahindra AI Nexus/data/ - it only imports and calls the already
existing generator function, the same reuse pattern already used by
Vechicle_Telematics/telematics_master_data.py.

The region roster does not change minute to minute in real operations, so
it is built once per process start and reused for every live tick, exactly
like the manufacturing machine pool and telematics vehicle pool.

Also builds a per-region CALIBRATION profile: a per-minute event rate for
every count metric, an average rupee value per booking/warranty-claim, and
a (mean, std) pair for every "average_*" business metric. These were
measured directly against the real mobility_timeseries database table
(172,800 historical rows, 4 regions x 1 twelve-hour-rolling-window
observation per minute, spanning 2026-07-02 to 2026-07-31) on 2026-09-03,
using:

    SELECT region_id, avg(<column>), stddev(<column>) ...
    FROM mobility_timeseries GROUP BY region_id

`live_mobility_generator.py` samples around these real, region-specific
numbers rather than guessed ones, so the live feed's business volume and
mix stays consistent with this dataset's own real history.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

NEXUS_ROOT = Path(__file__).resolve().parents[2]

if str(NEXUS_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXUS_ROOT))

from data.generators.master.geography import generate_geography


# ---------------------------------------------------------------------
# Region calibration - see module docstring for how these were measured.
#
# count_avg[column]: the real average value of that trailing-12h ROLLING
#     COUNT column across the historical dataset. Dividing by
#     ROLLING_STEPS (720 minutes) in live_mobility_generator.py recovers
#     the average number of NEW events per minute needed to keep that
#     rolling count at its real, observed average level.
# sum_avg[column]: the real average value of that trailing-12h ROLLING
#     SUM column (booking_value_inr, warranty_claim_amount_inr).
# mean_stats[column]: (mean, std) of that "average_*" column itself, taken
#     directly - these columns already ARE averages, not sums, so they are
#     sampled directly rather than divided by the window length.
# ---------------------------------------------------------------------

REGION_CALIBRATION: dict[str, dict[str, Any]] = {
    "REG_EAST": {
        "count_avg": {
            "lead_count": 4.9984,
            "followup_count": 7.8706,
            "followup_completed_count": 6.0672,
            "customer_response_count": 4.0246,
            "test_drive_requested_count": 2.5353,
            "test_drive_completed_count": 1.8123,
            "test_drive_no_show_count": 0.1859,
            "booking_count": 0.7916,
            "finance_application_count": 0.4694,
            "finance_approved_count": 0.2553,
            "finance_rejected_count": 0.0055,
            "finance_manual_review_count": 0.1781,
            "cancellation_count": 0.4833,
            "allocated_vehicle_count": 0.7006,
            "waitlisted_booking_count": 0.0000,
            "delivered_vehicle_count": 0.6203,
            "delayed_delivery_count": 0.1703,
            "service_event_count": 0.8560,
            "unscheduled_repair_count": 0.0833,
            "warranty_claim_count": 0.0667,
            "warranty_approved_count": 0.0500,
        },
        "sum_avg": {
            "booking_value_inr": 41972.7610,
            "warranty_claim_amount_inr": 1742.8185,
        },
        "mean_stats": {
            "avg_lead_engagement_score": (0.5977, 0.1555),
            "avg_followup_response_minutes": (101.9194, 41.9637),
            "avg_finance_approval_tat_hours": (6.5166, 10.4083),
            "avg_allocation_wait_hours": (8.4634, 11.4484),
            "avg_delivery_delay_days": (0.5208, 1.3413),
        },
    },
    "REG_NORTH": {
        "count_avg": {
            "lead_count": 5.4432,
            "followup_count": 8.8027,
            "followup_completed_count": 7.1655,
            "customer_response_count": 4.5696,
            "test_drive_requested_count": 2.9746,
            "test_drive_completed_count": 2.1489,
            "test_drive_no_show_count": 0.3112,
            "booking_count": 0.7736,
            "finance_application_count": 0.5870,
            "finance_approved_count": 0.3605,
            "finance_rejected_count": 0.0500,
            "finance_manual_review_count": 0.1167,
            "cancellation_count": 0.1515,
            "allocated_vehicle_count": 0.5316,
            "waitlisted_booking_count": 0.1307,
            "delivered_vehicle_count": 0.5213,
            "delayed_delivery_count": 0.3849,
            "service_event_count": 1.0662,
            "unscheduled_repair_count": 0.0833,
            "warranty_claim_count": 0.0500,
            "warranty_approved_count": 0.0333,
        },
        "sum_avg": {
            "booking_value_inr": 37783.8425,
            "warranty_claim_amount_inr": 1763.1970,
        },
        "mean_stats": {
            "avg_lead_engagement_score": (0.5798, 0.1234),
            "avg_followup_response_minutes": (95.7111, 36.3047),
            "avg_finance_approval_tat_hours": (4.4071, 7.3514),
            "avg_allocation_wait_hours": (10.7506, 14.1152),
            "avg_delivery_delay_days": (1.7390, 2.8842),
        },
    },
    "REG_SOUTH": {
        "count_avg": {
            "lead_count": 5.2015,
            "followup_count": 8.1441,
            "followup_completed_count": 6.5066,
            "customer_response_count": 4.4834,
            "test_drive_requested_count": 2.6393,
            "test_drive_completed_count": 1.8897,
            "test_drive_no_show_count": 0.3699,
            "booking_count": 0.6234,
            "finance_application_count": 0.3802,
            "finance_approved_count": 0.3112,
            "finance_rejected_count": 0.0167,
            "finance_manual_review_count": 0.0333,
            "cancellation_count": 0.1179,
            "allocated_vehicle_count": 0.5183,
            "waitlisted_booking_count": 0.0577,
            "delivered_vehicle_count": 0.6858,
            "delayed_delivery_count": 0.5207,
            "service_event_count": 1.1507,
            "unscheduled_repair_count": 0.2000,
            "warranty_claim_count": 0.0833,
            "warranty_approved_count": 0.0667,
        },
        "sum_avg": {
            "booking_value_inr": 35360.4951,
            "warranty_claim_amount_inr": 2504.3428,
        },
        "mean_stats": {
            "avg_lead_engagement_score": (0.5802, 0.1328),
            "avg_followup_response_minutes": (104.3989, 34.8489),
            "avg_finance_approval_tat_hours": (3.4787, 6.0811),
            "avg_allocation_wait_hours": (10.1643, 13.8989),
            "avg_delivery_delay_days": (1.8739, 2.5969),
        },
    },
    "REG_WEST": {
        "count_avg": {
            "lead_count": 8.1948,
            "followup_count": 13.6530,
            "followup_completed_count": 10.3396,
            "customer_response_count": 6.7938,
            "test_drive_requested_count": 4.2288,
            "test_drive_completed_count": 3.1666,
            "test_drive_no_show_count": 0.3245,
            "booking_count": 1.4012,
            "finance_application_count": 0.9257,
            "finance_approved_count": 0.5625,
            "finance_rejected_count": 0.0167,
            "finance_manual_review_count": 0.2776,
            "cancellation_count": 0.4090,
            "allocated_vehicle_count": 1.2674,
            "waitlisted_booking_count": 0.0000,
            "delivered_vehicle_count": 1.1531,
            "delayed_delivery_count": 0.8415,
            "service_event_count": 0.9252,
            "unscheduled_repair_count": 0.0500,
            "warranty_claim_count": 0.0333,
            "warranty_approved_count": 0.0333,
        },
        "sum_avg": {
            "booking_value_inr": 78667.7473,
            "warranty_claim_amount_inr": 881.0608,
        },
        "mean_stats": {
            "avg_lead_engagement_score": (0.5925, 0.0836),
            "avg_followup_response_minutes": (104.7410, 29.4388),
            "avg_finance_approval_tat_hours": (7.9218, 9.3401),
            "avg_allocation_wait_hours": (13.0697, 10.4461),
            "avg_delivery_delay_days": (2.0754, 2.5222),
        },
    },
}


def build_region_master() -> dict[str, Any]:
    """
    Returns:
        {
            "regions": DataFrame(region_id, region_name),
            "calibration": REGION_CALIBRATION,
        }
    """

    regions_df, _cities_df = generate_geography()
    regions_df = (
        regions_df[["region_id", "region_name"]]
        .astype(str)
        .sort_values("region_id")
        .reset_index(drop=True)
    )

    missing = set(regions_df["region_id"]) - set(REGION_CALIBRATION)
    if missing:
        raise ValueError(
            "No calibration profile for region(s) returned by "
            f"generate_geography(): {sorted(missing)}. Update "
            "REGION_CALIBRATION in mobility_master_data.py."
        )

    return {"regions": regions_df, "calibration": REGION_CALIBRATION}
