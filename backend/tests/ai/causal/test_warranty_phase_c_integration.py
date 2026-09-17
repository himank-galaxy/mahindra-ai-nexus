"""Focused tests for additive manufacturing/telematics warning integration."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from app.schemas.warranty_quality import (
    CausalPathSupportOut,
    EvidenceGraphOut,
)
from app.services.warranty_quality_early_warning import (
    _build_evidence_graph,
    _causal_paths_for_issue,
    _telematics_paths_for_issue,
)

RUN_ID = UUID("78b0f0bd-c66c-4020-963b-673a3d136fec")


def _manufacturing_edge(*, machines: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        source_metric="machine_load",
        target_metric="power_kw",
        scope="ALL_MACHINES",
        consensus_sign="+",
        recurring_machines=3,
        eligible_machines=3,
        recurrence_fraction=1.0,
        sign_agreement=1.0,
        mean_abs_score=0.42,
        median_abs_score=0.40,
        best_q_value=0.01,
        observed_lags=[1, 2],
        machine_ids=machines,
        edge_orientation="DIRECTED",
        consensus_edge_mark="-->",
        mark_agreement=1.0,
    )


def _telematics_edge(
    *,
    source_metric: str = "battery_current_a",
    target_metric: str = "battery_voltage_v",
    vehicle_ids: list[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        source_metric=source_metric,
        target_metric=target_metric,
        scope="ALL_VEHICLES",
        consensus_sign="+",
        eligible_vehicles=24,
        recurring_vehicles=20,
        recurrence_fraction=20 / 24,
        sign_agreement=0.95,
        mean_abs_score=0.31,
        median_abs_score=0.28,
        best_q_value=0.02,
        min_p_value=0.001,
        max_p_value=0.02,
        min_q_value=0.004,
        max_q_value=0.08,
        observed_lags=[1, 2],
        observed_lag_minutes=[5, 10],
        vehicle_ids=vehicle_ids,
        edge_orientation="DIRECTED",
        consensus_edge_mark="-->",
        mark_agreement=1.0,
    )


def test_manufacturing_causal_support_still_requires_exact_lineage_machine() -> None:
    exact_lineage = {
        ("MACHINE_1", "BATCH_1", "LOT_1"),
    }

    assert _causal_paths_for_issue(
        exact_lineage,
        [_manufacturing_edge(machines=["MACHINE_OTHER"])],
        limit=6,
    ) == ()

    paths = _causal_paths_for_issue(
        exact_lineage,
        [_manufacturing_edge(machines=["MACHINE_1"])],
        limit=6,
        causal_run_id=RUN_ID,
        lag_minutes_per_step=5,
    )
    assert len(paths) == 1
    assert paths[0].edge_type == "CAUSAL_DISCOVERED_MANUFACTURING"
    assert paths[0].causal_run_id == RUN_ID
    assert paths[0].observed_lag_minutes == (5, 10)
    assert paths[0].exact_lineage_count == 1


def test_telematics_paths_require_warning_vehicle_support() -> None:
    paths = _telematics_paths_for_issue(
        "ELECTRONIC_CONTROL",
        {"VEHICLE_1"},
        [
            _telematics_edge(vehicle_ids=["VEHICLE_1", "VEHICLE_2"]),
            _telematics_edge(
                source_metric="vehicle_speed_kph",
                target_metric="ambient_temperature_c",
                vehicle_ids=["VEHICLE_OTHER"],
            ),
        ],
        run_id=RUN_ID,
        limit=6,
    )

    assert len(paths) == 1
    assert paths[0].edge_type == "CAUSAL_DISCOVERED_TELEMATICS"
    assert paths[0].supporting_vehicle_ids == ("VEHICLE_1",)
    assert paths[0].overlap_vehicle_count == 1
    assert paths[0].observed_lag_minutes == (5, 10)


def test_empty_issue_family_does_not_force_telematics_candidate() -> None:
    assert _telematics_paths_for_issue(
        "INTERIOR_RATTLE",
        {"VEHICLE_1"},
        [
            _telematics_edge(
                source_metric="vehicle_vibration_mm_s",
                target_metric="vertical_acceleration_g",
                vehicle_ids=["VEHICLE_1"],
            )
        ],
        run_id=RUN_ID,
        limit=6,
    ) == ()


def test_evidence_graph_keeps_causal_and_observed_relations_distinct() -> None:
    issue = {
        "field_lineage_vehicle_keys": {
            ("MACHINE_1", "BATCH_1", "LOT_1", "VEHICLE_1"),
        },
        "service_event_ids": {"SERVICE_1"},
        "warranty_claim_ids": {"CLAIM_1"},
        "service_event_vehicle_ids": {
            "SERVICE_1": {"VEHICLE_1"},
        },
        "warranty_claim_vehicle_ids": {
            "CLAIM_1": {"VEHICLE_1"},
        },
        "warranty_claim_service_event_ids": {
            "CLAIM_1": {"SERVICE_1"},
        },
    }
    manufacturing_paths = _causal_paths_for_issue(
        {("MACHINE_1", "BATCH_1", "LOT_1")},
        [_manufacturing_edge(machines=["MACHINE_1"])],
        limit=6,
        causal_run_id=UUID("5fbba94e-b869-4522-a0c8-f362316b7409"),
    )
    telematics_paths = _telematics_paths_for_issue(
        "ELECTRONIC_CONTROL",
        {"VEHICLE_1"},
        [_telematics_edge(vehicle_ids=["VEHICLE_1"])],
        run_id=RUN_ID,
        limit=6,
    )

    graph = _build_evidence_graph(
        issue_category="ELECTRONIC_CONTROL",
        issue=issue,
        exact_lineages={("MACHINE_1", "BATCH_1", "LOT_1")},
        manufacturing_paths=manufacturing_paths,
        telematics_paths=telematics_paths,
        vehicle_warning_evidence={
            "VEHICLE_1": {
                "max_dtc_count": 2,
                "warning_seen": True,
            }
        },
    )
    graph_out = EvidenceGraphOut.model_validate(graph)
    causal_types = {
        edge.edge_type
        for edge in graph_out.edges
        if edge.edge_type.startswith("CAUSAL_DISCOVERED")
    }
    assert causal_types == {
        "CAUSAL_DISCOVERED_MANUFACTURING",
        "CAUSAL_DISCOVERED_TELEMATICS",
    }
    assert any(
        node.node_type == "DTC_OR_WARNING"
        for node in graph_out.nodes
    )
    assert any(
        node.node_type == "SERVICE_ISSUE"
        and "SERVICE_1" in node.node_id
        for node in graph_out.nodes
    )
    assert any(
        node.node_type == "WARRANTY_CLAIM"
        for node in graph_out.nodes
    )
    assert all(
        edge.edge_type.startswith("CAUSAL_DISCOVERED")
        or edge.edge_type in {
            "LINEAGE",
            "MANUFACTURING_EVIDENCE",
            "TELEMETRY_EVIDENCE",
            "SERVICE_EVIDENCE",
            "WARRANTY_EVIDENCE",
        }
        for edge in graph_out.edges
    )
    assert all(
        "claim_probability" not in edge.metadata
        and "root_cause_domain" not in edge.metadata
        for edge in graph_out.edges
    )


def test_bidirected_edge_renders_as_one_edge_not_two() -> None:
    # A BIDIRECTED LPCMCI relationship is ONE discovered relationship with
    # no preferred direction -- it must render as exactly one evidence-graph
    # edge (with orientation metadata for the frontend to draw double
    # arrowheads), never as two synthesized directed edges.
    issue = {
        "field_lineage_vehicle_keys": set(),
        "service_event_ids": set(),
        "warranty_claim_ids": set(),
        "service_event_vehicle_ids": {},
        "warranty_claim_vehicle_ids": {},
        "warranty_claim_service_event_ids": {},
    }
    bidirected_edge = SimpleNamespace(
        source_metric="machine_load",
        target_metric="power_kw",
        scope="ALL_MACHINES",
        consensus_sign="+",
        recurring_machines=3,
        eligible_machines=3,
        recurrence_fraction=1.0,
        sign_agreement=1.0,
        mean_abs_score=0.42,
        median_abs_score=0.40,
        best_q_value=0.01,
        observed_lags=[0],
        machine_ids=["MACHINE_1"],
        edge_orientation="BIDIRECTED",
        consensus_edge_mark="<->",
        mark_agreement=1.0,
    )
    manufacturing_paths = _causal_paths_for_issue(
        {("MACHINE_1", "BATCH_1", "LOT_1")},
        [bidirected_edge],
        limit=6,
        causal_run_id=RUN_ID,
    )
    assert manufacturing_paths[0].edge_orientation == "BIDIRECTED"
    assert manufacturing_paths[0].edge_mark == "<->"

    graph = _build_evidence_graph(
        issue_category="ELECTRONIC_CONTROL",
        issue=issue,
        exact_lineages={("MACHINE_1", "BATCH_1", "LOT_1")},
        manufacturing_paths=manufacturing_paths,
        telematics_paths=(),
        vehicle_warning_evidence={},
    )
    graph_out = EvidenceGraphOut.model_validate(graph)

    causal_edges = [
        edge
        for edge in graph_out.edges
        if edge.edge_type == "CAUSAL_DISCOVERED_MANUFACTURING"
    ]
    # Exactly one edge -- not one per direction.
    assert len(causal_edges) == 1
    edge = causal_edges[0]
    assert edge.metadata["edge_orientation"] == "BIDIRECTED"
    assert edge.metadata["edge_mark"] == "<->"
    assert edge.metadata["visual_style"] == "double_arrow"


def test_directed_edge_metadata_has_no_visual_style_override() -> None:
    # DIRECTED is the implicit default (solid single arrowhead) -- it must
    # not carry a visual_style key that could be misread as "special".
    issue = {
        "field_lineage_vehicle_keys": set(),
        "service_event_ids": set(),
        "warranty_claim_ids": set(),
        "service_event_vehicle_ids": {},
        "warranty_claim_vehicle_ids": {},
        "warranty_claim_service_event_ids": {},
    }
    manufacturing_paths = _causal_paths_for_issue(
        {("MACHINE_1", "BATCH_1", "LOT_1")},
        [_manufacturing_edge(machines=["MACHINE_1"])],
        limit=6,
        causal_run_id=RUN_ID,
    )
    graph = _build_evidence_graph(
        issue_category="ELECTRONIC_CONTROL",
        issue=issue,
        exact_lineages={("MACHINE_1", "BATCH_1", "LOT_1")},
        manufacturing_paths=manufacturing_paths,
        telematics_paths=(),
        vehicle_warning_evidence={},
    )
    graph_out = EvidenceGraphOut.model_validate(graph)
    causal_edges = [
        edge
        for edge in graph_out.edges
        if edge.edge_type == "CAUSAL_DISCOVERED_MANUFACTURING"
    ]
    assert len(causal_edges) == 1
    assert causal_edges[0].metadata["visual_style"] == "solid"


def test_telematics_path_contract_is_additive_and_schema_validates() -> None:
    path = _telematics_paths_for_issue(
        "TYRE_VIBRATION",
        {"VEHICLE_1"},
        [
            _telematics_edge(
                source_metric="vehicle_vibration_mm_s",
                target_metric="vertical_acceleration_g",
                vehicle_ids=["VEHICLE_1"],
            )
        ],
        run_id=RUN_ID,
        limit=6,
    )[0]

    validated = CausalPathSupportOut.model_validate(path)
    assert validated.causal_domain == "telematics"
    assert validated.overlap_machines == ()
    assert validated.exact_lineage_count == 0
