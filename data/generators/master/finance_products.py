"""
Finance Product master-data generator for Mahindra AI Nexus.

Generates:
- Stable finance-product reference records.

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save the returned DataFrame as:

    data/synthetic/master/finance_products.csv

IMPORTANT:
Loan limits, interest rates, LTV values and tenure ranges below
are synthetic engineering assumptions for the PoC.
They are NOT actual Mahindra Finance commercial terms.
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    generate_id,
)


# ============================================================
# SYNTHETIC FINANCE PRODUCT MASTER
#
# These are stable reference/configuration records.
# They are not randomly regenerated business events.
# ============================================================

FINANCE_PRODUCT_TEMPLATES: list[
    dict[str, Any]
] = [

    {
        "product_code": "AUTO_LOAN_NEW",
        "product_name": "New Vehicle Loan",
        "product_category": "AUTO_FINANCE",
        "secured": True,
        "min_loan_amount_inr": 300000,
        "max_loan_amount_inr": 3000000,
        "min_tenure_months": 12,
        "max_tenure_months": 84,
        "base_interest_rate_pct": 9.25,
        "max_ltv_pct": 90.0,
        "target_segment": "RETAIL_AUTO",
    },

    {
        "product_code": "AUTO_LOAN_USED",
        "product_name": "Used Vehicle Loan",
        "product_category": "AUTO_FINANCE",
        "secured": True,
        "min_loan_amount_inr": 200000,
        "max_loan_amount_inr": 1800000,
        "min_tenure_months": 12,
        "max_tenure_months": 60,
        "base_interest_rate_pct": 11.25,
        "max_ltv_pct": 80.0,
        "target_segment": "RETAIL_AUTO",
    },

    {
        "product_code": "TRACTOR_LOAN",
        "product_name": "Tractor Finance",
        "product_category": "RURAL_FINANCE",
        "secured": True,
        "min_loan_amount_inr": 250000,
        "max_loan_amount_inr": 2000000,
        "min_tenure_months": 12,
        "max_tenure_months": 72,
        "base_interest_rate_pct": 10.50,
        "max_ltv_pct": 85.0,
        "target_segment": "RURAL_AGRI",
    },

    {
        "product_code": "CV_LOAN",
        "product_name": "Commercial Vehicle Loan",
        "product_category": "COMMERCIAL_FINANCE",
        "secured": True,
        "min_loan_amount_inr": 500000,
        "max_loan_amount_inr": 5000000,
        "min_tenure_months": 12,
        "max_tenure_months": 72,
        "base_interest_rate_pct": 10.75,
        "max_ltv_pct": 85.0,
        "target_segment": "COMMERCIAL_OPERATOR",
    },

    {
        "product_code": "SME_LOAN",
        "product_name": "SME Business Loan",
        "product_category": "BUSINESS_FINANCE",
        "secured": False,
        "min_loan_amount_inr": 200000,
        "max_loan_amount_inr": 2500000,
        "min_tenure_months": 12,
        "max_tenure_months": 48,
        "base_interest_rate_pct": 13.50,
        "max_ltv_pct": None,
        "target_segment": "SME",
    },

    {
        "product_code": "PERSONAL_LOAN",
        "product_name": "Personal Loan",
        "product_category": "CONSUMER_FINANCE",
        "secured": False,
        "min_loan_amount_inr": 50000,
        "max_loan_amount_inr": 1000000,
        "min_tenure_months": 6,
        "max_tenure_months": 60,
        "base_interest_rate_pct": 14.25,
        "max_ltv_pct": None,
        "target_segment": "RETAIL_CONSUMER",
    },
]


# ============================================================
# TEMPLATE VALIDATION
# ============================================================


def _validate_template(
    template: Mapping[str, Any],
) -> None:
    """
    Validate one finance-product template before using it.
    """

    required = {
        "product_code",
        "product_name",
        "product_category",
        "secured",
        "min_loan_amount_inr",
        "max_loan_amount_inr",
        "min_tenure_months",
        "max_tenure_months",
        "base_interest_rate_pct",
        "max_ltv_pct",
        "target_segment",
    }

    missing = required.difference(
        template.keys()
    )

    if missing:
        raise ValueError(
            "Finance product template is "
            "missing keys: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # --------------------------------------------------------
    # Amount validation
    # --------------------------------------------------------

    if int(
        template[
            "min_loan_amount_inr"
        ]
    ) <= 0:

        raise ValueError(
            "min_loan_amount_inr "
            "must be > 0"
        )

    if int(
        template[
            "max_loan_amount_inr"
        ]
    ) < int(
        template[
            "min_loan_amount_inr"
        ]
    ):

        raise ValueError(
            "max_loan_amount_inr must be "
            ">= min_loan_amount_inr"
        )

    # --------------------------------------------------------
    # Tenure validation
    # --------------------------------------------------------

    if int(
        template[
            "min_tenure_months"
        ]
    ) <= 0:

        raise ValueError(
            "min_tenure_months "
            "must be > 0"
        )

    if int(
        template[
            "max_tenure_months"
        ]
    ) < int(
        template[
            "min_tenure_months"
        ]
    ):

        raise ValueError(
            "max_tenure_months must be "
            ">= min_tenure_months"
        )

    # --------------------------------------------------------
    # Interest validation
    # --------------------------------------------------------

    rate = float(
        template[
            "base_interest_rate_pct"
        ]
    )

    if not 0 < rate < 100:

        raise ValueError(
            "base_interest_rate_pct "
            "must be between 0 and 100"
        )

    # --------------------------------------------------------
    # LTV validation
    # --------------------------------------------------------

    ltv = template[
        "max_ltv_pct"
    ]

    if (
        ltv is not None
        and not (
            0
            < float(
                ltv
            )
            <= 100
        )
    ):

        raise ValueError(
            "max_ltv_pct must be "
            "in (0, 100] or None"
        )

    # Unsecured loans should not have an LTV.
    if (
        not bool(
            template[
                "secured"
            ]
        )
        and ltv is not None
    ):

        raise ValueError(
            "Unsecured finance products "
            "must not define max_ltv_pct"
        )


# ============================================================
# GENERATOR
# ============================================================


def generate_finance_products(
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Generate finance-product master data.

    Output columns:

        finance_product_id
        product_code
        product_name
        product_category
        secured

        min_loan_amount_inr
        max_loan_amount_inr

        min_tenure_months
        max_tenure_months

        base_interest_rate_pct
        max_ltv_pct

        target_segment
        active

        data_origin
        generator_version
    """

    if generation is None:

        generation = (
            load_generation_config()
        )

    # --------------------------------------------------------
    # Provenance
    # --------------------------------------------------------

    provenance = generation.get(
        "provenance",
        {},
    )

    data_origin = str(
        provenance.get(
            "data_origin",
            "SYNTHETIC",
        )
    )

    generator_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    # --------------------------------------------------------
    # Generate master records
    # --------------------------------------------------------

    rows: list[
        dict[str, Any]
    ] = []

    for index, template in enumerate(
        FINANCE_PRODUCT_TEMPLATES,
        start=1,
    ):

        _validate_template(
            template
        )

        rows.append(
            {
                "finance_product_id":
                    generate_id(
                        "FINPROD_SYN",
                        index,
                        width=3,
                    ),

                "product_code":
                    str(
                        template[
                            "product_code"
                        ]
                    ),

                "product_name":
                    str(
                        template[
                            "product_name"
                        ]
                    ),

                "product_category":
                    str(
                        template[
                            "product_category"
                        ]
                    ),

                "secured":
                    bool(
                        template[
                            "secured"
                        ]
                    ),

                "min_loan_amount_inr":
                    int(
                        template[
                            "min_loan_amount_inr"
                        ]
                    ),

                "max_loan_amount_inr":
                    int(
                        template[
                            "max_loan_amount_inr"
                        ]
                    ),

                "min_tenure_months":
                    int(
                        template[
                            "min_tenure_months"
                        ]
                    ),

                "max_tenure_months":
                    int(
                        template[
                            "max_tenure_months"
                        ]
                    ),

                "base_interest_rate_pct":
                    float(
                        template[
                            "base_interest_rate_pct"
                        ]
                    ),

                "max_ltv_pct":
                    (
                        None
                        if template[
                            "max_ltv_pct"
                        ]
                        is None
                        else float(
                            template[
                                "max_ltv_pct"
                            ]
                        )
                    ),

                "target_segment":
                    str(
                        template[
                            "target_segment"
                        ]
                    ),

                "active":
                    True,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    finance_products = (
        pd.DataFrame(
            rows,
            columns=[
                "finance_product_id",
                "product_code",
                "product_name",
                "product_category",
                "secured",
                "min_loan_amount_inr",
                "max_loan_amount_inr",
                "min_tenure_months",
                "max_tenure_months",
                "base_interest_rate_pct",
                "max_ltv_pct",
                "target_segment",
                "active",
                "data_origin",
                "generator_version",
            ],
        )
    )

    validate_finance_products(
        finance_products
    )

    return finance_products


# ============================================================
# VALIDATION
# ============================================================


def validate_finance_products(
    finance_products: pd.DataFrame,
) -> None:
    """
    Validate finance-product master data.
    """

    required_columns = {
        "finance_product_id",
        "product_code",
        "product_name",
        "product_category",
        "secured",
        "min_loan_amount_inr",
        "max_loan_amount_inr",
        "min_tenure_months",
        "max_tenure_months",
        "base_interest_rate_pct",
        "max_ltv_pct",
        "target_segment",
        "active",
        "data_origin",
        "generator_version",
    }

    missing_columns = (
        required_columns
        .difference(
            finance_products.columns
        )
    )

    if missing_columns:

        raise ValueError(
            "Finance-products DataFrame "
            "is missing required columns: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    if finance_products.empty:

        raise ValueError(
            "Finance-products DataFrame "
            "cannot be empty"
        )

    # --------------------------------------------------------
    # Required non-null fields
    # --------------------------------------------------------

    required_non_null = [
        "finance_product_id",
        "product_code",
        "product_name",
        "product_category",
        "secured",
        "min_loan_amount_inr",
        "max_loan_amount_inr",
        "min_tenure_months",
        "max_tenure_months",
        "base_interest_rate_pct",
        "target_segment",
        "active",
        "data_origin",
        "generator_version",
    ]

    for column in required_non_null:

        if finance_products[
            column
        ].isna().any():

            raise ValueError(
                f"Missing values found "
                f"in {column}"
            )

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    if finance_products[
        "finance_product_id"
    ].duplicated().any():

        raise ValueError(
            "Duplicate finance_product_id "
            "values found"
        )

    # --------------------------------------------------------
    # Unique product codes
    # --------------------------------------------------------

    if finance_products[
        "product_code"
    ].duplicated().any():

        raise ValueError(
            "Duplicate product_code "
            "values found"
        )

    # --------------------------------------------------------
    # Unique product names
    # --------------------------------------------------------

    if finance_products[
        "product_name"
    ].duplicated().any():

        raise ValueError(
            "Duplicate product_name "
            "values found"
        )

    # --------------------------------------------------------
    # Loan amount validation
    # --------------------------------------------------------

    min_amount = pd.to_numeric(
        finance_products[
            "min_loan_amount_inr"
        ],
        errors="raise",
    )

    max_amount = pd.to_numeric(
        finance_products[
            "max_loan_amount_inr"
        ],
        errors="raise",
    )

    if (
        min_amount <= 0
    ).any():

        raise ValueError(
            "min_loan_amount_inr "
            "must be > 0"
        )

    if (
        max_amount
        < min_amount
    ).any():

        raise ValueError(
            "max_loan_amount_inr must be "
            ">= min_loan_amount_inr"
        )

    # --------------------------------------------------------
    # Tenure validation
    # --------------------------------------------------------

    min_tenure = pd.to_numeric(
        finance_products[
            "min_tenure_months"
        ],
        errors="raise",
    )

    max_tenure = pd.to_numeric(
        finance_products[
            "max_tenure_months"
        ],
        errors="raise",
    )

    if (
        min_tenure <= 0
    ).any():

        raise ValueError(
            "min_tenure_months "
            "must be > 0"
        )

    if (
        max_tenure
        < min_tenure
    ).any():

        raise ValueError(
            "max_tenure_months must be "
            ">= min_tenure_months"
        )

    # --------------------------------------------------------
    # Interest-rate validation
    # --------------------------------------------------------

    interest_rate = pd.to_numeric(
        finance_products[
            "base_interest_rate_pct"
        ],
        errors="raise",
    )

    if (
        (
            interest_rate <= 0
        )
        |
        (
            interest_rate >= 100
        )
    ).any():

        raise ValueError(
            "base_interest_rate_pct "
            "must be between 0 and 100"
        )

    # --------------------------------------------------------
    # LTV validation
    #
    # max_ltv_pct may be NULL for unsecured products.
    # --------------------------------------------------------

    present_ltv = (
        finance_products[
            "max_ltv_pct"
        ].notna()
    )

    ltv = pd.to_numeric(
        finance_products.loc[
            present_ltv,
            "max_ltv_pct",
        ],
        errors="raise",
    )

    if (
        (
            ltv <= 0
        )
        |
        (
            ltv > 100
        )
    ).any():

        raise ValueError(
            "max_ltv_pct must be "
            "in (0, 100] when present"
        )

    # --------------------------------------------------------
    # Unsecured products should not have an LTV
    # --------------------------------------------------------

    unsecured_with_ltv = (
        ~finance_products[
            "secured"
        ].astype(
            bool
        )
        &
        finance_products[
            "max_ltv_pct"
        ].notna()
    )

    if unsecured_with_ltv.any():

        raise ValueError(
            "Unsecured finance products "
            "cannot have max_ltv_pct"
        )


# ============================================================
# PUBLIC MASTER GENERATOR
# ============================================================


def generate_finance_product_master(
    generation: Mapping[
        str,
        Any,
    ]
    | None = None,
) -> pd.DataFrame:
    """
    Public entry point used later by generate_all.py.

    Returns:
        finance_products_df
    """

    return generate_finance_products(
        generation=generation,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    finance_products_df = (
        generate_finance_product_master()
    )

    print(
        "\n=== FINANCE PRODUCTS ===\n"
    )

    print(
        finance_products_df.to_string(
            index=False
        )
    )

    print(
        "\nGenerated "
        f"{len(finance_products_df)} "
        "finance products successfully."
    )