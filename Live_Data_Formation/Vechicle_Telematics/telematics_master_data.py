"""
Master-data bootstrap for the live vehicle-telematics pipeline.

Reuses the existing, unmodified Synthetic Data Factory generators to
build the static "delivered vehicle" pool that telemetry rows are
generated for: customers, leads, followups, test drives, bookings,
finance applications, cancellations, allocations, deliveries, and
the manufacturing/production-batch master data those deliveries are
linked to.

This module does NOT modify anything under Mahindra AI Nexus/data/.
It only imports and calls the already-existing generator functions.

The delivered-vehicle roster does not change minute to minute in
real operations, so it is built once per process start and reused
for every live telemetry tick.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

NEXUS_ROOT = Path(__file__).resolve().parents[2]

if str(NEXUS_ROOT) not in sys.path:
    sys.path.insert(0, str(NEXUS_ROOT))

from data.generators.common.helpers import (
    load_generation_config,
    load_distribution_config,
)
from data.generators.master.geography import generate_geography
from data.generators.master.vehicle_models import generate_vehicle_models
from data.generators.master.dealers import generate_dealers
from data.generators.master.plants import generate_plant_master
from data.generators.master.machines import generate_machine_master
from data.generators.auto.suppliers import generate_supplier_master
from data.generators.auto.production import generate_production_batches
from data.generators.auto.customers import generate_customers
from data.generators.auto.leads import generate_leads
from data.generators.auto.followups import generate_followups
from data.generators.auto.test_drives import generate_test_drives
from data.generators.auto.bookings import generate_bookings
from data.generators.auto.finance_applications import (
    generate_finance_applications,
)
from data.generators.auto.cancellations import generate_cancellations
from data.generators.auto.allocations import generate_allocations
from data.generators.auto.deliveries import generate_deliveries


def build_delivered_vehicle_pool() -> dict[str, Any]:
    """
    Build the full static context needed to generate live telemetry:
    a roster of DELIVERED vehicles with complete production lineage
    (vehicle model, variant, production batch, supplier lot, plant,
    production line, quality scores), plus the supporting master
    tables required to validate/attach that lineage.

    Returns a dict with:
        deliveries, production_batches, supplier_lots, plants,
        production_lines, generation
    """

    generation = load_generation_config()
    distributions = load_distribution_config()

    regions, cities = generate_geography()

    vehicle_models = generate_vehicle_models(generation=generation)

    dealers = generate_dealers(
        regions=regions,
        cities=cities,
        generation=generation,
    )

    plants, production_lines = generate_plant_master(
        geography_cities=cities,
        generation=generation,
    )

    machines = generate_machine_master(
        production_lines=production_lines,
        generation=generation,
    )

    suppliers, supplier_lots = generate_supplier_master(
        cities=cities,
        generation=generation,
    )

    production_batches = generate_production_batches(
        plants=plants,
        production_lines=production_lines,
        machines=machines,
        vehicle_models=vehicle_models,
        suppliers=suppliers,
        supplier_lots=supplier_lots,
        generation=generation,
    )

    customers = generate_customers(
        regions=regions,
        cities=cities,
        vehicle_models=vehicle_models,
        generation=generation,
        distributions=distributions,
    )

    leads = generate_leads(
        customers=customers,
        dealers=dealers,
        vehicle_models=vehicle_models,
        generation=generation,
        distributions=distributions,
    )

    followups = generate_followups(
        leads=leads,
        dealers=dealers,
        generation=generation,
        distributions=distributions,
    )

    test_drives = generate_test_drives(
        leads=leads,
        followups=followups,
        generation=generation,
        distributions=distributions,
    )

    bookings = generate_bookings(
        customers=customers,
        leads=leads,
        followups=followups,
        test_drives=test_drives,
        vehicle_models=vehicle_models,
        generation=generation,
        distributions=distributions,
    )

    finance_applications = generate_finance_applications(
        bookings=bookings,
        customers=customers,
        generation=generation,
        distributions=distributions,
    )

    cancellations = generate_cancellations(
        bookings=bookings,
        finance_applications=finance_applications,
        generation=generation,
        distributions=distributions,
    )

    allocations = generate_allocations(
        bookings=bookings,
        cancellations=cancellations,
        production_batches=production_batches,
        dealers=dealers,
        finance_applications=finance_applications,
        generation=generation,
    )

    deliveries = generate_deliveries(
        bookings=bookings,
        allocations=allocations,
        generation=generation,
    )

    delivered = deliveries[
        deliveries["delivery_status"].astype(str).str.upper()
        == "DELIVERED"
    ].reset_index(drop=True)

    return {
        "deliveries": delivered,
        "production_batches": production_batches,
        "supplier_lots": supplier_lots,
        "plants": plants,
        "production_lines": production_lines,
        "generation": generation,
    }
