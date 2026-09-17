"""
Mahindra AI Nexus
Synthetic Data Factory - Full Generation Orchestrator

============================================================
PURPOSE
============================================================

Generate the complete deterministic synthetic business world
by invoking the already-validated individual generators in
dependency order.

This module:

    - loads configuration
    - generates every synthetic domain
    - applies controlled causal scenarios
    - generates evaluator-only causal ground truth
    - generates governance / agent / Copilot datasets
    - returns all generated DataFrames in a structured registry

This module DOES NOT:

    - write CSV files
    - import PostgreSQL
    - duplicate generator business logic
    - read ground truth into runtime datasets
    - invent additional generator aliases
    - modify frozen generators

CSV export belongs to:

    data/scripts/export_csv.py

PostgreSQL import belongs to:

    data/scripts/import_postgres.py

Cross-dataset validation belongs to:

    data/scripts/validate_all.py


============================================================
RUNTIME / GROUND-TRUTH SEPARATION
============================================================

Runtime causal observations:

    synthetic/causal/
        manufacturing_timeseries
        mobility_timeseries

Evaluator-only causal relationships:

    ground_truth/causal/
        manufacturing_causal_edges
        mobility_causal_edges

Controlled intervention truth:

    ground_truth/simulations/
        manufacturing_scenario_events
        manufacturing_scenario_expectations
        mobility_scenario_events
        mobility_scenario_expectations

Copilot runtime/evaluation input:

    synthetic/copilot/
        suggested_prompts
        copilot_eval_questions

Copilot evaluator-only truth:

    ground_truth/copilot/
        copilot_eval_ground_truth


============================================================
IMPORTANT
============================================================

Individual generators are treated as frozen dependencies.

generate_all.py only orchestrates them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


# ============================================================
# CONFIG
# ============================================================

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
    load_scenario_config,
)


# ============================================================
# MASTER
# ============================================================

from data.generators.master.geography import (
    generate_geography,
)

from data.generators.master.vehicle_models import (
    generate_vehicle_models,
)

from data.generators.master.dealers import (
    generate_dealers,
)

from data.generators.master.plants import (
    generate_plant_master,
)

from data.generators.master.machines import (
    generate_machines,
)

from data.generators.master.warehouses import (
    generate_warehouses,
)

from data.generators.master.routes import (
    generate_routes,
)

from data.generators.master.finance_products import (
    generate_finance_products,
)


# ============================================================
# AUTO
# ============================================================

from data.generators.auto.customers import (
    generate_customers,
)

from data.generators.auto.leads import (
    generate_leads,
)

from data.generators.auto.followups import (
    generate_followups,
)

from data.generators.auto.test_drives import (
    generate_test_drives,
)

from data.generators.auto.bookings import (
    generate_bookings,
)

from data.generators.auto.finance_applications import (
    generate_finance_applications,
)

from data.generators.auto.cancellations import (
    generate_cancellations,
)

from data.generators.auto.suppliers import (
    generate_supplier_master,
)

from data.generators.auto.production import (
    generate_production_batches,
)

from data.generators.auto.allocations import (
    generate_allocations,
)

from data.generators.auto.deliveries import (
    generate_deliveries,
)

from data.generators.auto.service import (
    generate_accident_service_events,
    generate_service_events,
)

from data.generators.auto.warranty import (
    generate_warranty_claims,
)

from data.generators.auto.insurance import (
    generate_insurance_claims,
)


# ============================================================
# CAUSAL
# ============================================================

from data.generators.causal.manufacturing_timeseries import (
    generate_manufacturing_timeseries,
)

from data.generators.causal.mobility_timeseries import (
    generate_mobility_timeseries,
)

from data.generators.causal.vehicle_telematics_timeseries import (
    generate_vehicle_telematics_timeseries,
)

from data.generators.causal.scenarios import (
    generate_and_apply_manufacturing_scenarios,
    generate_and_apply_mobility_scenarios,
)

from data.generators.causal.ground_truth import (
    generate_all_causal_ground_truth,
)


# ============================================================
# FINANCE
# ============================================================

from data.generators.finance.customers import (
    generate_finance_customers,
)

from data.generators.finance.loans import (
    generate_loan_accounts,
)

from data.generators.finance.payments import (
    generate_payment_history,
)

from data.generators.finance.cross_sell import (
    generate_cross_sell_events,
)


# ============================================================
# COLLECTIONS
# ============================================================

from data.generators.collections.cases import (
    generate_collection_cases,
)

from data.generators.collections.interactions import (
    generate_collection_interactions,
)


# ============================================================
# LOGISTICS
# ============================================================

from data.generators.logistics.shipments import (
    generate_shipments,
)

from data.generators.logistics.warehouse_events import (
    generate_warehouse_events,
)


# ============================================================
# CIRCULARITY
# ============================================================

from data.generators.circularity.elv import (
    generate_elv_assessments,
)

from data.generators.circularity.rvsf import (
    generate_rvsf_job_cards,
)

from data.generators.circularity.dmrv import (
    generate_dmrv_records,
)

from data.generators.circularity.credits import (
    generate_carbon_credit_listings,
)


# ============================================================
# XR
# ============================================================

from data.generators.xr.sessions import (
    generate_xr,
)


# ============================================================
# GOVERNANCE
# ============================================================

from data.generators.governance.recommendations import (
    generate_recommendations,
)

from data.generators.governance.trust import (
    generate_trust,
)

from data.generators.governance.audit import (
    generate_audit_events,
)


# ============================================================
# AGENTS
# ============================================================

from data.generators.agents.workflow import (
    generate_workflow,
)


# ============================================================
# COPILOT
# ============================================================

from data.generators.copilot.evaluation_cases import (
    generate_evaluation_cases,
)


# ============================================================
# TYPE ALIASES
# ============================================================

DatasetRegistry = dict[
    str,
    Any,
]


# ============================================================
# CAUSAL GROUND-TRUTH KEYS
# ============================================================

MANUFACTURING_CAUSAL_EDGES = (
    "manufacturing_causal_edges"
)

MANUFACTURING_SCENARIO_EVENTS = (
    "manufacturing_scenario_events"
)

MANUFACTURING_SCENARIO_EXPECTATIONS = (
    "manufacturing_scenario_expectations"
)

MOBILITY_CAUSAL_EDGES = (
    "mobility_causal_edges"
)

MOBILITY_SCENARIO_EVENTS = (
    "mobility_scenario_events"
)

MOBILITY_SCENARIO_EXPECTATIONS = (
    "mobility_scenario_expectations"
)


EXPECTED_CAUSAL_GROUND_TRUTH_KEYS = {
    MANUFACTURING_CAUSAL_EDGES,
    MANUFACTURING_SCENARIO_EVENTS,
    MANUFACTURING_SCENARIO_EXPECTATIONS,
    MOBILITY_CAUSAL_EDGES,
    MOBILITY_SCENARIO_EVENTS,
    MOBILITY_SCENARIO_EXPECTATIONS,
}


# ============================================================
# PRINT HELPERS
# ============================================================


def _print_stage(
    stage_number: int,
    title: str,
    verbose: bool,
) -> None:
    """
    Print one orchestration stage header.
    """

    if not verbose:
        return

    print(
        "\n"
        "============================================================"
    )

    print(
        f"{stage_number}. {title}"
    )

    print(
        "============================================================"
    )


def _print_dataset(
    name: str,
    dataframe: pd.DataFrame,
    verbose: bool,
) -> None:
    """
    Print generated row count.
    """

    if not verbose:
        return

    print(
        f"{name}:",
        len(
            dataframe
        ),
    )


# ============================================================
# STRUCTURAL REGISTRY VALIDATION
# ============================================================


def _validate_registry_node(
    node: Mapping[str, Any],
    path: str = "",
) -> tuple[
    int,
    int,
]:
    """
    Validate that every leaf in the generated registry is a
    pandas DataFrame.

    Returns:

        dataset_count
        total_row_count

    This is intentionally structural only.

    Business/FK/cross-domain validation belongs to validate_all.py.
    """

    dataset_count = 0
    total_row_count = 0

    for name, value in node.items():

        current_path = (
            f"{path}/{name}"
            if path
            else str(
                name
            )
        )

        if isinstance(
            value,
            pd.DataFrame,
        ):

            dataset_count += 1

            total_row_count += len(
                value
            )

            continue

        if isinstance(
            value,
            Mapping,
        ):

            (
                child_dataset_count,
                child_row_count,
            ) = _validate_registry_node(
                value,
                current_path,
            )

            dataset_count += (
                child_dataset_count
            )

            total_row_count += (
                child_row_count
            )

            continue

        raise TypeError(
            f"Generated registry leaf {current_path} "
            f"is not a pandas DataFrame. "
            f"Actual type={type(value).__name__}"
        )

    return (
        dataset_count,
        total_row_count,
    )


def _flatten_registry(
    node: Mapping[str, Any],
    path: str = "",
) -> list[
    tuple[
        str,
        pd.DataFrame,
    ]
]:
    """
    Flatten nested registry for summary/reporting.

    Does not copy the DataFrames.
    """

    result: list[
        tuple[
            str,
            pd.DataFrame,
        ]
    ] = []

    for name, value in node.items():

        current_path = (
            f"{path}/{name}"
            if path
            else str(
                name
            )
        )

        if isinstance(
            value,
            pd.DataFrame,
        ):

            result.append(
                (
                    current_path,
                    value,
                )
            )

            continue

        if isinstance(
            value,
            Mapping,
        ):

            result.extend(
                _flatten_registry(
                    value,
                    current_path,
                )
            )

            continue

        raise TypeError(
            f"Unsupported registry value at {current_path}: "
            f"{type(value).__name__}"
        )

    return result


# ============================================================
# CAUSAL GROUND-TRUTH VALIDATION
# ============================================================


def _validate_causal_ground_truth_registry(
    causal_ground_truth: Mapping[str, Any],
    manufacturing_scenario_events: pd.DataFrame,
    mobility_scenario_events: pd.DataFrame,
) -> None:
    """
    Validate the contract returned by the frozen causal
    ground-truth generator.

    Also verify that the scenario-event DataFrames returned by
    the ground-truth layer are identical to the scenario events
    already produced by the scenario generator.

    This prevents accidental divergence while avoiding duplicate
    registry storage.
    """

    actual_keys = set(
        causal_ground_truth.keys()
    )

    missing_keys = (
        EXPECTED_CAUSAL_GROUND_TRUTH_KEYS
        -
        actual_keys
    )

    unexpected_keys = (
        actual_keys
        -
        EXPECTED_CAUSAL_GROUND_TRUTH_KEYS
    )

    if missing_keys:

        raise KeyError(
            "Causal ground-truth output missing required datasets: "
            +
            ", ".join(
                sorted(
                    missing_keys
                )
            )
        )

    if unexpected_keys:

        raise KeyError(
            "Causal ground-truth output contains unexpected datasets: "
            +
            ", ".join(
                sorted(
                    unexpected_keys
                )
            )
        )

    for name in EXPECTED_CAUSAL_GROUND_TRUTH_KEYS:

        dataframe = (
            causal_ground_truth[
                name
            ]
        )

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):

            raise TypeError(
                f"Causal ground-truth dataset {name} "
                "must be a pandas DataFrame"
            )

    pd.testing.assert_frame_equal(
        manufacturing_scenario_events
        .reset_index(
            drop=True
        ),
        causal_ground_truth[
            MANUFACTURING_SCENARIO_EVENTS
        ]
        .reset_index(
            drop=True
        ),
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        mobility_scenario_events
        .reset_index(
            drop=True
        ),
        causal_ground_truth[
            MOBILITY_SCENARIO_EVENTS
        ]
        .reset_index(
            drop=True
        ),
        check_dtype=True,
        check_exact=True,
    )


# ============================================================
# FULL GENERATION
# ============================================================


def generate_all(
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
    scenarios: Mapping[str, Any] | None = None,
    verbose: bool = True,
) -> DatasetRegistry:
    """
    Generate the entire Mahindra AI Nexus synthetic data world.

    Parameters
    ----------
    generation:
        Optional already-loaded generation.yaml mapping.

    distributions:
        Optional already-loaded distributions.yaml mapping.

    scenarios:
        Optional already-loaded scenarios.yaml mapping.

        The current public causal-scenario generator signatures do
        not accept this mapping directly.

        Loading it here still provides fail-fast validation that
        the expected canonical scenario configuration is present.

    verbose:
        Print orchestration progress.

    Returns
    -------
    dict

        {
            "synthetic": {
                ...
            },
            "ground_truth": {
                ...
            },
        }

    Every leaf is a pandas DataFrame.
    """

    # ========================================================
    # CONFIG
    # ========================================================

    if generation is None:

        generation = (
            load_generation_config()
        )

    if distributions is None:

        distributions = (
            load_distribution_config()
        )

    if scenarios is None:

        scenarios = (
            load_scenario_config()
        )

    if not isinstance(
        generation,
        Mapping,
    ):

        raise TypeError(
            "generation configuration must be a mapping"
        )

    if not isinstance(
        distributions,
        Mapping,
    ):

        raise TypeError(
            "distributions configuration must be a mapping"
        )

    if not isinstance(
        scenarios,
        Mapping,
    ):

        raise TypeError(
            "scenarios configuration must be a mapping"
        )

    if verbose:

        print(
            "\n"
            "============================================================\n"
            "MAHINDRA AI NEXUS - SYNTHETIC DATA FACTORY\n"
            "FULL GENERATION RUN\n"
            "============================================================"
        )

        print(
            "Seed:",
            generation.get(
                "seed"
            ),
        )

        print(
            "Generator version:",
            generation.get(
                "generator_version"
            ),
        )

        print(
            "Data origin:",
            generation.get(
                "provenance",
                {},
            ).get(
                "data_origin"
            ),
        )

    # ========================================================
    # 1. MASTER
    # ========================================================

    _print_stage(
        1,
        "MASTER DATA",
        verbose,
    )

    (
        regions,
        cities,
    ) = generate_geography(
        generation=
            generation,

        distributions=
            distributions,
    )

    vehicle_models = generate_vehicle_models(
        generation=
            generation,

        distributions=
            distributions,
    )

    dealers = generate_dealers(
        regions=
            regions,

        cities=
            cities,

        generation=
            generation,
    )

    (
        plants,
        production_lines,
    ) = generate_plant_master(
        geography_cities=
            cities,

        generation=
            generation,
    )

    machines = generate_machines(
        production_lines=
            production_lines,

        generation=
            generation,
    )

    warehouses = generate_warehouses(
        geography_cities=
            cities,

        generation=
            generation,
    )

    routes = generate_routes(
        warehouses=
            warehouses,

        generation=
            generation,
    )

    finance_products = generate_finance_products(
        generation=
            generation,
    )

    for name, dataframe in (
        (
            "regions",
            regions,
        ),
        (
            "cities",
            cities,
        ),
        (
            "vehicle_models",
            vehicle_models,
        ),
        (
            "dealers",
            dealers,
        ),
        (
            "plants",
            plants,
        ),
        (
            "production_lines",
            production_lines,
        ),
        (
            "machines",
            machines,
        ),
        (
            "warehouses",
            warehouses,
        ),
        (
            "routes",
            routes,
        ),
        (
            "finance_products",
            finance_products,
        ),
    ):

        _print_dataset(
            name,
            dataframe,
            verbose,
        )

    # ========================================================
    # 2. AUTO
    # ========================================================

    _print_stage(
        2,
        "AUTO",
        verbose,
    )

    customers = generate_customers(
        regions=
            regions,

        cities=
            cities,

        vehicle_models=
            vehicle_models,

        generation=
            generation,

        distributions=
            distributions,
    )

    leads = generate_leads(
        customers=
            customers,

        dealers=
            dealers,

        vehicle_models=
            vehicle_models,

        generation=
            generation,

        distributions=
            distributions,
    )

    followups = generate_followups(
        leads=
            leads,

        dealers=
            dealers,

        generation=
            generation,

        distributions=
            distributions,
    )

    test_drives = generate_test_drives(
        leads=
            leads,

        followups=
            followups,

        generation=
            generation,

        distributions=
            distributions,
    )

    bookings = generate_bookings(
        customers=
            customers,

        leads=
            leads,

        followups=
            followups,

        test_drives=
            test_drives,

        vehicle_models=
            vehicle_models,

        generation=
            generation,

        distributions=
            distributions,
    )

    finance_applications = generate_finance_applications(
        bookings=
            bookings,

        customers=
            customers,

        generation=
            generation,

        distributions=
            distributions,
    )

    cancellations = generate_cancellations(
        bookings=
            bookings,

        finance_applications=
            finance_applications,

        generation=
            generation,

        distributions=
            distributions,
    )

    (
        suppliers,
        supplier_lots,
    ) = generate_supplier_master(
        cities=
            cities,

        generation=
            generation,

        distributions=
            distributions,
    )

    production_batches = generate_production_batches(
        plants=
            plants,

        production_lines=
            production_lines,

        machines=
            machines,

        vehicle_models=
            vehicle_models,

        suppliers=
            suppliers,

        supplier_lots=
            supplier_lots,

        generation=
            generation,
    )

    allocations = generate_allocations(
        bookings=
            bookings,

        cancellations=
            cancellations,

        production_batches=
            production_batches,

        dealers=
            dealers,

        finance_applications=
            finance_applications,

        generation=
            generation,
    )

    deliveries = generate_deliveries(
        bookings=
            bookings,

        allocations=
            allocations,

        generation=
            generation,
    )

    service_events = generate_service_events(
        deliveries=
            deliveries,

        generation=
            generation,
    )

    warranty_claims = generate_warranty_claims(
        service_events=
            service_events,

        generation=
            generation,
    )

    for name, dataframe in (
        (
            "customers",
            customers,
        ),
        (
            "leads",
            leads,
        ),
        (
            "followups",
            followups,
        ),
        (
            "test_drives",
            test_drives,
        ),
        (
            "bookings",
            bookings,
        ),
        (
            "finance_applications",
            finance_applications,
        ),
        (
            "cancellations",
            cancellations,
        ),
        (
            "suppliers",
            suppliers,
        ),
        (
            "supplier_lots",
            supplier_lots,
        ),
        (
            "production_batches",
            production_batches,
        ),
        (
            "allocations",
            allocations,
        ),
        (
            "deliveries",
            deliveries,
        ),
        (
            "service_events",
            service_events,
        ),
        (
            "warranty_claims",
            warranty_claims,
        ),
    ):

        _print_dataset(
            name,
            dataframe,
            verbose,
        )

    # ========================================================
    # 3. CAUSAL BASE OBSERVATIONS
    # ========================================================

    _print_stage(
        3,
        "CAUSAL OBSERVATIONS",
        verbose,
    )

    manufacturing_baseline = (
        generate_manufacturing_timeseries(
            plants=
                plants,

            production_lines=
                production_lines,

            machines=
                machines,

            production_batches=
                production_batches,

            generation=
                generation,

            distributions=
                distributions,
        )
    )

    mobility_baseline = generate_mobility_timeseries(
        regions=
            regions,

        leads=
            leads,

        followups=
            followups,

        test_drives=
            test_drives,

        bookings=
            bookings,

        finance_applications=
            finance_applications,

        cancellations=
            cancellations,

        allocations=
            allocations,

        deliveries=
            deliveries,

        service_events=
            service_events,

        warranty_claims=
            warranty_claims,

        generation=
            generation,
    )

    # To pass manufacturing_runtime to telematics, we must move telematics generation BELOW manufacturing scenarios
    # (or use manufacturing_baseline). manufacturing_baseline has the same batches and timestamps, so we can use that.
    vehicle_telematics_timeseries = (
        generate_vehicle_telematics_timeseries(
            deliveries=deliveries,
            service_events=service_events,
            warranty_claims=warranty_claims,
            production_batches=production_batches,
            supplier_lots=supplier_lots,
            plants=plants,
            production_lines=production_lines,
            manufacturing_timeseries=manufacturing_baseline,
            generation=generation,
        )
    )

    _print_dataset(
        "manufacturing_baseline",
        manufacturing_baseline,
        verbose,
    )

    _print_dataset(
        "mobility_baseline",
        mobility_baseline,
        verbose,
    )

    _print_dataset(
        "vehicle_telematics_timeseries",
        vehicle_telematics_timeseries,
        verbose,
    )

    # ========================================================
    # 4. CONTROLLED CAUSAL SCENARIOS
    # ========================================================

    _print_stage(
        4,
        "CONTROLLED CAUSAL SCENARIOS",
        verbose,
    )

    (
        manufacturing_runtime,
        manufacturing_scenario_events,
    ) = generate_and_apply_manufacturing_scenarios(
        manufacturing_timeseries=
            manufacturing_baseline,

        generation=
            generation,
    )

    (
        mobility_runtime,
        mobility_scenario_events,
    ) = generate_and_apply_mobility_scenarios(
        mobility_timeseries=
            mobility_baseline,

        generation=
            generation,
    )

    _print_dataset(
        "manufacturing_runtime",
        manufacturing_runtime,
        verbose,
    )

    _print_dataset(
        "manufacturing_scenario_events",
        manufacturing_scenario_events,
        verbose,
    )

    _print_dataset(
        "mobility_runtime",
        mobility_runtime,
        verbose,
    )

    _print_dataset(
        "mobility_scenario_events",
        mobility_scenario_events,
        verbose,
    )

    # ========================================================
    # 5. CAUSAL GROUND TRUTH
    # ========================================================

    _print_stage(
        5,
        "CAUSAL GROUND TRUTH",
        verbose,
    )

    causal_ground_truth = (
        generate_all_causal_ground_truth(
            manufacturing_runtime=
                manufacturing_runtime,

            manufacturing_scenario_events=
                manufacturing_scenario_events,

            mobility_runtime=
                mobility_runtime,

            mobility_scenario_events=
                mobility_scenario_events,
        )
    )

    if not isinstance(
        causal_ground_truth,
        Mapping,
    ):

        raise TypeError(
            "generate_all_causal_ground_truth() "
            "must return a mapping"
        )

    _validate_causal_ground_truth_registry(
        causal_ground_truth=
            causal_ground_truth,

        manufacturing_scenario_events=
            manufacturing_scenario_events,

        mobility_scenario_events=
            mobility_scenario_events,
    )

    for name, dataframe in (
        causal_ground_truth.items()
    ):

        _print_dataset(
            str(
                name
            ),
            dataframe,
            verbose,
        )

    # ========================================================
    # 6. FINANCE
    # ========================================================

    _print_stage(
        6,
        "FINANCE",
        verbose,
    )

    finance_customers = generate_finance_customers(
        regions=
            regions,

        cities=
            cities,

        generation=
            generation,

        distributions=
            distributions,
    )

    loan_accounts = generate_loan_accounts(
        finance_customers=
            finance_customers,

        finance_products=
            finance_products,

        generation=
            generation,

        distributions=
            distributions,
    )

    payment_history = generate_payment_history(
        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        generation=
            generation,

        distributions=
            distributions,
    )

    cross_sell_events = generate_cross_sell_events(
        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        finance_products=
            finance_products,

        generation=
            generation,

        distributions=
            distributions,
    )

    for name, dataframe in (
        (
            "finance_customers",
            finance_customers,
        ),
        (
            "loan_accounts",
            loan_accounts,
        ),
        (
            "payment_history",
            payment_history,
        ),
        (
            "cross_sell_events",
            cross_sell_events,
        ),
    ):

        _print_dataset(
            name,
            dataframe,
            verbose,
        )

    # ========================================================
    # 7. COLLECTIONS
    # ========================================================

    _print_stage(
        7,
        "COLLECTIONS",
        verbose,
    )

    collection_cases = generate_collection_cases(
        finance_customers=
            finance_customers,

        loan_accounts=
            loan_accounts,

        payment_history=
            payment_history,

        generation=
            generation,
    )

    collection_interactions = (
        generate_collection_interactions(
            collection_cases=
                collection_cases,

            finance_customers=
                finance_customers,

            loan_accounts=
                loan_accounts,

            payment_history=
                payment_history,

            generation=
                generation,

            distributions=
                distributions,
        )
    )

    _print_dataset(
        "collection_cases",
        collection_cases,
        verbose,
    )

    _print_dataset(
        "collection_interactions",
        collection_interactions,
        verbose,
    )

    # ========================================================
    # 8. LOGISTICS
    # ========================================================

    _print_stage(
        8,
        "LOGISTICS",
        verbose,
    )

    shipments = generate_shipments(
        routes=
            routes,

        warehouses=
            warehouses,

        generation=
            generation,

        distributions=
            distributions,
    )

    warehouse_events = generate_warehouse_events(
        shipments=
            shipments,

        warehouses=
            warehouses,

        generation=
            generation,
    )

    _print_dataset(
        "shipments",
        shipments,
        verbose,
    )

    _print_dataset(
        "warehouse_events",
        warehouse_events,
        verbose,
    )

    # ========================================================
    # 9. CIRCULARITY
    # ========================================================

    _print_stage(
        9,
        "CIRCULARITY",
        verbose,
    )

    elv_assessments = generate_elv_assessments(
        vehicle_models=
            vehicle_models,

        cities=
            cities,

        regions=
            regions,

        generation=
            generation,

        distributions=
            distributions,
    )

    rvsf_job_cards = generate_rvsf_job_cards(
        elv_assessments=
            elv_assessments,

        generation=
            generation,
    )

    dmrv_records = generate_dmrv_records(
        rvsf_job_cards=
            rvsf_job_cards,

        generation=
            generation,
    )

    credit_listings = (
        generate_carbon_credit_listings(
            elv_assessments=
                elv_assessments,

            rvsf_job_cards=
                rvsf_job_cards,

            dmrv_records=
                dmrv_records,

            generation=
                generation,
        )
    )

    for name, dataframe in (
        (
            "elv_assessments",
            elv_assessments,
        ),
        (
            "rvsf_job_cards",
            rvsf_job_cards,
        ),
        (
            "dmrv_records",
            dmrv_records,
        ),
        (
            "credit_listings",
            credit_listings,
        ),
    ):

        _print_dataset(
            name,
            dataframe,
            verbose,
        )

    # ========================================================
    # 10. XR
    # ========================================================

    _print_stage(
        10,
        "XR",
        verbose,
    )

    (
        xr_experiences,
        xr_sessions,
    ) = generate_xr(
        vehicle_models=
            vehicle_models,

        generation=
            generation,
    )

    _print_dataset(
        "xr_experiences",
        xr_experiences,
        verbose,
    )

    _print_dataset(
        "xr_sessions",
        xr_sessions,
        verbose,
    )

    # ========================================================
    # 11. GOVERNANCE
    # ========================================================

    _print_stage(
        11,
        "GOVERNANCE",
        verbose,
    )

    recommendations = generate_recommendations(
        allocations=
            allocations,

        cross_sell_events=
            cross_sell_events,

        collection_cases=
            collection_cases,

        shipments=
            shipments,

        credit_listings=
            credit_listings,

        generation=
            generation,
    )

    (
        compliance_checks,
        trust_decisions,
        human_reviews,
    ) = generate_trust(
        recommendations=
            recommendations,

        generation=
            generation,
    )

    audit_events = generate_audit_events(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        human_reviews=
            human_reviews,

        generation=
            generation,
    )

    for name, dataframe in (
        (
            "recommendations",
            recommendations,
        ),
        (
            "compliance_checks",
            compliance_checks,
        ),
        (
            "trust_decisions",
            trust_decisions,
        ),
        (
            "human_reviews",
            human_reviews,
        ),
        (
            "audit_events",
            audit_events,
        ),
    ):

        _print_dataset(
            name,
            dataframe,
            verbose,
        )

    # ========================================================
    # 12. AGENT WORKFLOWS
    # ========================================================

    _print_stage(
        12,
        "AGENT WORKFLOWS",
        verbose,
    )

    (
        agent_workflow_runs,
        agent_events,
        action_outcomes,
    ) = generate_workflow(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        human_reviews=
            human_reviews,

        audit_events=
            audit_events,

        generation=
            generation,
    )

    _print_dataset(
        "agent_workflow_runs",
        agent_workflow_runs,
        verbose,
    )

    _print_dataset(
        "agent_events",
        agent_events,
        verbose,
    )

    _print_dataset(
        "action_outcomes",
        action_outcomes,
        verbose,
    )

    # ========================================================
    # 13. COPILOT EVALUATION
    #
    # IMPORTANT:
    # Copilot receives runtime manufacturing observations.
    #
    # It never receives:
    #
    #     manufacturing_causal_edges
    #     mobility_causal_edges
    #     scenario expectations
    #     other evaluator-only ground truth
    # ========================================================

    _print_stage(
        13,
        "COPILOT EVALUATION",
        verbose,
    )

    (
        suggested_prompts,
        copilot_eval_questions,
        copilot_eval_ground_truth,
    ) = generate_evaluation_cases(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        audit_events=
            audit_events,

        workflow_runs=
            agent_workflow_runs,

        agent_events=
            agent_events,

        action_outcomes=
            action_outcomes,

        manufacturing_timeseries=
            manufacturing_runtime,

        warranty_claims=
            warranty_claims,

        generation=
            generation,
    )

    _print_dataset(
        "suggested_prompts",
        suggested_prompts,
        verbose,
    )

    _print_dataset(
        "copilot_eval_questions",
        copilot_eval_questions,
        verbose,
    )

    _print_dataset(
        "copilot_eval_ground_truth",
        copilot_eval_ground_truth,
        verbose,
    )

    # ========================================================
    # 14. REGISTRY
    # ========================================================

    _print_stage(
        14,
        "BUILD DATASET REGISTRY",
        verbose,
    )

    registry: DatasetRegistry = {
        "synthetic": {

            # =================================================
            # MASTER
            # =================================================

            "master": {
                "regions":
                    regions,

                "cities":
                    cities,

                "vehicle_models":
                    vehicle_models,

                "dealers":
                    dealers,

                "plants":
                    plants,

                "production_lines":
                    production_lines,

                "machines":
                    machines,

                "warehouses":
                    warehouses,

                "routes":
                    routes,

                "finance_products":
                    finance_products,
            },

            # =================================================
            # AUTO
            # =================================================

            "auto": {
                "customers":
                    customers,

                "leads":
                    leads,

                "followups":
                    followups,

                "test_drives":
                    test_drives,

                "bookings":
                    bookings,

                "finance_applications":
                    finance_applications,

                "cancellations":
                    cancellations,

                "suppliers":
                    suppliers,

                "supplier_lots":
                    supplier_lots,

                "production_batches":
                    production_batches,

                "allocations":
                    allocations,

                "deliveries":
                    deliveries,

                "service_events":
                    service_events,

                "warranty_claims":
                    warranty_claims,
            },

            # =================================================
            # CAUSAL RUNTIME OBSERVATIONS
            #
            # Ground truth is not exposed here.
            # =================================================

            "causal": {
                "manufacturing_timeseries":
                    manufacturing_runtime,

                "mobility_timeseries":
                    mobility_runtime,

                "vehicle_telematics_timeseries":
                    vehicle_telematics_timeseries,
            },

            # =================================================
            # FINANCE
            # =================================================

            "finance": {
                "finance_customers":
                    finance_customers,

                "loan_accounts":
                    loan_accounts,

                "payment_history":
                    payment_history,

                "cross_sell_events":
                    cross_sell_events,
            },

            # =================================================
            # COLLECTIONS
            # =================================================

            "collections": {
                "collection_cases":
                    collection_cases,

                "collection_interactions":
                    collection_interactions,
            },

            # =================================================
            # LOGISTICS
            # =================================================

            "logistics": {
                "shipments":
                    shipments,

                "warehouse_events":
                    warehouse_events,
            },

            # =================================================
            # CIRCULARITY
            # =================================================

            "circularity": {
                "elv_assessments":
                    elv_assessments,

                "rvsf_job_cards":
                    rvsf_job_cards,

                "dmrv_records":
                    dmrv_records,

                "credit_listings":
                    credit_listings,
            },

            # =================================================
            # XR
            # =================================================

            "xr": {
                "xr_experiences":
                    xr_experiences,

                "xr_sessions":
                    xr_sessions,
            },

            # =================================================
            # GOVERNANCE
            #
            # action_outcomes remains runtime governance
            # evidence for Recommend -> Approve -> Act -> Learn.
            # =================================================

            "governance": {
                "recommendations":
                    recommendations,

                "compliance_checks":
                    compliance_checks,

                "trust_decisions":
                    trust_decisions,

                "human_reviews":
                    human_reviews,

                "audit_events":
                    audit_events,

                "action_outcomes":
                    action_outcomes,
            },

            # =================================================
            # AGENTS
            # =================================================

            "agents": {
                "agent_workflow_runs":
                    agent_workflow_runs,

                "agent_events":
                    agent_events,
            },

            # =================================================
            # COPILOT RUNTIME / EVALUATION INPUT
            # =================================================

            "copilot": {
                "suggested_prompts":
                    suggested_prompts,

                "copilot_eval_questions":
                    copilot_eval_questions,
            },
        },

        # =====================================================
        # EVALUATOR-ONLY GROUND TRUTH
        # =====================================================

        "ground_truth": {

            # =================================================
            # CAUSAL RELATIONSHIPS
            #
            # ONLY known synthetic causal edges live here.
            # =================================================

            "causal": {
                MANUFACTURING_CAUSAL_EDGES:
                    causal_ground_truth[
                        MANUFACTURING_CAUSAL_EDGES
                    ],

                MOBILITY_CAUSAL_EDGES:
                    causal_ground_truth[
                        MOBILITY_CAUSAL_EDGES
                    ],
            },

            # =================================================
            # CONTROLLED SCENARIOS / EXPECTED EFFECTS
            #
            # Scenario events and scenario expectations live
            # together here and are not duplicated elsewhere.
            # =================================================

            "simulations": {
                MANUFACTURING_SCENARIO_EVENTS:
                    causal_ground_truth[
                        MANUFACTURING_SCENARIO_EVENTS
                    ],

                MANUFACTURING_SCENARIO_EXPECTATIONS:
                    causal_ground_truth[
                        MANUFACTURING_SCENARIO_EXPECTATIONS
                    ],

                MOBILITY_SCENARIO_EVENTS:
                    causal_ground_truth[
                        MOBILITY_SCENARIO_EVENTS
                    ],

                MOBILITY_SCENARIO_EXPECTATIONS:
                    causal_ground_truth[
                        MOBILITY_SCENARIO_EXPECTATIONS
                    ],
            },

            # =================================================
            # COPILOT EVALUATOR-ONLY TRUTH
            # =================================================

            "copilot": {
                "copilot_eval_ground_truth":
                    copilot_eval_ground_truth,
            },
        },
    }

    (
        dataset_count,
        total_row_count,
    ) = _validate_registry_node(
        registry
    )

    if verbose:

        print(
            "Registered DataFrames:",
            dataset_count,
        )

        print(
            "Registered rows:",
            total_row_count,
        )

    return registry


# ============================================================
# SUMMARY
# ============================================================


def print_generation_summary(
    registry: Mapping[str, Any],
) -> None:
    """
    Print every generated dataset and row count.
    """

    flattened = _flatten_registry(
        registry
    )

    print(
        "\n"
        "============================================================\n"
        "FULL GENERATION SUMMARY\n"
        "============================================================"
    )

    for path, dataframe in flattened:

        print(
            f"{path:<70}",
            f"{len(dataframe):>10}",
        )

    print(
        "\n"
        "------------------------------------------------------------"
    )

    print(
        "Total DataFrames:",
        len(
            flattened
        ),
    )

    print(
        "Total registered rows:",
        sum(
            len(
                dataframe
            )
            for _, dataframe
            in flattened
        ),
    )


# ============================================================
# CLI
# ============================================================


def main() -> None:
    """
    Run the complete factory in memory.

    No files are written here.
    """

    registry = generate_all(
        verbose=True,
    )

    print_generation_summary(
        registry
    )

    print(
        "\n"
        "============================================================\n"
        "GENERATE ALL: PASS\n"
        "============================================================"
    )

    print(
        "All generator dependencies completed successfully."
    )

    print(
        "No CSV files were written."
    )

    print(
        "No PostgreSQL writes were performed."
    )

    print(
        "\nNext stage: data/scripts/validate_all.py"
    )


if __name__ == "__main__":
    main()