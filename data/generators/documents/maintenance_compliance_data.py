"""
Synthetic data for Document #5 (docs/data_required_for_warranty_predictive_model.md
section 6.5): Maintenance/Service Compliance.

Grounded directly in data/generators/auto/service.py's real constants,
not invented: this project's synthetic service_events data currently
models exactly one scheduled maintenance checkpoint (FIRST_INSPECTION,
occurring 20-45 days after delivery) plus UNSCHEDULED_REPAIR events -
not the full multi-visit free/paid service schedule the real Mahindra
Thar PDF shows (5k/10k/20k/.../100k km). This document describes the
single checkpoint the data actually supports, and says so explicitly,
rather than inventing a fuller schedule the underlying data can't back
up. A production system would need service.py extended with more
service_type values before a fuller schedule could be made real.
"""

from __future__ import annotations

# Mirrors data/generators/auto/service.py's real constants exactly -
# keep these in sync if that module's numbers ever change.
FIRST_INSPECTION_MIN_DAYS = 20
FIRST_INSPECTION_MAX_DAYS = 45
FIRST_INSPECTION_REAL_ATTENDANCE_RATE = 0.78  # from FIRST_INSPECTION_ATTENDANCE_PROBABILITY

CRITICAL_SERVICE_ITEMS: tuple[str, ...] = (
    "Engine oil and oil filter",
    "Brake fluid and clutch fluid - level and leak check",
    "Coolant - level and leak check",
    "Battery electrolyte level and specific gravity (12V starter battery)",
    "All lights, horns, wipers and washers",
    "Tyre pressure and rotation",
    "Front suspension bolt torque",
    "Wheel alignment (if abnormal conditions noticed)",
)
