"""Warranty, Quality & Service causal early-warning evidence service.

The warning unit is an ISSUE CATEGORY, not a causal edge.

Evidence chain
--------------
Observed field issue
    ->
exact representative machine
    ->
exact production batch
    ->
exact supplier lot
    ->
manufacturing observation inside the persisted causal-run source window
    ->
stable PCMCI causal candidate supported by that machine

Important interpretation
------------------------
Exact lineage proves traceability between the field incident and manufacturing
history used by the causal run.

A stable PCMCI candidate remains statistical causal evidence. It does NOT prove
that a specific production batch, supplier lot, or machine caused a warranty
failure.

This service deliberately does NOT:

- rerun PCMCI,
- read causal ground truth,
- read scenario expectations,
- use claim_probability,
- use root_cause_domain as causal evidence,
- convert PCMCI effect scores into causal probabilities,
- manufacture AI confidence values.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, true

from app.database.runtime_schema import runtime_metadata
from app.models.manufacturing_causal_state import (
    ManufacturingCausalEdge,
    ManufacturingCausalRun,
)
from app.models.telematics_causal_state import (
    TelematicsCausalEdge,
    TelematicsCausalRun,
)
from app.services.base import BaseService

# ============================================================================
# RUNTIME TABLES
# ============================================================================

MANUFACTURING_TABLE = runtime_metadata.tables[
    "manufacturing_timeseries"
]

SERVICE_TABLE = runtime_metadata.tables[
    "service_events"
]

WARRANTY_TABLE = runtime_metadata.tables[
    "warranty_claims"
]

TELEMATICS_TABLE = runtime_metadata.tables[
    "vehicle_telematics_timeseries"
]

DELIVERIES_TABLE = runtime_metadata.tables[
    "deliveries"
]


# ============================================================================
# TYPES / CONFIGURATION
# ============================================================================

LineageKey = tuple[
    str,
    str,
    str,
]


@dataclass(frozen=True)
class WarrantyQualityWarningConfig:
    """Transparent empirical warning-calibration policy."""

    percentile_median: float = 0.50
    percentile_high: float = 0.75
    percentile_extreme: float = 0.90

    max_causal_paths: int = 6
    max_supplier_hotspots: int = 5
    max_market_hotspots: int = 5


DEFAULT_WARNING_CONFIG = (
    WarrantyQualityWarningConfig()
)

# Presentation-layer family mapping only. These families select persisted
# telematics candidates for a field issue; they are not labels used by causal
# discovery and do not introduce a hidden issue-to-signal ground truth map.
ISSUE_TELEMATICS_FAMILIES: dict[str, frozenset[str]] = {
    "TYRE_VIBRATION": frozenset(
        {
            "vehicle_vibration_mm_s",
            "vertical_acceleration_g",
            "lateral_acceleration_g",
            "road_roughness_index",
            "impact_g_force",
        }
    ),
    "ELECTRONIC_CONTROL": frozenset(
        {
            "battery_temperature_c",
            "battery_soc_pct",
            "battery_voltage_v",
            "battery_current_a",
            "battery_internal_resistance_ohm",
        }
    ),
    # There is no persisted, meaningful interior-rattle telematics family in
    # the current contract. Keep this intentionally empty rather than force
    # an unrelated signal into the warning.
    "INTERIOR_RATTLE": frozenset(),
}


# Presentation hint for the evidence graph, keyed off the LPCMCI edge
# orientation. Additive metadata only -- the frontend decides how (or
# whether) to use it; DIRECTED intentionally has no entry (solid single
# arrowhead is the implicit default, matching pre-LPCMCI behavior exactly).
_EDGE_ORIENTATION_VISUAL_STYLE: dict[str, str] = {
    "BIDIRECTED": "double_arrow",
    "PARTIALLY_ORIENTED": "dashed",
    "AMBIGUOUS": "dotted",
}


# ============================================================================
# PUBLIC RESULT CONTRACTS
# ============================================================================


@dataclass(frozen=True)
class ExactLineageEvidence:
    """Exact field-to-manufacturing lineage inside the causal-run window."""

    machine_id: str
    production_batch_id: str
    supplier_lot_id: str


@dataclass(frozen=True)
class CausalPathSupport:
    """Stable causal candidate supported on exact-lineage machines."""

    source_metric: str
    target_metric: str

    scope: str
    consensus_sign: str

    recurring_machines: int
    eligible_machines: int
    recurrence_fraction: float

    sign_agreement: float

    mean_abs_score: float
    best_q_value: float

    observed_lags: tuple[
        int,
        ...,
    ]

    overlap_machines: tuple[
        str,
        ...,
    ]

    overlap_count: int

    issue_exact_lineage_machine_fraction: float
    causal_edge_machine_fraction: float

    exact_lineage_count: int
    exact_lineage_fraction: float

    # Additive provenance and vehicle-level support fields. The original
    # manufacturing fields remain populated for manufacturing paths; telematics
    # paths use the vehicle fields and leave machine fields at zero/empty.
    edge_type: str = "CAUSAL_DISCOVERED_MANUFACTURING"
    provenance: str = "manufacturing_causal_run"
    causal_domain: str = "manufacturing"
    causal_run_id: uuid.UUID | None = None
    observed_lag_minutes: tuple[int, ...] = ()
    best_p_value: float | None = None
    min_p_value: float | None = None
    max_p_value: float | None = None
    min_q_value: float | None = None
    max_q_value: float | None = None
    median_abs_score: float | None = None
    recurring_vehicles: int = 0
    eligible_vehicles: int = 0
    supporting_vehicle_ids: tuple[str, ...] = ()
    overlap_vehicles: tuple[str, ...] = ()
    overlap_vehicle_count: int = 0
    issue_vehicle_fraction: float = 0.0
    causal_edge_vehicle_fraction: float = 0.0

    # LPCMCI edge orientation. Distinct from edge_type (a domain-provenance
    # tag) -- this is the discovered statistical relationship's shape.
    # Defaults reflect PCMCI's plain directed output.
    edge_orientation: str = "DIRECTED"
    edge_mark: str = "-->"
    mark_agreement: float = 1.0


@dataclass(frozen=True)
class EvidenceGraphNode:
    '''A real field, lineage, metric, or persisted evidence graph node.'''

    node_id: str
    node_type: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceGraphEdge:
    '''A typed evidence relation; only causal edges are labelled causal.'''

    source_node_id: str
    target_node_id: str
    edge_type: str
    provenance: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceGraph:
    '''Presentation graph joining persisted causal and observed evidence.'''

    nodes: tuple[EvidenceGraphNode, ...] = ()
    edges: tuple[EvidenceGraphEdge, ...] = ()


@dataclass(frozen=True)
class SupplierHotspot:
    """Observed warranty exposure grouped by supplier/component."""

    supplier_id: str
    supplier_name: str
    component_category: str

    claims: int
    supplier_lots: int
    batches: int

    approved_exposure_inr: float


@dataclass(frozen=True)
class MarketHotspot:
    """Observed warranty exposure grouped by model/variant/geography."""

    vehicle_model_name: str
    variant: str

    region_name: str
    city_name: str

    claims: int
    batches: int
    supplier_lots: int

    approved_exposure_inr: float


@dataclass(frozen=True)
class WarningCalibration:
    """Empirical thresholds calculated from the current field cohort."""

    issue_categories: int

    complaints_p50: float
    complaints_p75: float
    complaints_p90: float

    claims_p50: float
    claims_p75: float
    claims_p90: float

    approved_exposure_p50: float
    approved_exposure_p75: float
    approved_exposure_p90: float

    batches_p75: float
    supplier_lots_p75: float
    cities_p75: float

    evidence_score_p50: float
    evidence_score_p75: float
    evidence_score_p90: float


@dataclass(frozen=True)
class WarrantyQualityWarning:
    """One issue-category causal early-warning evidence object."""

    issue_category: str

    priority: str

    # Transparent evidence index.
    # This is NOT a probability or model confidence.
    evidence_score: int

    service_events: int
    complaints: int
    repairs: int
    warranty_candidates: int

    warranty_claims: int

    # Counted from service events only to avoid double-counting claim-linked
    # service incidents.
    service_low_events: int
    service_medium_events: int
    service_high_events: int

    affected_machines: int
    affected_vehicles: int
    affected_batches: int
    affected_supplier_lots: int
    affected_models: int
    affected_cities: int

    claim_exposure_inr: float
    approved_exposure_inr: float

    field_lineages: int
    exact_window_lineages: int
    exact_window_lineage_coverage: float

    exact_lineage_machines: int
    lineage_evidence_grade: str

    machine_ids: tuple[
        str,
        ...,
    ]

    exact_lineages: tuple[
        ExactLineageEvidence,
        ...,
    ]

    causal_paths: tuple[
        CausalPathSupport,
        ...,
    ]

    supplier_hotspots: tuple[
        SupplierHotspot,
        ...,
    ]

    market_hotspots: tuple[
        MarketHotspot,
        ...,
    ]

    service_event_ids: tuple[str, ...] = ()
    warranty_claim_ids: tuple[str, ...] = ()
    telematics_edges_considered: int = 0
    telematics_paths_selected: int = 0
    telematics_eligibility_diagnostics: dict[str, Any] = field(default_factory=dict)
    evidence_graph: EvidenceGraph = field(default_factory=EvidenceGraph)


@dataclass(frozen=True)
class WarrantyQualityEarlyWarningResult:
    """Complete early-warning result for one persisted causal run."""

    causal_run_id: uuid.UUID
    causal_signature: str

    source_from: datetime
    source_to: datetime

    generated_at: datetime

    issue_categories_evaluated: int
    issue_categories_with_exact_lineage: int

    warnings_generated: int

    calibration: WarningCalibration

    warnings: tuple[
        WarrantyQualityWarning,
        ...,
    ]

    # causal_run_id remains the backward-compatible manufacturing ID.
    manufacturing_causal_run_id: uuid.UUID | None = None
    telematics_causal_run_id: uuid.UUID | None = None
    telematics_causal_signature: str | None = None
    telematics_source_from: datetime | None = None
    telematics_source_to: datetime | None = None
    simulation_as_of: datetime | None = None


# ============================================================================
# CALIBRATION HELPERS
# ============================================================================


def _percentile_cont(
    values: list[float],
    quantile: float,
) -> float:
    """PostgreSQL-style continuous percentile for a finite numeric sample."""

    if not values:
        return 0.0

    if not (
        0.0
        <= quantile
        <= 1.0
    ):
        raise ValueError(
            "quantile must lie in [0, 1]."
        )

    ordered = sorted(
        float(value)
        for value in values
    )

    if len(ordered) == 1:
        return ordered[0]

    position = (
        len(ordered) - 1
    ) * quantile

    lower_index = math.floor(
        position
    )

    upper_index = math.ceil(
        position
    )

    if lower_index == upper_index:
        return ordered[
            lower_index
        ]

    fraction = (
        position
        - lower_index
    )

    lower = ordered[
        lower_index
    ]

    upper = ordered[
        upper_index
    ]

    return (
        lower
        + (
            upper - lower
        )
        * fraction
    )


def _empirical_tier(
    value: float,
    *,
    p75: float,
    p90: float,
) -> int:
    """Score one observed field dimension using cohort-derived cutoffs."""

    if (
        p90 > 0.0
        and value >= p90
    ):
        return 2

    if (
        p75 > 0.0
        and value >= p75
    ):
        return 1

    return 0


def _validate_config(
    config: WarrantyQualityWarningConfig,
) -> None:
    quantiles = (
        config.percentile_median,
        config.percentile_high,
        config.percentile_extreme,
    )

    if not all(
        0.0 < value <= 1.0
        for value in quantiles
    ):
        raise ValueError(
            "Warning percentiles must lie in (0, 1]."
        )

    if not (
        config.percentile_median
        <= config.percentile_high
        <= config.percentile_extreme
    ):
        raise ValueError(
            "Warning percentiles must satisfy "
            "median <= high <= extreme."
        )

    if config.max_causal_paths < 1:
        raise ValueError(
            "max_causal_paths must be at least 1."
        )

    if config.max_supplier_hotspots < 1:
        raise ValueError(
            "max_supplier_hotspots must be at least 1."
        )

    if config.max_market_hotspots < 1:
        raise ValueError(
            "max_market_hotspots must be at least 1."
        )


def _zero_calibration() -> WarningCalibration:
    return WarningCalibration(
        issue_categories=0,

        complaints_p50=0.0,
        complaints_p75=0.0,
        complaints_p90=0.0,

        claims_p50=0.0,
        claims_p75=0.0,
        claims_p90=0.0,

        approved_exposure_p50=0.0,
        approved_exposure_p75=0.0,
        approved_exposure_p90=0.0,

        batches_p75=0.0,
        supplier_lots_p75=0.0,
        cities_p75=0.0,

        evidence_score_p50=0.0,
        evidence_score_p75=0.0,
        evidence_score_p90=0.0,
    )


# ============================================================================
# LINEAGE HELPERS
# ============================================================================


def _lineage_key(
    machine_id: Any,
    production_batch_id: Any,
    supplier_lot_id: Any,
) -> LineageKey:
    return (
        str(machine_id),
        str(production_batch_id),
        str(supplier_lot_id),
    )


def _lineage_evidence(
    lineages: set[
        LineageKey
    ],
) -> tuple[
    ExactLineageEvidence,
    ...,
]:
    return tuple(
        ExactLineageEvidence(
            machine_id=machine_id,
            production_batch_id=production_batch_id,
            supplier_lot_id=supplier_lot_id,
        )
        for (
            machine_id,
            production_batch_id,
            supplier_lot_id,
        )
        in sorted(
            lineages
        )
    )


def _lineage_grade(
    field_lineages: int,
    exact_window_lineages: int,
) -> str:
    if field_lineages <= 0:
        return "NO_FIELD_LINEAGE"

    if exact_window_lineages <= 0:
        return "NO_EXACT_WINDOW_LINEAGE"

    if exact_window_lineages == field_lineages:
        return "EXACT_WINDOW_LINEAGE"

    return "PARTIAL_EXACT_WINDOW_LINEAGE"


# ============================================================================
# INTERNAL ISSUE ACCUMULATOR
# ============================================================================


def _new_issue() -> dict[
    str,
    Any,
]:
    return {
        "service_events": 0,
        "complaints": 0,
        "repairs": 0,
        "warranty_candidates": 0,

        "service_low_events": 0,
        "service_medium_events": 0,
        "service_high_events": 0,

        "warranty_claims": 0,

        "claim_exposure_inr": 0.0,
        "approved_exposure_inr": 0.0,

        "machine_ids": set(),
        "vehicle_ids": set(),
        "service_event_ids": set(),
        "warranty_claim_ids": set(),
        "field_lineage_vehicle_keys": set(),
        "service_event_vehicle_ids": defaultdict(set),
        "warranty_claim_vehicle_ids": defaultdict(set),
        "warranty_claim_service_event_ids": defaultdict(set),
        "batch_ids": set(),
        "supplier_lot_ids": set(),
        "model_ids": set(),
        "city_ids": set(),

        "field_lineages": set(),
        "exact_window_lineages": set(),

        "supplier_groups": defaultdict(
            lambda: {
                "claim_ids": set(),
                "supplier_lot_ids": set(),
                "batch_ids": set(),
                "approved_exposure_inr": 0.0,
            }
        ),

        "market_groups": defaultdict(
            lambda: {
                "claim_ids": set(),
                "batch_ids": set(),
                "supplier_lot_ids": set(),
                "approved_exposure_inr": 0.0,
            }
        ),
    }


def _service_severity_bucket(
    issue: dict[
        str,
        Any,
    ],
    severity: Any,
) -> None:
    """Count service severity exactly once per service event."""

    value = str(
        severity
        or ""
    ).strip().upper()

    if value == "HIGH":
        issue[
            "service_high_events"
        ] += 1

    elif value == "MEDIUM":
        issue[
            "service_medium_events"
        ] += 1

    else:
        issue[
            "service_low_events"
        ] += 1


def _add_common_field_dimensions(
    issue: dict[
        str,
        Any,
    ],
    *,
    machine_id: Any,
    vehicle_id: Any,
    production_batch_id: Any,
    supplier_lot_id: Any,
    vehicle_model_id: Any,
    city_id: Any,
) -> None:
    machine_id_value = str(
        machine_id
    )

    batch_id_value = str(
        production_batch_id
    )

    supplier_lot_value = str(
        supplier_lot_id
    )

    issue[
        "machine_ids"
    ].add(
        machine_id_value
    )

    issue[
        "vehicle_ids"
    ].add(
        str(
            vehicle_id
        )
    )

    issue[
        "batch_ids"
    ].add(
        batch_id_value
    )

    issue[
        "supplier_lot_ids"
    ].add(
        supplier_lot_value
    )

    issue[
        "model_ids"
    ].add(
        str(
            vehicle_model_id
        )
    )

    issue[
        "city_ids"
    ].add(
        str(
            city_id
        )
    )

    issue[
        "field_lineages"
    ].add(
        (
            machine_id_value,
            batch_id_value,
            supplier_lot_value,
        )
    )

    issue[
        "field_lineage_vehicle_keys"
    ].add(
        (
            machine_id_value,
            batch_id_value,
            supplier_lot_value,
            str(vehicle_id),
        )
    )


# ============================================================================
# CAUSAL SUPPORT
# ============================================================================


def _causal_paths_for_issue(
    exact_lineages: set[
        LineageKey
    ],
    edges: list[
        ManufacturingCausalEdge
    ],
    *,
    limit: int,
    causal_run_id: uuid.UUID | None = None,
    lag_minutes_per_step: int | None = None,
) -> tuple[
    CausalPathSupport,
    ...,
]:
    """Attach stable candidates only through exact run-window lineage machines."""

    if not exact_lineages:
        return ()

    exact_machine_ids = {
        machine_id
        for (
            machine_id,
            _,
            _,
        )
        in exact_lineages
    }

    candidates: list[
        CausalPathSupport
    ] = []

    for edge in edges:
        edge_machine_ids = {
            str(
                machine_id
            )
            for machine_id
            in (
                edge.machine_ids
                or []
            )
        }

        if not edge_machine_ids:
            continue

        overlap_machines = (
            exact_machine_ids
            & edge_machine_ids
        )

        if not overlap_machines:
            continue

        overlap = tuple(
            sorted(
                overlap_machines
            )
        )

        overlap_lineages = {
            lineage
            for lineage
            in exact_lineages
            if lineage[0]
            in overlap_machines
        }

        candidates.append(
            CausalPathSupport(
                source_metric=(
                    edge.source_metric
                ),

                target_metric=(
                    edge.target_metric
                ),

                scope=edge.scope,

                consensus_sign=(
                    edge.consensus_sign
                ),

                recurring_machines=int(
                    edge.recurring_machines
                ),

                eligible_machines=int(
                    edge.eligible_machines
                ),

                recurrence_fraction=float(
                    edge.recurrence_fraction
                ),

                sign_agreement=float(
                    edge.sign_agreement
                ),

                mean_abs_score=float(
                    edge.mean_abs_score
                ),

                best_q_value=float(
                    edge.best_q_value
                ),

                observed_lags=tuple(
                    int(
                        lag
                    )
                    for lag
                    in (
                        edge.observed_lags
                        or []
                    )
                ),

                overlap_machines=overlap,

                overlap_count=len(
                    overlap
                ),

                issue_exact_lineage_machine_fraction=(
                    len(
                        overlap
                    )
                    / len(
                        exact_machine_ids
                    )
                ),

                causal_edge_machine_fraction=(
                    len(
                        overlap
                    )
                    / len(
                        edge_machine_ids
                    )
                ),

                exact_lineage_count=len(
                    overlap_lineages
                ),

                exact_lineage_fraction=(
                    len(
                        overlap_lineages
                    )
                    / len(
                        exact_lineages
                    )
                ),

                edge_type="CAUSAL_DISCOVERED_MANUFACTURING",
                provenance="manufacturing_causal_run",
                causal_domain="manufacturing",
                causal_run_id=causal_run_id,
                # Persisted on the manufacturing edge, so the Edge Inspector
                # should show it rather than an em dash. Manufacturing edges
                # carry no p-value or min/max q-value spread, which stay unset.
                median_abs_score=float(edge.median_abs_score),
                observed_lag_minutes=(
                    tuple(
                        int(lag) * lag_minutes_per_step
                        for lag in (edge.observed_lags or [])
                    )
                    if lag_minutes_per_step is not None
                    else ()
                ),
                edge_orientation=str(edge.edge_orientation),
                edge_mark=str(edge.consensus_edge_mark),
                mark_agreement=float(edge.mark_agreement),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.exact_lineage_fraction,
            -item.exact_lineage_count,
            -item.overlap_count,
            -item.recurrence_fraction,
            -item.sign_agreement,
            -item.mean_abs_score,
            item.best_q_value,
            item.source_metric,
            item.target_metric,
        )
    )

    return tuple(
        candidates[
            :limit
        ]
    )


def _telematics_paths_for_issue(
    issue_category: str,
    vehicle_ids: set[str],
    edges: list[TelematicsCausalEdge],
    *,
    run_id: uuid.UUID | None,
    limit: int,
) -> tuple[CausalPathSupport, ...]:
    """Select persisted telematics candidates with vehicle-level support."""

    family = ISSUE_TELEMATICS_FAMILIES.get(
        issue_category,
        frozenset(),
    )
    if not family or not vehicle_ids:
        return ()

    candidates: list[CausalPathSupport] = []
    for edge in edges:
        source_metric = str(edge.source_metric)
        target_metric = str(edge.target_metric)
        if source_metric not in family and target_metric not in family:
            continue

        supporting_vehicle_ids = tuple(
            sorted(
                vehicle_ids
                & {
                    str(vehicle_id)
                    for vehicle_id in (edge.vehicle_ids or [])
                }
            )
        )
        if not supporting_vehicle_ids:
            continue

        edge_vehicle_ids = {
            str(vehicle_id)
            for vehicle_id in (edge.vehicle_ids or [])
        }
        candidates.append(
            CausalPathSupport(
                source_metric=source_metric,
                target_metric=target_metric,
                scope=str(edge.scope),
                consensus_sign=str(edge.consensus_sign),
                recurring_machines=0,
                eligible_machines=0,
                recurrence_fraction=float(edge.recurrence_fraction),
                sign_agreement=float(edge.sign_agreement),
                mean_abs_score=float(edge.mean_abs_score),
                best_q_value=float(edge.best_q_value),
                observed_lags=tuple(
                    int(lag)
                    for lag in (edge.observed_lags or [])
                ),
                overlap_machines=(),
                overlap_count=0,
                issue_exact_lineage_machine_fraction=0.0,
                causal_edge_machine_fraction=0.0,
                exact_lineage_count=0,
                exact_lineage_fraction=0.0,
                edge_type="CAUSAL_DISCOVERED_TELEMATICS",
                provenance="telematics_causal_run",
                causal_domain="telematics",
                causal_run_id=run_id,
                observed_lag_minutes=tuple(
                    int(lag)
                    for lag in (edge.observed_lag_minutes or [])
                ),
                best_p_value=float(edge.min_p_value),
                min_p_value=float(edge.min_p_value),
                max_p_value=float(edge.max_p_value),
                min_q_value=float(edge.min_q_value),
                max_q_value=float(edge.max_q_value),
                median_abs_score=float(edge.median_abs_score),
                recurring_vehicles=int(edge.recurring_vehicles),
                eligible_vehicles=int(edge.eligible_vehicles),
                supporting_vehicle_ids=supporting_vehicle_ids,
                overlap_vehicles=supporting_vehicle_ids,
                overlap_vehicle_count=len(supporting_vehicle_ids),
                issue_vehicle_fraction=(
                    len(supporting_vehicle_ids) / len(vehicle_ids)
                ),
                causal_edge_vehicle_fraction=(
                    len(supporting_vehicle_ids) / len(edge_vehicle_ids)
                    if edge_vehicle_ids
                    else 0.0
                ),
                edge_orientation=str(edge.edge_orientation),
                edge_mark=str(edge.consensus_edge_mark),
                mark_agreement=float(edge.mark_agreement),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.overlap_vehicle_count,
            -item.recurrence_fraction,
            -item.sign_agreement,
            -item.mean_abs_score,
            item.best_q_value,
            item.source_metric,
            item.target_metric,
        )
    )
    return tuple(candidates[:limit])


def _telematics_edges_considered(
    issue_category: str,
    vehicle_ids: set[str],
    edges: list[TelematicsCausalEdge],
) -> int:
    family = ISSUE_TELEMATICS_FAMILIES.get(
        issue_category,
        frozenset(),
    )
    if not family:
        return 0
    return sum(
        1
        for edge in edges
        if (
            str(edge.source_metric) in family
            or str(edge.target_metric) in family
        )
        and vehicle_ids
        & {
            str(vehicle_id)
            for vehicle_id in (edge.vehicle_ids or [])
        }
    )


def _telematics_eligibility_diagnostics(
    issue_category: str,
    warning_vehicle_ids: set[str],
    telematics_run: TelematicsCausalRun | None,
    edges: list[TelematicsCausalEdge],
    cohort_exclusions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Explain cohort/path absence factually, without changing causal validity.

    A vehicle missing from the cohort is reported with the cohort planner's own
    reason (``not_delivered``, ``insufficient_raw_history``,
    ``insufficient_analytical_rows``, ``outside_source_window``) rather than a
    generic label, so the absence can be acted on instead of guessed at.
    """
    cohort_ids = {
        str(vehicle_id)
        for vehicle_id in ((telematics_run.vehicle_ids if telematics_run is not None else []) or [])
    }
    planner_reasons = dict(cohort_exclusions or {})
    family = ISSUE_TELEMATICS_FAMILIES.get(issue_category, frozenset())
    family_edges = [
        edge
        for edge in edges
        if str(edge.source_metric) in family or str(edge.target_metric) in family
    ]
    supported_ids = {
        str(vehicle_id)
        for edge in family_edges
        for vehicle_id in (edge.vehicle_ids or [])
    }
    reasons: dict[str, str] = {}
    for vehicle_id in sorted(warning_vehicle_ids):
        if telematics_run is None:
            reasons[vehicle_id] = "no_completed_telematics_run"
        elif vehicle_id not in cohort_ids:
            reasons[vehicle_id] = planner_reasons.get(vehicle_id, "outside_source_window")
        elif not family:
            reasons[vehicle_id] = "no_supported_metric_family"
        elif vehicle_id not in supported_ids:
            reasons[vehicle_id] = "no_supported_metric_intersection"
    return {
        "warning_vehicle_count": len(warning_vehicle_ids),
        "completed_causal_cohort_count": len(cohort_ids),
        "warning_vehicles_in_completed_causal_cohort": sorted(warning_vehicle_ids & cohort_ids),
        "vehicles_with_supported_metric_intersection": sorted(warning_vehicle_ids & supported_ids),
        "supported_metric_family": sorted(family),
        "ineligibility_reasons": reasons,
    }


