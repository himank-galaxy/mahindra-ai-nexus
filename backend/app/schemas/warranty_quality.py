"""Warranty, Quality & Service early-warning API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal[
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
]

LineageEvidenceGrade = Literal[
    "EXACT_WINDOW_LINEAGE",
    "PARTIAL_EXACT_WINDOW_LINEAGE",
    "NO_EXACT_WINDOW_LINEAGE",
    "NO_FIELD_LINEAGE",
]


class WarrantyQualitySchema(BaseModel):
    """Base schema supporting validation from service dataclasses."""

    model_config = ConfigDict(
        from_attributes=True,
    )


class ExactLineageOut(
    WarrantyQualitySchema
):
    """Exact manufacturing lineage supporting a field issue."""

    machine_id: str
    production_batch_id: str
    supplier_lot_id: str


class CausalPathSupportOut(
    WarrantyQualitySchema
):
    """Stable PCMCI candidate associated through exact lineage."""

    source_metric: str
    target_metric: str

    scope: str
    consensus_sign: str

    recurring_machines: int = Field(
        ge=0,
    )

    eligible_machines: int = Field(
        ge=0,
    )

    recurrence_fraction: float = Field(
        ge=0.0,
        le=1.0,
    )

    sign_agreement: float = Field(
        ge=0.0,
        le=1.0,
    )

    mean_abs_score: float = Field(
        ge=0.0,
    )

    best_q_value: float = Field(
        ge=0.0,
        le=1.0,
    )

    observed_lags: tuple[
        int,
        ...,
    ]

    overlap_machines: tuple[
        str,
        ...,
    ]

    overlap_count: int = Field(
        ge=0,
    )

    issue_exact_lineage_machine_fraction: float = Field(
        ge=0.0,
        le=1.0,
    )

    causal_edge_machine_fraction: float = Field(
        ge=0.0,
        le=1.0,
    )

    exact_lineage_count: int = Field(
        ge=0,
    )

    exact_lineage_fraction: float = Field(
        ge=0.0,
        le=1.0,
    )

    edge_type: str = "CAUSAL_DISCOVERED_MANUFACTURING"
    provenance: str = "manufacturing_causal_run"
    causal_domain: str = "manufacturing"

    # LPCMCI edge orientation. Distinct from edge_type (a domain-provenance
    # tag, e.g. "CAUSAL_DISCOVERED_MANUFACTURING") -- this is the discovered
    # statistical relationship's shape. Defaults reflect PCMCI's plain
    # directed output, so existing consumers/fixtures built without these
    # fields keep validating.
    edge_orientation: str = "DIRECTED"
    edge_mark: str = "-->"
    mark_agreement: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )
    causal_run_id: UUID | None = None
    observed_lag_minutes: tuple[int, ...] = ()
    best_p_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_p_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    max_p_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    min_q_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    max_q_value: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    median_abs_score: float | None = Field(
        default=None,
        ge=0.0,
    )
    recurring_vehicles: int = Field(
        default=0,
        ge=0,
    )
    eligible_vehicles: int = Field(
        default=0,
        ge=0,
    )
    supporting_vehicle_ids: tuple[str, ...] = ()
    overlap_vehicles: tuple[str, ...] = ()
    overlap_vehicle_count: int = Field(
        default=0,
        ge=0,
    )
    issue_vehicle_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    causal_edge_vehicle_fraction: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class EvidenceGraphNodeOut(
    WarrantyQualitySchema
):
    node_id: str
    node_type: str
    label: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class EvidenceGraphEdgeOut(
    WarrantyQualitySchema
):
    source_node_id: str
    target_node_id: str
    edge_type: str
    provenance: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class EvidenceGraphOut(
    WarrantyQualitySchema
):
    nodes: tuple[
        EvidenceGraphNodeOut,
        ...,
    ] = ()
    edges: tuple[
        EvidenceGraphEdgeOut,
        ...,
    ] = ()


class SupplierHotspotOut(
    WarrantyQualitySchema
):
    """Warranty exposure grouped by supplier/component."""

    supplier_id: str
    supplier_name: str
    component_category: str

    claims: int = Field(
        ge=0,
    )

    supplier_lots: int = Field(
        ge=0,
    )

    batches: int = Field(
        ge=0,
    )

    approved_exposure_inr: float = Field(
        ge=0.0,
    )


class MarketHotspotOut(
    WarrantyQualitySchema
):
    """Warranty exposure grouped by model/variant/geography."""

    vehicle_model_name: str
    variant: str

    region_name: str
    city_name: str

    claims: int = Field(
        ge=0,
    )

    batches: int = Field(
        ge=0,
    )

    supplier_lots: int = Field(
        ge=0,
    )

    approved_exposure_inr: float = Field(
        ge=0.0,
    )


class WarningCalibrationOut(
    WarrantyQualitySchema
):
    """Empirical field calibration used by warning prioritization."""

    issue_categories: int = Field(
        ge=0,
    )

    complaints_p50: float = Field(
        ge=0.0,
    )

    complaints_p75: float = Field(
        ge=0.0,
    )

    complaints_p90: float = Field(
        ge=0.0,
    )

    claims_p50: float = Field(
        ge=0.0,
    )

    claims_p75: float = Field(
        ge=0.0,
    )

    claims_p90: float = Field(
        ge=0.0,
    )

    approved_exposure_p50: float = Field(
        ge=0.0,
    )

    approved_exposure_p75: float = Field(
        ge=0.0,
    )

    approved_exposure_p90: float = Field(
        ge=0.0,
    )

    batches_p75: float = Field(
        ge=0.0,
    )

    supplier_lots_p75: float = Field(
        ge=0.0,
    )

    cities_p75: float = Field(
        ge=0.0,
    )

    evidence_score_p50: float = Field(
        ge=0.0,
    )

    evidence_score_p75: float = Field(
        ge=0.0,
    )

    evidence_score_p90: float = Field(
        ge=0.0,
    )


class WarrantyQualityWarningOut(
    WarrantyQualitySchema
):
    """One issue-category early warning."""

    issue_category: str

    priority: Priority

    # Transparent evidence index, not probability/confidence.
    evidence_score: int = Field(
        ge=0,
    )

    service_events: int = Field(
        ge=0,
    )

    complaints: int = Field(
        ge=0,
    )

    repairs: int = Field(
        ge=0,
    )

    warranty_candidates: int = Field(
        ge=0,
    )

    warranty_claims: int = Field(
        ge=0,
    )

    service_low_events: int = Field(
        ge=0,
    )

    service_medium_events: int = Field(
        ge=0,
    )

    service_high_events: int = Field(
        ge=0,
    )

    affected_machines: int = Field(
        ge=0,
    )

    affected_vehicles: int = Field(
        ge=0,
    )

    affected_batches: int = Field(
        ge=0,
    )

    affected_supplier_lots: int = Field(
        ge=0,
    )

    affected_models: int = Field(
        ge=0,
    )

    affected_cities: int = Field(
        ge=0,
    )

    claim_exposure_inr: float = Field(
        ge=0.0,
    )

    approved_exposure_inr: float = Field(
        ge=0.0,
    )

    field_lineages: int = Field(
        ge=0,
    )

    exact_window_lineages: int = Field(
        ge=0,
    )

    exact_window_lineage_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )

    exact_lineage_machines: int = Field(
        ge=0,
    )

    lineage_evidence_grade: LineageEvidenceGrade

    machine_ids: tuple[
        str,
        ...,
    ]

    exact_lineages: tuple[
        ExactLineageOut,
        ...,
    ]

    causal_paths: tuple[
        CausalPathSupportOut,
        ...,
    ]

    supplier_hotspots: tuple[
        SupplierHotspotOut,
        ...,
    ]

    market_hotspots: tuple[
        MarketHotspotOut,
        ...,
    ]

    service_event_ids: tuple[str, ...] = ()
    warranty_claim_ids: tuple[str, ...] = ()
    telematics_edges_considered: int = Field(
        default=0,
        ge=0,
    )
    telematics_paths_selected: int = Field(
        default=0,
        ge=0,
    )
    telematics_eligibility_diagnostics: dict[str, Any] = Field(default_factory=dict)
    lifecycle_state: Literal["NEW", "ACTIVE", "ESCALATED", "DEESCALATED", "RESOLVED", "UNCHANGED"] = "UNCHANGED"
    warning_signature: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_transition_at: datetime | None = None
    evidence_graph: EvidenceGraphOut = Field(
        default_factory=EvidenceGraphOut,
    )


class WarrantyQualityEarlyWarningOut(
    WarrantyQualitySchema
):
    """Complete early-warning API response."""

    causal_run_id: UUID
    causal_signature: str

    source_from: datetime
    source_to: datetime

    generated_at: datetime

    issue_categories_evaluated: int = Field(
        ge=0,
    )

    issue_categories_with_exact_lineage: int = Field(
        ge=0,
    )

    warnings_generated: int = Field(
        ge=0,
    )

    calibration: WarningCalibrationOut

    warnings: tuple[
        WarrantyQualityWarningOut,
        ...,
    ]

    manufacturing_causal_run_id: UUID | None = None
    telematics_causal_run_id: UUID | None = None
    telematics_causal_signature: str | None = None
    telematics_source_from: datetime | None = None
    telematics_source_to: datetime | None = None
    simulation_as_of: datetime | None = None


class CausalGraphDeltaOut(WarrantyQualitySchema):
    """Structural change against the previous successful causal run."""

    new_edges: int = Field(default=0, ge=0)
    removed_edges: int = Field(default=0, ge=0)
    unchanged_edges: int = Field(default=0, ge=0)
    strengthened_edges: int = Field(default=0, ge=0)
    weakened_edges: int = Field(default=0, ge=0)
    sign_changed_edges: int = Field(default=0, ge=0)
    mark_changed_edges: int = Field(default=0, ge=0)
    previous_run_id: UUID | None = None


class CausalDataFreshnessOut(WarrantyQualitySchema):
    source: Literal["manufacturing", "telematics", "service", "warranty", "ingestion", "warning"]
    observed_at: datetime | None = None
    age_minutes: float | None = Field(default=None, ge=0.0)
    status: Literal["AVAILABLE", "NOT_AVAILABLE"]


class CausalRunStatusOut(WarrantyQualitySchema):
    domain: Literal["manufacturing", "telematics"]
    status: str
    run_id: UUID | None = None
    signature: str | None = None
    computed_at: datetime | None = None
    source_from: datetime | None = None
    source_to: datetime | None = None
    source_rows: int | None = Field(default=None, ge=0)
    stable_edge_count: int | None = Field(default=None, ge=0)
    data_freshness: CausalDataFreshnessOut
    model_freshness: datetime | None = None
    graph_delta: CausalGraphDeltaOut = Field(default_factory=CausalGraphDeltaOut)
    last_refresh_at: datetime | None = None
    next_refresh_at: datetime | None = None
    last_error: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    active_run_started_at: datetime | None = None
    active_target_watermark: datetime | None = None
    pending_refresh: bool = False
    pending_target_watermark: datetime | None = None
    last_runtime_seconds: float | None = Field(default=None, ge=0.0)
    last_completed_at: datetime | None = None


class CausalIngestionStatusOut(WarrantyQualitySchema):
    """Physical ingestion state for one domain's own immutable replay source."""

    domain: Literal["manufacturing", "telematics", "service", "warranty"]
    source_table: str
    status: str
    source_available_from: datetime | None = None
    source_available_to: datetime | None = None
    replay_start: datetime | None = None
    replay_cursor: datetime | None = None
    initialized_at: datetime | None = None
    exhausted_at: datetime | None = None
    last_tick_at: datetime | None = None
    tick_count: int = Field(default=0, ge=0)
    last_ingested_timestamp: datetime | None = None
    last_ingested_rows: int = Field(default=0, ge=0)
    rows_ingested_total: int = Field(default=0, ge=0)
    runtime_row_count: int = Field(default=0, ge=0)
    runtime_max_timestamp: datetime | None = None
    last_commit_at: datetime | None = None
    last_error: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CausalWarningStatusOut(WarrantyQualitySchema):
    status: str = "NOT_READY"
    evaluation_run_id: UUID | None = None
    evaluation_signature: str | None = None
    field_evidence_signature: str | None = None
    manufacturing_causal_run_id: UUID | None = None
    telematics_causal_run_id: UUID | None = None
    computed_at: datetime | None = None
    last_evaluated_at: datetime | None = None
    warning_count: int = Field(default=0, ge=0)
    lifecycle_counts: dict[str, int] = Field(default_factory=dict)
    runtime_seconds: float | None = Field(default=None, ge=0.0)
    last_error: str | None = None


class CausalSimulationStatusOut(WarrantyQualitySchema):
    simulation_as_of: datetime
    replay_start: datetime
    replay_end: datetime
    replay_speed: float = Field(ge=0.0)
    paused: bool
    status: Literal["RUNNING", "PAUSED", "COMPLETE"]
    last_tick_at: datetime
    tick_count: int = Field(ge=0)


class CausalSchedulerStatusOut(WarrantyQualitySchema):
    enabled: bool
    last_refresh_at: datetime | None = None
    next_refresh_at: datetime | None = None
    status: str


class WarrantyQualityCausalStatusOut(WarrantyQualitySchema):
    """Read-only replay, data-freshness, model-freshness, and scheduler status."""

    simulation: CausalSimulationStatusOut
    data_freshness: tuple[CausalDataFreshnessOut, ...]
    ingestion: tuple[CausalIngestionStatusOut, ...] = ()
    manufacturing: CausalRunStatusOut
    telematics: CausalRunStatusOut
    warning: CausalWarningStatusOut = Field(default_factory=CausalWarningStatusOut)
    scheduler: CausalSchedulerStatusOut
