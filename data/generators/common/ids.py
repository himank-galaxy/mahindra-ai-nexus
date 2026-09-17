"""
Central ID-generation utilities for the Mahindra AI Nexus
Synthetic Data Factory.

All synthetic IDs should be generated from this module instead of
creating custom ID logic inside individual generators.
"""

from __future__ import annotations

import re
import unicodedata


# ------------------------------------------------------------------
# Standard prefixes used across synthetic datasets
# ------------------------------------------------------------------

ENTITY_PREFIXES = {
    # Master
    "dealer": "DEALER_SYN",
    "plant": "PLANT_SYN",
    "production_line": "LINE_SYN",
    "machine": "MACHINE_SYN",
    "warehouse": "WH_SYN",
    "supplier": "SUPPLIER_SYN",
    "supplier_lot": "LOT_SYN",

    # Auto / Dealer
    "customer": "CUSTOMER_SYN",
    "lead": "LEAD_SYN",
    "followup": "FOLLOWUP_SYN",
    "test_drive": "TD_SYN",
    "booking": "BOOK_SYN",
    "finance_application": "FINAPP_SYN",
    "cancellation": "CANCEL_SYN",
    "allocation": "ALLOC_SYN",
    "delivery": "DELIVERY_SYN",
    "service_event": "SERVICE_SYN",
    "warranty_claim": "WARRANTY_SYN",
    "insurance_claim": "INSCLAIM_SYN",
    "production_batch": "BATCH_SYN",

    # Finance
    "finance_customer": "FINCUST_SYN",
    "loan_account": "LOAN_SYN",
    "payment": "PAYMENT_SYN",
    "cross_sell_event": "CROSSSELL_SYN",

    # Collections
    "collections_case": "COLL_SYN",
    "collections_interaction": "COLLINT_SYN",

    # Logistics
    "route": "ROUTE_SYN",
    "shipment": "SHIP_SYN",
    "warehouse_event": "WHEVT_SYN",

    # Circularity
    "elv_assessment": "ELV_SYN",
    "rvsf_job": "RVSF_SYN",
    "dmrv_record": "DMRV_SYN",
    "credit": "CREDIT_SYN",

    # Governance
    "recommendation": "REC_SYN",
    "decision": "DECISION_SYN",
    "compliance_check": "COMPCHK_SYN",
    "audit_event": "AUDIT_SYN",
    "human_review": "REVIEW_SYN",
    "action_outcome": "OUTCOME_SYN",

    # Agents
    "workflow_run": "WORKFLOW_SYN",
    "agent_run": "AGENTRUN_SYN",

    # XR
    "xr_session": "XRSESSION_SYN",

    # Copilot
    "copilot_case": "COPILOT_SYN",
}


def generate_id(
    prefix: str,
    number: int,
    width: int = 6,
) -> str:
    """
    Generate a zero-padded synthetic ID.

    Example:
        generate_id("LEAD_SYN", 1)
        -> LEAD_SYN_000001

        generate_id("BOOK_SYN", 57)
        -> BOOK_SYN_000057
    """

    if not prefix:
        raise ValueError("prefix cannot be empty")

    if not isinstance(number, int):
        raise TypeError("number must be an integer")

    if number < 0:
        raise ValueError("number must be >= 0")

    if width <= 0:
        raise ValueError("width must be > 0")

    return f"{prefix}_{number:0{width}d}"


def make_entity_id(
    entity_type: str,
    number: int,
    width: int = 6,
) -> str:
    """
    Generate an ID using a registered entity type.

    Example:
        make_entity_id("lead", 1)
        -> LEAD_SYN_000001

        make_entity_id("shipment", 25)
        -> SHIP_SYN_000025
    """

    if entity_type not in ENTITY_PREFIXES:
        valid = ", ".join(sorted(ENTITY_PREFIXES))
        raise KeyError(
            f"Unknown entity_type '{entity_type}'. "
            f"Valid entity types: {valid}"
        )

    prefix = ENTITY_PREFIXES[entity_type]

    return generate_id(
        prefix=prefix,
        number=number,
        width=width,
    )


def slug_token(value: str) -> str:
    """
    Convert a name into a stable uppercase identifier token.

    Examples:
        "Pune"       -> PUNE
        "XUV 3XO"    -> XUV_3XO
        "Scorpio-N"  -> SCORPIO_N
    """

    if not value:
        raise ValueError("value cannot be empty")

    normalized = unicodedata.normalize(
        "NFKD",
        str(value),
    )

    normalized = (
        normalized
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
    )

    normalized = re.sub(
        r"[^A-Z0-9]+",
        "_",
        normalized,
    )

    normalized = normalized.strip("_")

    if not normalized:
        raise ValueError(
            f"Could not create identifier token from {value!r}"
        )

    return normalized


def make_region_id(region_name: str) -> str:
    """
    Example:
        West -> REG_WEST
    """

    return f"REG_{slug_token(region_name)}"


def make_city_id(city_name: str) -> str:
    """
    Example:
        Pune -> CITY_PUNE
    """

    return f"CITY_{slug_token(city_name)}"


def make_vehicle_model_id(model_name: str) -> str:
    """
    Examples:
        XUV700    -> VEH_XUV700
        XUV 3XO   -> VEH_XUV_3XO
        Scorpio-N -> VEH_SCORPIO_N
    """

    return f"VEH_{slug_token(model_name)}"