def _build_evidence_graph(
    *,
    issue_category: str,
    issue: dict[str, Any],
    exact_lineages: set[LineageKey],
    manufacturing_paths: tuple[CausalPathSupport, ...],
    telematics_paths: tuple[CausalPathSupport, ...],
    vehicle_warning_evidence: dict[str, dict[str, Any]],
) -> EvidenceGraph:
    # Graph construction is presentation-only. Every identifier comes from
    # runtime rows or the persisted causal edge/run records.
    nodes: dict[str, EvidenceGraphNode] = {}
    edges: dict[tuple[str, str, str, str], EvidenceGraphEdge] = {}

    def add_node(
        node_id: str,
        node_type: str,
        label: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        nodes.setdefault(
            node_id,
            EvidenceGraphNode(
                node_id=node_id,
                node_type=node_type,
                label=label,
                metadata=metadata or {},
            ),
        )

    def add_edge(
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        provenance: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = (
            source_node_id,
            target_node_id,
            edge_type,
            provenance,
        )
        edges.setdefault(
            key,
            EvidenceGraphEdge(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge_type,
                provenance=provenance,
                metadata=metadata or {},
            ),
        )

    issue_node_id = f"service_issue:{issue_category}"
    add_node(
        issue_node_id,
        "SERVICE_ISSUE",
        issue_category,
        {"issue_category": issue_category},
    )

    exact_lineage_set = set(exact_lineages)
    for machine_id, batch_id, supplier_lot_id in sorted(
        exact_lineage_set
    ):
        machine_node_id = f"machine:{machine_id}"
        batch_node_id = f"production_batch:{batch_id}"
        supplier_node_id = f"supplier_lot:{supplier_lot_id}"
        add_node(machine_node_id, "MACHINE", machine_id)
        add_node(batch_node_id, "PRODUCTION_BATCH", batch_id)
        add_node(supplier_node_id, "SUPPLIER_LOT", supplier_lot_id)
        add_edge(
            issue_node_id,
            machine_node_id,
            "LINEAGE",
            "field_service_warranty",
            {
                "machine_id": machine_id,
                "production_batch_id": batch_id,
                "supplier_lot_id": supplier_lot_id,
            },
        )
        add_edge(
            machine_node_id,
            batch_node_id,
            "LINEAGE",
            "manufacturing_timeseries",
        )
        add_edge(
            batch_node_id,
            supplier_node_id,
            "LINEAGE",
            "manufacturing_timeseries",
        )

    for machine_id, batch_id, supplier_lot_id, vehicle_id in sorted(
        issue["field_lineage_vehicle_keys"]
    ):
        if (
            machine_id,
            batch_id,
            supplier_lot_id,
        ) not in exact_lineage_set:
            continue
        vehicle_node_id = f"vehicle:{vehicle_id}"
        add_node(vehicle_node_id, "VEHICLE", vehicle_id)
        add_edge(
            f"machine:{machine_id}",
            vehicle_node_id,
            "LINEAGE",
            "field_service_warranty",
            {
                "production_batch_id": batch_id,
                "supplier_lot_id": supplier_lot_id,
            },
        )

    for path in manufacturing_paths:
        source_node_id = f"manufacturing_metric:{path.source_metric}"
        target_node_id = f"manufacturing_metric:{path.target_metric}"
        add_node(
            source_node_id,
            "MANUFACTURING_METRIC",
            path.source_metric,
        )
        add_node(
            target_node_id,
            "MANUFACTURING_METRIC",
            path.target_metric,
        )
        edge_metadata = {
            "source_metric": path.source_metric,
            "target_metric": path.target_metric,
            "consensus_sign": path.consensus_sign,
            "observed_lags": list(path.observed_lags),
            "observed_lag_minutes": list(path.observed_lag_minutes),
            "mean_abs_score": path.mean_abs_score,
            "best_q_value": path.best_q_value,
            "run_id": (
                str(path.causal_run_id)
                if path.causal_run_id is not None
                else None
            ),
            "supporting_machine_ids": list(path.overlap_machines),
            "edge_orientation": path.edge_orientation,
            "edge_mark": path.edge_mark,
            "mark_agreement": path.mark_agreement,
            "visual_style": _EDGE_ORIENTATION_VISUAL_STYLE.get(
                path.edge_orientation,
                "solid",
            ),
        }

        # A single edge, always -- an LPCMCI BIDIRECTED relationship is ONE
        # discovered relationship with no preferred direction, not two
        # separate directed ones. source_node_id/target_node_id remain a
        # structurally directed pair (the graph schema requires two
        # endpoints), but "edge_orientation": "BIDIRECTED" in metadata
        # tells the frontend to render double arrowheads on this single
        # edge rather than drawing it as source->target.
        add_edge(
            source_node_id,
            target_node_id,
            path.edge_type,
            path.provenance,
            edge_metadata,
        )
        for machine_id in path.overlap_machines:
            add_edge(
                target_node_id,
                f"machine:{machine_id}",
                "MANUFACTURING_EVIDENCE",
                path.provenance,
                {"machine_id": machine_id},
            )

    for path in telematics_paths:
        source_node_id = f"telemetry_metric:{path.source_metric}"
        target_node_id = f"telemetry_metric:{path.target_metric}"
        add_node(
            source_node_id,
            "TELEMETRY_METRIC",
            path.source_metric,
        )
        add_node(
            target_node_id,
            "TELEMETRY_METRIC",
            path.target_metric,
        )
        edge_metadata = {
            "source_metric": path.source_metric,
            "target_metric": path.target_metric,
            "consensus_sign": path.consensus_sign,
            "observed_lags": list(path.observed_lags),
            "observed_lag_minutes": list(path.observed_lag_minutes),
            "mean_abs_score": path.mean_abs_score,
            "median_abs_score": path.median_abs_score,
            "best_p_value": path.best_p_value,
            "min_p_value": path.min_p_value,
            "max_p_value": path.max_p_value,
            "best_q_value": path.best_q_value,
            "min_q_value": path.min_q_value,
            "max_q_value": path.max_q_value,
            "run_id": (
                str(path.causal_run_id)
                if path.causal_run_id is not None
                else None
            ),
            "supporting_vehicle_ids": list(
                path.supporting_vehicle_ids
            ),
            "edge_orientation": path.edge_orientation,
            "edge_mark": path.edge_mark,
            "mark_agreement": path.mark_agreement,
            "visual_style": _EDGE_ORIENTATION_VISUAL_STYLE.get(
                path.edge_orientation,
                "solid",
            ),
        }

        # See the manufacturing loop above: a single edge always, with
        # "edge_orientation" in metadata telling the frontend how to render
        # it (double arrowheads for BIDIRECTED, never two directed edges).
        add_edge(
            source_node_id,
            target_node_id,
            path.edge_type,
            path.provenance,
            edge_metadata,
        )
        for vehicle_id in path.supporting_vehicle_ids:
            vehicle_node_id = f"vehicle:{vehicle_id}"
            add_node(vehicle_node_id, "VEHICLE", vehicle_id)
            add_edge(
                vehicle_node_id,
                source_node_id,
                "TELEMETRY_EVIDENCE",
                path.provenance,
                {
                    "vehicle_id": vehicle_id,
                    "run_id": (
                        str(path.causal_run_id)
                        if path.causal_run_id is not None
                        else None
                    ),
                },
            )

    for vehicle_id, evidence in sorted(
        vehicle_warning_evidence.items()
    ):
        dtc_count = int(evidence.get("max_dtc_count", 0) or 0)
        warning_seen = bool(evidence.get("warning_seen", False))
        if not warning_seen and dtc_count <= 0:
            continue
        vehicle_node_id = f"vehicle:{vehicle_id}"
        warning_node_id = f"warning:{vehicle_id}"
        add_node(vehicle_node_id, "VEHICLE", vehicle_id)
        add_node(
            warning_node_id,
            "DTC_OR_WARNING",
            f"DTC / warning ({vehicle_id})",
            {
                "vehicle_id": vehicle_id,
                "max_dtc_count": dtc_count,
                "warning_seen": warning_seen,
            },
        )
        add_edge(
            vehicle_node_id,
            warning_node_id,
            "TELEMETRY_EVIDENCE",
            "vehicle_telematics_timeseries",
            {
                "vehicle_id": vehicle_id,
                "max_dtc_count": dtc_count,
                "warning_seen": warning_seen,
            },
        )

    for service_event_id in sorted(issue["service_event_ids"]):
        service_node_id = f"service_event:{service_event_id}"
        add_node(
            service_node_id,
            "SERVICE_ISSUE",
            f"Service event {service_event_id}",
            {"service_event_id": service_event_id},
        )
        for vehicle_id in sorted(
            issue["service_event_vehicle_ids"][service_event_id]
        ):
            add_node(
                f"vehicle:{vehicle_id}",
                "VEHICLE",
                vehicle_id,
            )
            add_edge(
                f"vehicle:{vehicle_id}",
                service_node_id,
                "SERVICE_EVIDENCE",
                "service_events",
                {
                    "vehicle_id": vehicle_id,
                    "service_event_id": service_event_id,
                },
            )
        add_edge(
            service_node_id,
            issue_node_id,
            "SERVICE_EVIDENCE",
            "service_events",
            {"service_event_id": service_event_id},
        )

    for claim_id in sorted(issue["warranty_claim_ids"]):
        claim_node_id = f"warranty_claim:{claim_id}"
        add_node(
            claim_node_id,
            "WARRANTY_CLAIM",
            f"Warranty claim {claim_id}",
            {"warranty_claim_id": claim_id},
        )
        for vehicle_id in sorted(
            issue["warranty_claim_vehicle_ids"][claim_id]
        ):
            add_node(
                f"vehicle:{vehicle_id}",
                "VEHICLE",
                vehicle_id,
            )
            add_edge(
                f"vehicle:{vehicle_id}",
                claim_node_id,
                "WARRANTY_EVIDENCE",
                "warranty_claims",
                {
                    "vehicle_id": vehicle_id,
                    "warranty_claim_id": claim_id,
                },
            )
        for service_event_id in sorted(
            issue["warranty_claim_service_event_ids"][claim_id]
        ):
            add_edge(
                f"service_event:{service_event_id}",
                claim_node_id,
                "WARRANTY_EVIDENCE",
                "warranty_claims",
                {
                    "service_event_id": service_event_id,
                    "warranty_claim_id": claim_id,
                },
            )
        add_edge(
            claim_node_id,
            issue_node_id,
            "WARRANTY_EVIDENCE",
            "warranty_claims",
            {"warranty_claim_id": claim_id},
        )

    return EvidenceGraph(
        nodes=tuple(
            nodes[node_id]
            for node_id in sorted(nodes)
        ),
        edges=tuple(
            edges[key]
            for key in sorted(edges)
        ),
    )


# ============================================================================
# HOTSPOTS
# ============================================================================


def _supplier_hotspots(
    issue: dict[
        str,
        Any,
    ],
    *,
    limit: int,
) -> tuple[
    SupplierHotspot,
    ...,
]:
    output: list[
        SupplierHotspot
    ] = []

    for (
        supplier_id,
        supplier_name,
        component_category,
    ), values in issue[
        "supplier_groups"
    ].items():

        output.append(
            SupplierHotspot(
                supplier_id=(
                    supplier_id
                ),

                supplier_name=(
                    supplier_name
                ),

                component_category=(
                    component_category
                ),

                claims=len(
                    values[
                        "claim_ids"
                    ]
                ),

                supplier_lots=len(
                    values[
                        "supplier_lot_ids"
                    ]
                ),

                batches=len(
                    values[
                        "batch_ids"
                    ]
                ),

                approved_exposure_inr=float(
                    values[
                        "approved_exposure_inr"
                    ]
                ),
            )
        )

    output.sort(
        key=lambda item: (
            -item.approved_exposure_inr,
            -item.claims,
            item.supplier_name,
        )
    )

    return tuple(
        output[
            :limit
        ]
    )


def _market_hotspots(
    issue: dict[
        str,
        Any,
    ],
    *,
    limit: int,
) -> tuple[
    MarketHotspot,
    ...,
]:
    output: list[
        MarketHotspot
    ] = []

    for (
        model_name,
        variant,
        region_name,
        city_name,
    ), values in issue[
        "market_groups"
    ].items():

        output.append(
            MarketHotspot(
                vehicle_model_name=(
                    model_name
                ),

                variant=variant,

                region_name=(
                    region_name
                ),

                city_name=(
                    city_name
                ),

                claims=len(
                    values[
                        "claim_ids"
                    ]
                ),

                batches=len(
                    values[
                        "batch_ids"
                    ]
                ),

                supplier_lots=len(
                    values[
                        "supplier_lot_ids"
                    ]
                ),

                approved_exposure_inr=float(
                    values[
                        "approved_exposure_inr"
                    ]
                ),
            )
        )

    output.sort(
        key=lambda item: (
            -item.claims,
            -item.approved_exposure_inr,
            item.vehicle_model_name,
            item.variant,
            item.city_name,
        )
    )

    return tuple(
        output[
            :limit
        ]
    )


# ============================================================================
# SERVICE
# ============================================================================


class WarrantyQualityEarlyWarningService(
    BaseService
):
    """Build exact-lineage causal warranty/quality warnings."""

    async def _load_run(
        self,
        run_id: uuid.UUID | str | None,
    ) -> ManufacturingCausalRun | None:
        statement = select(
            ManufacturingCausalRun
        )

        if run_id is not None:
            resolved_run_id = (
                run_id
                if isinstance(
                    run_id,
                    uuid.UUID,
                )
                else uuid.UUID(
                    str(
                        run_id
                    )
                )
            )

            statement = statement.where(
                ManufacturingCausalRun.id
                == resolved_run_id
            )

        else:
            statement = (
                statement
                .order_by(
                    ManufacturingCausalRun
                    .computed_at
                    .desc(),
                    ManufacturingCausalRun
                    .id
                    .desc(),
                )
                .limit(
                    1
                )
            )

        return (
            await self._session.execute(
                statement
            )
        ).scalar_one_or_none()

    async def _load_edges(
        self,
        run_id: uuid.UUID,
    ) -> list[
        ManufacturingCausalEdge
    ]:
        return list(
            (
                await self._session.execute(
                    select(
                        ManufacturingCausalEdge
                    )
                    .where(
                        ManufacturingCausalEdge.run_id
                        == run_id
                    )
                    .order_by(
                        ManufacturingCausalEdge
                        .recurrence_fraction
                        .desc(),

                        ManufacturingCausalEdge
                        .sign_agreement
                        .desc(),

                        ManufacturingCausalEdge
                        .mean_abs_score
                        .desc(),

                        ManufacturingCausalEdge
                        .best_q_value
                        .asc(),
                    )
                )
            ).scalars().all()
        )

    async def _load_telematics_cohort_exclusions(self) -> dict[str, str]:
        """Read the cohort planner's own per-vehicle exclusion reasons.

        The scheduler already decided, with the full runtime picture, why a
        vehicle could not be analysed. Reusing that verdict keeps the warning
        diagnostic factual instead of re-deriving a weaker guess here.
        """
        from app.models.causal_runtime_state import CausalSchedulerState

        state = await self._session.get(CausalSchedulerState, "telematics")
        diagnostics = (state.last_diagnostics or {}) if state is not None else {}
        exclusions = diagnostics.get("eligibility_exclusions")
        if not isinstance(exclusions, dict):
            return {}
        return {str(key): str(value) for key, value in exclusions.items()}

    async def _load_telematics_run(
        self,
        run_id: uuid.UUID | str | None,
    ) -> TelematicsCausalRun | None:
        statement = select(TelematicsCausalRun)
        if run_id is not None:
            resolved_run_id = (
                run_id
                if isinstance(run_id, uuid.UUID)
                else uuid.UUID(str(run_id))
            )
            statement = statement.where(
                TelematicsCausalRun.id == resolved_run_id
            )
        else:
            statement = (
                statement
                .order_by(
                    TelematicsCausalRun.computed_at.desc(),
                    TelematicsCausalRun.id.desc(),
                )
                .limit(1)
            )
        return (
            await self._session.execute(statement)
        ).scalar_one_or_none()

    async def _load_telematics_edges(
        self,
        run_id: uuid.UUID,
    ) -> list[TelematicsCausalEdge]:
        return list(
            (
                await self._session.execute(
                    select(TelematicsCausalEdge)
                    .where(TelematicsCausalEdge.run_id == run_id)
                    .order_by(
                        TelematicsCausalEdge.recurrence_fraction.desc(),
                        TelematicsCausalEdge.sign_agreement.desc(),
                        TelematicsCausalEdge.mean_abs_score.desc(),
                        TelematicsCausalEdge.best_q_value.asc(),
                    )
                )
            ).scalars().all()
        )

    async def _load_vehicle_warning_evidence(
        self,
        vehicle_ids: tuple[str, ...],
        simulation_as_of: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not vehicle_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    TELEMATICS_TABLE.c.vehicle_id,
                    func.max(
                        TELEMATICS_TABLE.c.dtc_count
                    ).label("max_dtc_count"),
                    func.bool_or(
                        TELEMATICS_TABLE.c.warning_flag
                    ).label("warning_seen"),
                )
                .where(
                    TELEMATICS_TABLE.c.vehicle_id.in_(vehicle_ids)
                )
                .where(
                    true() if simulation_as_of is None else TELEMATICS_TABLE.c.timestamp <= simulation_as_of
                )
                .group_by(TELEMATICS_TABLE.c.vehicle_id)
            )
        ).mappings().all()
        return {
            str(row["vehicle_id"]): {
                "max_dtc_count": int(row["max_dtc_count"] or 0),
                "warning_seen": bool(row["warning_seen"]),
            }
            for row in rows
        }

    async def _load_current_vehicle_ids(
        self,
        simulation_as_of: datetime | None = None,
    ) -> tuple[str, ...]:
        """Return telemetry vehicles visible at the replay watermark."""

        statement = select(TELEMATICS_TABLE.c.vehicle_id).distinct()
        if simulation_as_of is not None:
            statement = (
                statement
                .select_from(TELEMATICS_TABLE.join(DELIVERIES_TABLE, DELIVERIES_TABLE.c.vehicle_id == TELEMATICS_TABLE.c.vehicle_id))
                .where(TELEMATICS_TABLE.c.timestamp <= simulation_as_of)
                .where(DELIVERIES_TABLE.c.actual_delivery_date.is_not(None))
                .where(TELEMATICS_TABLE.c.timestamp >= DELIVERIES_TABLE.c.actual_delivery_date)
            )
        vehicle_ids = (
            await self._session.execute(statement.order_by(TELEMATICS_TABLE.c.vehicle_id))
        ).scalars().all()

        return tuple(
            str(vehicle_id)
            for vehicle_id in vehicle_ids
        )

    async def _load_manufacturing_lineages(
        self,
        *,
        machine_ids: tuple[
            str,
            ...,
        ],
        source_from: datetime,
        source_to: datetime,
    ) -> set[
        LineageKey
    ]:
        """Load exact manufacturing lineage present inside this causal run."""

        rows = (
            await self._session.execute(
                select(
                    MANUFACTURING_TABLE.c.machine_id,
                    MANUFACTURING_TABLE.c.production_batch_id,
                    MANUFACTURING_TABLE.c.supplier_lot_id,
                )
                .where(
                    MANUFACTURING_TABLE
                    .c.machine_id
                    .in_(
                        machine_ids
                    )
                )
                .where(
                    MANUFACTURING_TABLE.c.timestamp
                    >= source_from
                )
                .where(
                    MANUFACTURING_TABLE.c.timestamp
                    <= source_to
                )
                .distinct()
            )
        ).mappings().all()

        return {
            _lineage_key(
                row[
                    "machine_id"
                ],
                row[
                    "production_batch_id"
                ],
                row[
                    "supplier_lot_id"
                ],
            )
            for row
            in rows
        }

    async def _load_field_issues(
        self,
        machine_ids: tuple[
            str,
            ...,
        ],
        current_vehicle_ids: tuple[
            str,
            ...,
        ],
        simulation_as_of: datetime | None = None,
    ) -> dict[
        str,
        dict[
            str,
            Any,
        ],
    ]:
        """Aggregate observed service and warranty evidence by issue category."""

        if not current_vehicle_ids:
            return {}

        issues: dict[
            str,
            dict[
                str,
                Any,
            ],
        ] = {}

        # --------------------------------------------------------------------
        # SERVICE EVIDENCE
        #
        # Service severity is counted here exactly once.
        # --------------------------------------------------------------------

        service_rows = (
            await self._session.execute(
                select(
                    SERVICE_TABLE.c.service_event_id,
                    SERVICE_TABLE.c.issue_category,
                    SERVICE_TABLE.c.severity,

                    SERVICE_TABLE.c.complaint_reported,
                    SERVICE_TABLE.c.repair_required,
                    SERVICE_TABLE.c.warranty_candidate,

                    SERVICE_TABLE.c.representative_machine_id,
                    SERVICE_TABLE.c.vehicle_id,

                    SERVICE_TABLE.c.production_batch_id,
                    SERVICE_TABLE.c.primary_supplier_lot_id,

                    SERVICE_TABLE.c.vehicle_model_id,
                    SERVICE_TABLE.c.city_id,
                )
                .where(
                    SERVICE_TABLE
                    .c.representative_machine_id
                    .in_(
                        machine_ids
                    )
                )
                .where(
                    SERVICE_TABLE.c.vehicle_id.in_(
                        current_vehicle_ids
                    )
                )
                .where(
                    SERVICE_TABLE
                    .c.issue_category
                    .is_not(
                        None
                    )
                )
                .where(
                    true() if simulation_as_of is None else SERVICE_TABLE.c.service_started_at <= simulation_as_of
                )
            )
        ).mappings().all()

        for row in service_rows:
            issue_category = str(
                row[
                    "issue_category"
                ]
            )

            issue = issues.setdefault(
                issue_category,
                _new_issue(),
            )

            raw_service_event_id = row.get("service_event_id")
            if raw_service_event_id is not None:
                service_event_id = str(raw_service_event_id)
                issue["service_event_ids"].add(
                    service_event_id
                )
                issue["service_event_vehicle_ids"][
                    service_event_id
                ].add(
                    str(row["vehicle_id"])
                )

            issue[
                "service_events"
            ] += 1

            if row[
                "complaint_reported"
            ]:
                issue[
                    "complaints"
                ] += 1

            if row[
                "repair_required"
            ]:
                issue[
                    "repairs"
                ] += 1

            if row[
                "warranty_candidate"
            ]:
                issue[
                    "warranty_candidates"
                ] += 1

            _service_severity_bucket(
                issue,
                row[
                    "severity"
                ],
            )

            _add_common_field_dimensions(
                issue,

                machine_id=(
                    row[
                        "representative_machine_id"
                    ]
                ),

                vehicle_id=(
                    row[
                        "vehicle_id"
                    ]
                ),

                production_batch_id=(
                    row[
                        "production_batch_id"
                    ]
                ),

                supplier_lot_id=(
                    row[
                        "primary_supplier_lot_id"
                    ]
                ),

                vehicle_model_id=(
                    row[
                        "vehicle_model_id"
                    ]
                ),

                city_id=(
                    row[
                        "city_id"
                    ]
                ),
            )

        # --------------------------------------------------------------------
        # WARRANTY EVIDENCE
        #
        # Deliberately excludes claim_probability and root_cause_domain.
        # --------------------------------------------------------------------

        warranty_rows = (
            await self._session.execute(
                select(
                    WARRANTY_TABLE.c.warranty_claim_id,
                    WARRANTY_TABLE.c.service_event_id,
                    WARRANTY_TABLE.c.issue_category,

                    WARRANTY_TABLE.c.representative_machine_id,
                    WARRANTY_TABLE.c.vehicle_id,

                    WARRANTY_TABLE.c.production_batch_id,

                    WARRANTY_TABLE.c.primary_supplier_id,
                    WARRANTY_TABLE.c.primary_supplier_name,
                    WARRANTY_TABLE.c.primary_supplier_lot_id,
                    WARRANTY_TABLE.c.supplier_component_category,

                    WARRANTY_TABLE.c.vehicle_model_id,
                    WARRANTY_TABLE.c.vehicle_model_name,
                    WARRANTY_TABLE.c.variant,

                    WARRANTY_TABLE.c.region_name,
                    WARRANTY_TABLE.c.city_id,
                    WARRANTY_TABLE.c.city_name,

                    WARRANTY_TABLE.c.claim_amount_inr,
                    WARRANTY_TABLE.c.approved_amount_inr,
                )
                .where(
                    WARRANTY_TABLE
                    .c.representative_machine_id
                    .in_(
                        machine_ids
                    )
                )
                .where(
                    WARRANTY_TABLE.c.vehicle_id.in_(
                        current_vehicle_ids
                    )
                )
                .where(
                    true() if simulation_as_of is None else WARRANTY_TABLE.c.claim_submitted_at <= simulation_as_of
                )
            )
        ).mappings().all()

        for row in warranty_rows:
            issue_category = str(
                row[
                    "issue_category"
                ]
            )

            issue = issues.setdefault(
                issue_category,
                _new_issue(),
            )

            claim_id = str(
                row[
                    "warranty_claim_id"
                ]
            )

            claim_amount = float(
                row[
                    "claim_amount_inr"
                ]
                or 0.0
            )

            approved_amount = float(
                row[
                    "approved_amount_inr"
                ]
                or 0.0
            )

            issue["warranty_claim_ids"].add(
                claim_id
            )
            issue["warranty_claim_vehicle_ids"][
                claim_id
            ].add(
                str(row["vehicle_id"])
            )
            raw_service_event_id = row.get("service_event_id")
            if raw_service_event_id is not None:
                issue["warranty_claim_service_event_ids"][
                    claim_id
                ].add(
                    str(raw_service_event_id)
                )

            issue[
                "warranty_claims"
            ] += 1

            issue[
                "claim_exposure_inr"
            ] += claim_amount

            issue[
                "approved_exposure_inr"
            ] += approved_amount

            _add_common_field_dimensions(
                issue,

                machine_id=(
                    row[
                        "representative_machine_id"
                    ]
                ),

                vehicle_id=(
                    row[
                        "vehicle_id"
                    ]
                ),

                production_batch_id=(
                    row[
                        "production_batch_id"
                    ]
                ),

                supplier_lot_id=(
                    row[
                        "primary_supplier_lot_id"
                    ]
                ),

                vehicle_model_id=(
                    row[
                        "vehicle_model_id"
                    ]
                ),

                city_id=(
                    row[
                        "city_id"
                    ]
                ),
            )

            supplier_key = (
                str(
                    row[
                        "primary_supplier_id"
                    ]
                ),

                str(
                    row[
                        "primary_supplier_name"
                    ]
                ),

                str(
                    row[
                        "supplier_component_category"
                    ]
                ),
            )

            supplier_group = issue[
                "supplier_groups"
            ][
                supplier_key
            ]

            supplier_group[
                "claim_ids"
            ].add(
                claim_id
            )

            supplier_group[
                "supplier_lot_ids"
            ].add(
                str(
                    row[
                        "primary_supplier_lot_id"
                    ]
                )
            )

            supplier_group[
                "batch_ids"
            ].add(
                str(
                    row[
                        "production_batch_id"
                    ]
                )
            )

            supplier_group[
                "approved_exposure_inr"
            ] += approved_amount

            market_key = (
                str(
                    row[
                        "vehicle_model_name"
                    ]
                ),

                str(
                    row[
                        "variant"
                    ]
                ),

                str(
                    row[
                        "region_name"
                    ]
                ),

                str(
                    row[
                        "city_name"
                    ]
                ),
            )

            market_group = issue[
                "market_groups"
            ][
                market_key
            ]

            market_group[
                "claim_ids"
            ].add(
                claim_id
            )

            market_group[
                "batch_ids"
            ].add(
                str(
                    row[
                        "production_batch_id"
                    ]
                )
            )

            market_group[
                "supplier_lot_ids"
            ].add(
                str(
                    row[
                        "primary_supplier_lot_id"
                    ]
                )
            )

            market_group[
                "approved_exposure_inr"
            ] += approved_amount

        return issues

    @staticmethod
    def _apply_exact_lineage(
        issues: dict[
            str,
            dict[
                str,
                Any,
            ],
        ],
        manufacturing_lineages: set[
            LineageKey
        ],
    ) -> None:
        """Intersect every field issue with manufacturing lineage in run window."""

        for issue in issues.values():
            issue[
                "exact_window_lineages"
            ] = (
                set(
                    issue[
                        "field_lineages"
                    ]
                )
                & manufacturing_lineages
            )

    async def get_warnings(
        self,
        *,
        run_id: uuid.UUID | str | None = None,
        telematics_run_id: uuid.UUID | str | None = None,
        simulation_as_of: datetime | None = None,
        config: WarrantyQualityWarningConfig = (
            DEFAULT_WARNING_CONFIG
        ),
    ) -> WarrantyQualityEarlyWarningResult | None:
        """Build exact-lineage causal warnings for one persisted causal run."""

        _validate_config(
            config
        )
        if simulation_as_of is not None:
            if simulation_as_of.tzinfo is None or simulation_as_of.utcoffset() is None:
                raise ValueError("simulation_as_of must be timezone-aware.")
            simulation_as_of = simulation_as_of.astimezone(UTC)

        run = await self._load_run(
            run_id
        )

        if run is None:
            return None

        telematics_run = await self._load_telematics_run(
            telematics_run_id
        )
        telematics_edges = (
            await self._load_telematics_edges(telematics_run.id)
            if telematics_run is not None
            else []
        )
        telematics_cohort_exclusions = await self._load_telematics_cohort_exclusions()

        machine_ids = tuple(
            sorted(
                str(
                    machine_id
                )
                for machine_id
                in (
                    run.machine_ids
                    or []
                )
            )
        )

        if not machine_ids:
            raise RuntimeError(
                "Persisted manufacturing causal run "
                "contains no machine IDs."
            )

        if (
            run.source_from is None
            or run.source_to is None
        ):
            raise RuntimeError(
                "Persisted manufacturing causal run "
                "has no source window."
            )

        edges = await self._load_edges(
            run.id
        )

        lag_minutes_parameter = (
            (run.parameters or {}).get("analysis_frequency_minutes")
        )
        try:
            manufacturing_lag_minutes_per_step = (
                int(lag_minutes_parameter)
                if lag_minutes_parameter is not None
                else None
            )
        except (TypeError, ValueError):
            manufacturing_lag_minutes_per_step = None

        manufacturing_lineages = (
            await self._load_manufacturing_lineages(
                machine_ids=machine_ids,
                source_from=run.source_from,
                source_to=run.source_to,
            )
        )

        current_vehicle_ids = (
            await self._load_current_vehicle_ids(simulation_as_of)
        )

        issues = await self._load_field_issues(
            machine_ids,
            current_vehicle_ids,
            simulation_as_of,
        )
        vehicle_warning_evidence = (
            await self._load_vehicle_warning_evidence(
                current_vehicle_ids,
                simulation_as_of,
            )
        )

        self._apply_exact_lineage(
            issues,
            manufacturing_lineages,
        )

        if not issues:
            return WarrantyQualityEarlyWarningResult(
                causal_run_id=run.id,
                causal_signature=run.signature,

                source_from=run.source_from,
                source_to=run.source_to,

                generated_at=datetime.now(
                    UTC
                ),

                issue_categories_evaluated=0,
                issue_categories_with_exact_lineage=0,

                warnings_generated=0,

                calibration=(
                    _zero_calibration()
                ),

                warnings=(),

                manufacturing_causal_run_id=run.id,
                telematics_causal_run_id=(
                    telematics_run.id
                    if telematics_run is not None
                    else None
                ),
                telematics_causal_signature=(
                    telematics_run.signature
                    if telematics_run is not None
                    else None
                ),
                telematics_source_from=(
                    telematics_run.source_from
                    if telematics_run is not None
                    else None
                ),
                telematics_source_to=(
                    telematics_run.source_to
                    if telematics_run is not None
                    else None
                ),
                simulation_as_of=simulation_as_of,
            )

        issue_values = list(
            issues.values()
        )

        # --------------------------------------------------------------------
        # EMPIRICAL FIELD CALIBRATION
        # --------------------------------------------------------------------

        complaints_values = [
            float(
                issue[
                    "complaints"
                ]
            )
            for issue
            in issue_values
        ]

        claims_values = [
            float(
                issue[
                    "warranty_claims"
                ]
            )
            for issue
            in issue_values
        ]

        approved_values = [
            float(
                issue[
                    "approved_exposure_inr"
                ]
            )
            for issue
            in issue_values
        ]

        batches_values = [
            float(
                len(
                    issue[
                        "batch_ids"
                    ]
                )
            )
            for issue
            in issue_values
        ]

        supplier_lots_values = [
            float(
                len(
                    issue[
                        "supplier_lot_ids"
                    ]
                )
            )
            for issue
            in issue_values
        ]

        cities_values = [
            float(
                len(
                    issue[
                        "city_ids"
                    ]
                )
            )
            for issue
            in issue_values
        ]

        complaints_p50 = _percentile_cont(
            complaints_values,
            config.percentile_median,
        )

        complaints_p75 = _percentile_cont(
            complaints_values,
            config.percentile_high,
        )

        complaints_p90 = _percentile_cont(
            complaints_values,
            config.percentile_extreme,
        )

        claims_p50 = _percentile_cont(
            claims_values,
            config.percentile_median,
        )

        claims_p75 = _percentile_cont(
            claims_values,
            config.percentile_high,
        )

        claims_p90 = _percentile_cont(
            claims_values,
            config.percentile_extreme,
        )

        approved_p50 = _percentile_cont(
            approved_values,
            config.percentile_median,
        )

        approved_p75 = _percentile_cont(
            approved_values,
            config.percentile_high,
        )

        approved_p90 = _percentile_cont(
            approved_values,
            config.percentile_extreme,
        )

        batches_p75 = _percentile_cont(
            batches_values,
            config.percentile_high,
        )

        supplier_lots_p75 = _percentile_cont(
            supplier_lots_values,
            config.percentile_high,
        )

        cities_p75 = _percentile_cont(
            cities_values,
            config.percentile_high,
        )

        # --------------------------------------------------------------------
        # TRANSPARENT EVIDENCE INDEX
        #
        # This is NOT probability and NOT AI confidence.
        #
        # Causal evidence remains separate.
        # --------------------------------------------------------------------

        scores: dict[
            str,
            int,
        ] = {}

        for (
            issue_category,
            issue,
        ) in issues.items():

            score = 0

            score += _empirical_tier(
                float(
                    issue[
                        "complaints"
                    ]
                ),
                p75=complaints_p75,
                p90=complaints_p90,
            )

            score += _empirical_tier(
                float(
                    issue[
                        "warranty_claims"
                    ]
                ),
                p75=claims_p75,
                p90=claims_p90,
            )

            score += _empirical_tier(
                float(
                    issue[
                        "approved_exposure_inr"
                    ]
                ),
                p75=approved_p75,
                p90=approved_p90,
            )

            if (
                issue[
                    "service_high_events"
                ]
                > 0
            ):
                score += 2

            elif (
                issue[
                    "service_medium_events"
                ]
                > 0
            ):
                score += 1

            if (
                batches_p75 > 0.0
                and len(
                    issue[
                        "batch_ids"
                    ]
                )
                >= batches_p75
            ):
                score += 1

            if (
                supplier_lots_p75 > 0.0
                and len(
                    issue[
                        "supplier_lot_ids"
                    ]
                )
                >= supplier_lots_p75
            ):
                score += 1

            if (
                cities_p75 > 0.0
                and len(
                    issue[
                        "city_ids"
                    ]
                )
                >= cities_p75
            ):
                score += 1

            scores[
                issue_category
            ] = score

        score_values = [
            float(
                score
            )
            for score
            in scores.values()
        ]

        score_p50 = _percentile_cont(
            score_values,
            config.percentile_median,
        )

        score_p75 = _percentile_cont(
            score_values,
            config.percentile_high,
        )

        score_p90 = _percentile_cont(
            score_values,
            config.percentile_extreme,
        )

        calibration = WarningCalibration(
            issue_categories=len(
                issues
            ),

            complaints_p50=(
                complaints_p50
            ),

            complaints_p75=(
                complaints_p75
            ),

            complaints_p90=(
                complaints_p90
            ),

            claims_p50=(
                claims_p50
            ),

            claims_p75=(
                claims_p75
            ),

            claims_p90=(
                claims_p90
            ),

            approved_exposure_p50=(
                approved_p50
            ),

            approved_exposure_p75=(
                approved_p75
            ),

            approved_exposure_p90=(
                approved_p90
            ),

            batches_p75=(
                batches_p75
            ),

            supplier_lots_p75=(
                supplier_lots_p75
            ),

            cities_p75=(
                cities_p75
            ),

            evidence_score_p50=(
                score_p50
            ),

            evidence_score_p75=(
                score_p75
            ),

            evidence_score_p90=(
                score_p90
            ),
        )

        # --------------------------------------------------------------------
        # BUILD EXACT-LINEAGE CAUSAL WARNINGS
        # --------------------------------------------------------------------

        warnings: list[
            WarrantyQualityWarning
        ] = []

        issues_with_exact_lineage = 0

        for issue_category in sorted(
            issues
        ):
            issue = issues[
                issue_category
            ]

            field_lineages: set[
                LineageKey
            ] = set(
                issue[
                    "field_lineages"
                ]
            )

            exact_lineages: set[
                LineageKey
            ] = set(
                issue[
                    "exact_window_lineages"
                ]
            )

            if exact_lineages:
                issues_with_exact_lineage += 1

            field_lineage_count = len(
                field_lineages
            )

            exact_lineage_count = len(
                exact_lineages
            )

            lineage_coverage = (
                exact_lineage_count
                / field_lineage_count
                if field_lineage_count
                else 0.0
            )

            exact_machine_ids = {
                machine_id
                for (
                    machine_id,
                    _,
                    _,
                )
                in exact_lineages
            }

            # A causal warning requires at least one exact manufacturing
            # lineage inside the persisted causal-run source window.
            if not exact_lineages:
                continue

            manufacturing_paths = (
                _causal_paths_for_issue(
                    exact_lineages,
                    edges,
                    limit=config.max_causal_paths,
                    causal_run_id=run.id,
                    lag_minutes_per_step=(
                        manufacturing_lag_minutes_per_step
                    ),
                )
            )

            exact_vehicle_ids = {
                vehicle_id
                for (
                    machine_id,
                    production_batch_id,
                    supplier_lot_id,
                    vehicle_id,
                )
                in issue["field_lineage_vehicle_keys"]
                if (
                    machine_id,
                    production_batch_id,
                    supplier_lot_id,
                ) in exact_lineages
            }
            telematics_paths = (
                _telematics_paths_for_issue(
                    issue_category,
                    exact_vehicle_ids,
                    telematics_edges,
                    run_id=(
                        telematics_run.id
                        if telematics_run is not None
                        else None
                    ),
                    limit=config.max_causal_paths,
                )
            )
            causal_paths = manufacturing_paths + telematics_paths
            telematics_eligibility_diagnostics = _telematics_eligibility_diagnostics(
                issue_category,
                exact_vehicle_ids,
                telematics_run,
                telematics_edges,
                telematics_cohort_exclusions,
            )

            if not causal_paths:
                continue

            telematics_edges_considered = (
                _telematics_edges_considered(
                    issue_category,
                    exact_vehicle_ids,
                    telematics_edges,
                )
            )
            evidence_graph = _build_evidence_graph(
                issue_category=issue_category,
                issue=issue,
                exact_lineages=exact_lineages,
                manufacturing_paths=manufacturing_paths,
                telematics_paths=telematics_paths,
                vehicle_warning_evidence={
                    vehicle_id: vehicle_warning_evidence[vehicle_id]
                    for vehicle_id in exact_vehicle_ids
                    if vehicle_id in vehicle_warning_evidence
                },
            )

            score = scores[
                issue_category
            ]

            if score <= 0:
                priority = "LOW"

            elif (
                score_p90 > 0.0
                and score >= score_p90
            ):
                priority = "CRITICAL"

            elif (
                score_p75 > 0.0
                and score >= score_p75
            ):
                priority = "HIGH"

            elif (
                score_p50 > 0.0
                and score >= score_p50
            ):
                priority = "MEDIUM"

            else:
                priority = "LOW"

            all_machine_ids = {
                str(
                    machine_id
                )
                for machine_id
                in issue[
                    "machine_ids"
                ]
            }

            warnings.append(
                WarrantyQualityWarning(
                    issue_category=(
                        issue_category
                    ),

                    priority=(
                        priority
                    ),

                    evidence_score=(
                        score
                    ),

                    service_events=int(
                        issue[
                            "service_events"
                        ]
                    ),

                    complaints=int(
                        issue[
                            "complaints"
                        ]
                    ),

                    repairs=int(
                        issue[
                            "repairs"
                        ]
                    ),

                    warranty_candidates=int(
                        issue[
                            "warranty_candidates"
                        ]
                    ),

                    warranty_claims=int(
                        issue[
                            "warranty_claims"
                        ]
                    ),

                    service_low_events=int(
                        issue[
                            "service_low_events"
                        ]
                    ),

                    service_medium_events=int(
                        issue[
                            "service_medium_events"
                        ]
                    ),

                    service_high_events=int(
                        issue[
                            "service_high_events"
                        ]
                    ),

                    affected_machines=len(
                        all_machine_ids
                    ),

                    affected_vehicles=len(
                        issue[
                            "vehicle_ids"
                        ]
                    ),

                    affected_batches=len(
                        issue[
                            "batch_ids"
                        ]
                    ),

                    affected_supplier_lots=len(
                        issue[
                            "supplier_lot_ids"
                        ]
                    ),

                    affected_models=len(
                        issue[
                            "model_ids"
                        ]
                    ),

                    affected_cities=len(
                        issue[
                            "city_ids"
                        ]
                    ),

                    claim_exposure_inr=float(
                        issue[
                            "claim_exposure_inr"
                        ]
                    ),

                    approved_exposure_inr=float(
                        issue[
                            "approved_exposure_inr"
                        ]
                    ),

                    field_lineages=(
                        field_lineage_count
                    ),

                    exact_window_lineages=(
                        exact_lineage_count
                    ),

                    exact_window_lineage_coverage=(
                        lineage_coverage
                    ),

                    exact_lineage_machines=len(
                        exact_machine_ids
                    ),

                    lineage_evidence_grade=(
                        _lineage_grade(
                            field_lineage_count,
                            exact_lineage_count,
                        )
                    ),

                    machine_ids=tuple(
                        sorted(
                            all_machine_ids
                        )
                    ),

                    exact_lineages=(
                        _lineage_evidence(
                            exact_lineages
                        )
                    ),

                    causal_paths=(
                        causal_paths
                    ),

                    supplier_hotspots=(
                        _supplier_hotspots(
                            issue,
                            limit=(
                                config
                                .max_supplier_hotspots
                            ),
                        )
                    ),

                    market_hotspots=(
                        _market_hotspots(
                            issue,
                            limit=(
                                config
                                .max_market_hotspots
                            ),
                        )
                    ),

                    service_event_ids=tuple(
                        sorted(issue["service_event_ids"])
                    ),
                    warranty_claim_ids=tuple(
                        sorted(issue["warranty_claim_ids"])
                    ),
                    telematics_edges_considered=(
                        telematics_edges_considered
                    ),
                    telematics_paths_selected=len(
                        telematics_paths
                    ),
                    telematics_eligibility_diagnostics=telematics_eligibility_diagnostics,
                    evidence_graph=evidence_graph,
                )
            )

        priority_order = {
            "CRITICAL": 0,
            "HIGH": 1,
            "MEDIUM": 2,
            "LOW": 3,
        }

        warnings.sort(
            key=lambda warning: (
                priority_order[
                    warning.priority
                ],
                -warning.evidence_score,
                -warning.exact_window_lineage_coverage,
                -warning.approved_exposure_inr,
                -warning.warranty_claims,
                -warning.complaints,
                warning.issue_category,
            )
        )

        return WarrantyQualityEarlyWarningResult(
            causal_run_id=(
                run.id
            ),

            causal_signature=(
                run.signature
            ),

            source_from=(
                run.source_from
            ),

            source_to=(
                run.source_to
            ),

            generated_at=datetime.now(
                UTC
            ),

            issue_categories_evaluated=len(
                issues
            ),

            issue_categories_with_exact_lineage=(
                issues_with_exact_lineage
            ),

            warnings_generated=len(
                warnings
            ),

            calibration=(
                calibration
            ),

            warnings=tuple(
                warnings
            ),

            manufacturing_causal_run_id=run.id,
            telematics_causal_run_id=(
                telematics_run.id
                if telematics_run is not None
                else None
            ),
            telematics_causal_signature=(
                telematics_run.signature
                if telematics_run is not None
                else None
            ),
            telematics_source_from=(
                telematics_run.source_from
                if telematics_run is not None
                else None
            ),
            telematics_source_to=(
                telematics_run.source_to
                if telematics_run is not None
                else None
            ),
            simulation_as_of=simulation_as_of,
        )
