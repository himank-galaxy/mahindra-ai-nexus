"""
Synthetic Auto lead generator for Mahindra AI Nexus.

Generates lead/event records from:
- synthetic customers
- dealer master
- vehicle model master
- generation.yaml
- distributions.yaml

This module DOES NOT write CSV files.

Later:
    data/scripts/generate_all.py

will save:

    data/synthetic/auto/leads.csv
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.distributions import (
    sample_distribution,
)

from data.generators.common.helpers import (
    load_distribution_config,
    load_generation_config,
)

from data.generators.common.ids import (
    make_entity_id,
)

from data.generators.common.seed import (
    derive_seed,
    make_rng,
)


# ============================================================
# BASIC HELPERS
# ============================================================


def _as_positive_int(
    value: Any,
    name: str,
) -> int:
    """
    Convert a configuration value into a positive integer.
    """

    if isinstance(value, bool):
        raise TypeError(
            f"{name} must be an integer, not bool"
        )

    try:
        result = int(value)

    except (TypeError, ValueError) as exc:
        raise TypeError(
            f"{name} must be an integer"
        ) from exc

    if result <= 0:
        raise ValueError(
            f"{name} must be > 0"
        )

    return result


def _get_lead_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read lead count.

    Supports:

        auto:
          leads:
            count: 10000

    and, if present:

        auto:
          leads:
            target_count: 10000
    """

    try:
        lead_config = (
            generation[
                "auto"
            ][
                "leads"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing configuration key: "
            "generation.auto.leads"
        ) from exc

    if isinstance(
        lead_config,
        Mapping,
    ):

        value = lead_config.get(
            "count",
            lead_config.get(
                "target_count"
            ),
        )

    else:
        value = lead_config

    if value is None:
        raise KeyError(
            "Missing lead count. Expected "
            "generation.auto.leads.count "
            "or generation.auto.leads.target_count"
        )

    return _as_positive_int(
        value,
        "generation.auto.leads.count",
    )


def _normalize_weights(
    weights: Mapping[str, Any],
    name: str,
) -> dict[str, float]:
    """
    Validate and normalize categorical probabilities.
    """

    if (
        not isinstance(
            weights,
            Mapping,
        )
        or not weights
    ):
        raise ValueError(
            f"{name} must be a non-empty mapping"
        )

    parsed: dict[
        str,
        float,
    ] = {}

    for label, raw in weights.items():

        try:
            value = float(raw)

        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Weight for {label!r} "
                f"in {name} must be numeric"
            ) from exc

        if value < 0:
            raise ValueError(
                f"Weight for {label!r} "
                f"in {name} cannot be negative"
            )

        parsed[
            str(label)
        ] = value

    total = sum(
        parsed.values()
    )

    if total <= 0:
        raise ValueError(
            f"Weights in {name} "
            "must sum to > 0"
        )

    return {
        key: value / total
        for key, value
        in parsed.items()
    }


# ============================================================
# GENERATION END TIME
# ============================================================


def _get_generation_end(
    generation: Mapping[str, Any],
) -> pd.Timestamp:
    """
    Read configured synthetic-data end time.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):
        time_config = generation.get(
            "time_window"
        )

    if not isinstance(
        time_config,
        Mapping,
    ):
        raise KeyError(
            "Missing generation time configuration. "
            "Expected generation.time "
            "or generation.time_window."
        )

    end_value = time_config.get(
        "end",
        time_config.get(
            "end_date"
        ),
    )

    if end_value is None:
        raise KeyError(
            "Missing end/end_date in "
            "generation time configuration"
        )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    timestamp = pd.Timestamp(
        end_value
    )

    if timestamp.tzinfo is None:
        timestamp = (
            timestamp.tz_localize(
                timezone
            )
        )

    else:
        timestamp = (
            timestamp.tz_convert(
                timezone
            )
        )

    return timestamp


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    customers: pd.DataFrame,
    dealers: pd.DataFrame,
    vehicle_models: pd.DataFrame,
) -> None:
    """
    Validate required upstream data.
    """

    customer_required = {
        "customer_id",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "preferred_vehicle_model_id",
        "preferred_vehicle_model_name",

        "purchase_horizon_days",

        "created_at",
    }

    dealer_required = {
        "dealer_id",
        "dealer_name",

        "city_id",
        "city_name",

        "region_id",
        "region_name",

        "monthly_lead_capacity",

        "active",
    }

    vehicle_required = {
        "vehicle_model_id",
        "model_name",
    }

    for (
        name,
        dataframe,
        required,
    ) in (
        (
            "customers",
            customers,
            customer_required,
        ),
        (
            "dealers",
            dealers,
            dealer_required,
        ),
        (
            "vehicle_models",
            vehicle_models,
            vehicle_required,
        ),
    ):

        missing = (
            required
            .difference(
                dataframe.columns
            )
        )

        if missing:
            raise ValueError(
                f"{name} DataFrame is missing "
                "required columns: "
                + ", ".join(
                    sorted(
                        missing
                    )
                )
            )

        if dataframe.empty:
            raise ValueError(
                f"{name} DataFrame cannot be empty"
            )

    if customers[
        "customer_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate customer_id values found"
        )

    if dealers[
        "dealer_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate dealer_id values found"
        )

    if vehicle_models[
        "vehicle_model_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate vehicle_model_id values found"
        )


# ============================================================
# DEALER ASSIGNMENT
# ============================================================


def _build_dealer_pools(
    dealers: pd.DataFrame,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    """
    Build dealer lookup tables.

    Preferred assignment:
        same city

    Fallback:
        same region
    """

    active_dealers = dealers[
        dealers[
            "active"
        ].astype(bool)
    ].copy()

    if active_dealers.empty:
        raise ValueError(
            "No active dealers available"
        )

    city_pools = {

        str(city_id):
            group.reset_index(
                drop=True
            )

        for city_id, group
        in active_dealers.groupby(
            "city_id",
            sort=False,
        )
    }

    region_pools = {

        str(region_id):
            group.reset_index(
                drop=True
            )

        for region_id, group
        in active_dealers.groupby(
            "region_id",
            sort=False,
        )
    }

    return (
        city_pools,
        region_pools,
    )


def _choose_dealer(
    rng: np.random.Generator,
    customer: pd.Series,
    city_pools: dict[
        str,
        pd.DataFrame,
    ],
    region_pools: dict[
        str,
        pd.DataFrame,
    ],
) -> pd.Series:
    """
    Choose a dealer for a customer.

    Dealers with higher monthly lead capacity
    receive proportionally more leads.
    """

    pool = city_pools.get(
        str(
            customer[
                "city_id"
            ]
        )
    )

    if (
        pool is None
        or pool.empty
    ):

        pool = region_pools.get(
            str(
                customer[
                    "region_id"
                ]
            )
        )

    if (
        pool is None
        or pool.empty
    ):

        raise ValueError(
            "No active dealer found for "
            f"customer {customer['customer_id']}"
        )

    capacities = pd.to_numeric(
        pool[
            "monthly_lead_capacity"
        ],
        errors="raise",
    ).to_numpy(
        dtype=float
    )

    if (
        capacities <= 0
    ).any():
        raise ValueError(
            "Dealer monthly_lead_capacity "
            "must be > 0"
        )

    probabilities = (
        capacities
        / capacities.sum()
    )

    selected_index = int(
        rng.choice(
            np.arange(
                len(pool)
            ),
            p=probabilities,
        )
    )

    return pool.iloc[
        selected_index
    ]


# ============================================================
# CUSTOMER SELECTION
# ============================================================


def _select_customer_indices(
    rng: np.random.Generator,
    customers: pd.DataFrame,
    lead_count: int,
) -> np.ndarray:
    """
    Select customers that create leads.

    With the current design:

        customers = 5,000
        leads     = 10,000

    Every customer can appear at least once,
    while additional lead events are assigned to
    customers with shorter purchase horizons more often.

    One customer may therefore have multiple lead events.
    """

    customer_count = len(
        customers
    )

    # --------------------------------------------------------
    # Fewer leads than customers
    # --------------------------------------------------------

    if lead_count <= customer_count:

        return rng.choice(
            np.arange(
                customer_count
            ),
            size=lead_count,
            replace=False,
        )

    # --------------------------------------------------------
    # First pass:
    # every customer gets one lead
    # --------------------------------------------------------

    base_indices = np.arange(
        customer_count
    )

    # --------------------------------------------------------
    # Repeat probability:
    #
    # shorter purchase horizon
    #       ↓
    # higher chance of another lead interaction
    # --------------------------------------------------------

    horizons = pd.to_numeric(
        customers[
            "purchase_horizon_days"
        ],
        errors="raise",
    ).to_numpy(
        dtype=float
    )

    repeat_weights = (
        1.0
        / np.maximum(
            horizons,
            1.0,
        )
    )

    repeat_weights = (
        repeat_weights
        / repeat_weights.sum()
    )

    extra_indices = (
        rng.choice(
            np.arange(
                customer_count
            ),
            size=(
                lead_count
                - customer_count
            ),
            replace=True,
            p=repeat_weights,
        )
    )

    result = np.concatenate(
        [
            base_indices,
            extra_indices,
        ]
    )

    # Shuffle so the first 5,000 rows are not
    # simply customer 1 -> customer 5000.
    rng.shuffle(
        result
    )

    return result


# ============================================================
# LEAD EVENT TIME
# ============================================================


def _generate_lead_timestamp(
    rng: np.random.Generator,
    customer_created_at: Any,
    generation_end: pd.Timestamp,
) -> pd.Timestamp:
    """
    Generate lead time after customer creation.

    Maximum synthetic delay:
        7 days

    The timestamp never exceeds the configured
    generation end time.
    """

    start = pd.Timestamp(
        customer_created_at
    )

    if (
        start.tzinfo is None
        and generation_end.tzinfo
        is not None
    ):

        start = start.tz_localize(
            generation_end.tzinfo
        )

    elif (
        start.tzinfo is not None
        and generation_end.tzinfo
        is not None
    ):

        start = start.tz_convert(
            generation_end.tzinfo
        )

    if start > generation_end:
        raise ValueError(
            f"Customer created_at {start} "
            "is after generation end "
            f"{generation_end}"
        )

    available_seconds = max(
        0.0,
        (
            generation_end
            - start
        ).total_seconds(),
    )

    max_delay_seconds = min(
        7
        * 24
        * 60
        * 60,

        available_seconds,
    )

    if max_delay_seconds <= 0:
        return start

    delay_seconds = float(
        rng.uniform(
            0,
            max_delay_seconds,
        )
    )

    return (
        start
        + timedelta(
            seconds=delay_seconds
        )
    )


# ============================================================
# LEAD GENERATOR
# ============================================================


def generate_leads(
    customers: pd.DataFrame,
    dealers: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate Auto lead events.

    Main output:

        lead_id
        customer_id
        dealer_id

        region/city
        vehicle model

        source_channel

        budget_fit
        engagement_score
        urgency_score
        model_interest_score
        source_quality

        latent_purchase_intent

        lead_created_at
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    if distributions is None:
        distributions = (
            load_distribution_config()
        )

    # ========================================================
    # UPSTREAM VALIDATION
    # ========================================================

    _validate_inputs(
        customers=customers,
        dealers=dealers,
        vehicle_models=vehicle_models,
    )

    # ========================================================
    # LEAD COUNT
    # ========================================================

    lead_count = _get_lead_count(
        generation
    )

    # ========================================================
    # DETERMINISTIC RNG
    # ========================================================

    try:
        base_seed = int(
            generation[
                "seed"
            ]
        )

    except KeyError as exc:
        raise KeyError(
            "Missing generation.seed"
        ) from exc

    lead_seed = (
        derive_seed(
            base_seed,
            "auto.leads",
        )
    )

    rng = make_rng(
        lead_seed
    )

    # ========================================================
    # EXACT LEADS DISTRIBUTION CONFIG
    # ========================================================

    lead_config = (
        distributions.get(
            "leads"
        )
    )

    if not isinstance(
        lead_config,
        Mapping,
    ):
        raise KeyError(
            "Missing distributions.leads "
            "configuration"
        )

    required_distribution_keys = {
        "source_channel_weights",
        "budget_fit",
        "engagement_score",
        "urgency_score",
        "model_interest_score",
        "source_quality",
        "latent_purchase_intent",
    }

    missing = (
        required_distribution_keys
        .difference(
            lead_config.keys()
        )
    )

    if missing:
        raise KeyError(
            "distributions.leads is missing "
            "required keys: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # SOURCE CHANNEL
    # ========================================================

    source_weights = (
        _normalize_weights(
            lead_config[
                "source_channel_weights"
            ],
            (
                "distributions.leads."
                "source_channel_weights"
            ),
        )
    )

    # ========================================================
    # SOURCE QUALITY
    # ========================================================

    raw_source_quality = (
        lead_config[
            "source_quality"
        ]
    )

    if not isinstance(
        raw_source_quality,
        Mapping,
    ):
        raise TypeError(
            "distributions.leads."
            "source_quality must be a mapping"
        )

    source_quality = {

        str(channel):
            float(score)

        for channel, score
        in raw_source_quality.items()
    }

    # All channels must have quality scores.
    if (
        set(
            source_weights
        )
        != set(
            source_quality
        )
    ):

        raise ValueError(
            "Lead source-channel keys and "
            "source_quality keys must match"
        )

    for (
        channel,
        value,
    ) in source_quality.items():

        if not (
            0
            <= value
            <= 1
        ):
            raise ValueError(
                f"Source quality for {channel} "
                "must be between 0 and 1"
            )

    # ========================================================
    # LATENT PURCHASE INTENT FORMULA
    # ========================================================

    latent_config = (
        lead_config[
            "latent_purchase_intent"
        ]
    )

    if not isinstance(
        latent_config,
        Mapping,
    ):
        raise TypeError(
            "distributions.leads."
            "latent_purchase_intent "
            "must be a mapping"
        )

    latent_weights = {

        "budget_fit":
            float(
                latent_config[
                    "budget_fit_weight"
                ]
            ),

        "model_interest":
            float(
                latent_config[
                    "model_interest_weight"
                ]
            ),

        "engagement":
            float(
                latent_config[
                    "engagement_weight"
                ]
            ),

        "source_quality":
            float(
                latent_config[
                    "source_quality_weight"
                ]
            ),

        "urgency":
            float(
                latent_config[
                    "urgency_weight"
                ]
            ),
    }

    if any(
        value < 0
        for value
        in latent_weights.values()
    ):
        raise ValueError(
            "Latent purchase-intent weights "
            "cannot be negative"
        )

    weight_total = sum(
        latent_weights.values()
    )

    if weight_total <= 0:
        raise ValueError(
            "Latent purchase-intent weights "
            "must sum to > 0"
        )

    # Normalize defensively.
    latent_weights = {

        key:
            value / weight_total

        for key, value
        in latent_weights.items()
    }

    noise_std = float(
        latent_config[
            "noise_std"
        ]
    )

    if noise_std < 0:
        raise ValueError(
            "latent_purchase_intent."
            "noise_std cannot be negative"
        )

    # ========================================================
    # GENERATION END DATE
    # ========================================================

    generation_end = (
        _get_generation_end(
            generation
        )
    )

    # ========================================================
    # DEALER POOLS
    # ========================================================

    (
        city_dealer_pools,
        region_dealer_pools,
    ) = _build_dealer_pools(
        dealers
    )

    # ========================================================
    # CUSTOMER SELECTION
    # ========================================================

    customer_indices = (
        _select_customer_indices(
            rng=rng,
            customers=customers,
            lead_count=lead_count,
        )
    )

    # ========================================================
    # SOURCE CHANNEL GENERATION
    # ========================================================

    source_channels = (
        rng.choice(
            list(
                source_weights.keys()
            ),
            size=lead_count,
            p=np.asarray(
                list(
                    source_weights.values()
                ),
                dtype=float,
            ),
        )
    )

    # ========================================================
    # SCORE GENERATION
    #
    # Uses EXACT distributions.yaml sections.
    # ========================================================

    budget_fit = np.asarray(
        sample_distribution(
            lead_config[
                "budget_fit"
            ],
            size=lead_count,
            rng=rng,
        ),
        dtype=float,
    )

    engagement_scores = np.asarray(
        sample_distribution(
            lead_config[
                "engagement_score"
            ],
            size=lead_count,
            rng=rng,
        ),
        dtype=float,
    )

    urgency_base = np.asarray(
        sample_distribution(
            lead_config[
                "urgency_score"
            ],
            size=lead_count,
            rng=rng,
        ),
        dtype=float,
    )

    model_interest_scores = np.asarray(
        sample_distribution(
            lead_config[
                "model_interest_score"
            ],
            size=lead_count,
            rng=rng,
        ),
        dtype=float,
    )

    # ========================================================
    # PROVENANCE
    # ========================================================

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

    # ========================================================
    # VEHICLE LOOKUP
    # ========================================================

    model_lookup = dict(
        zip(
            vehicle_models[
                "vehicle_model_id"
            ],
            vehicle_models[
                "model_name"
            ],
        )
    )

    # ========================================================
    # BUILD LEAD RECORDS
    # ========================================================

    rows: list[
        dict[str, Any]
    ] = []

    customer_lead_counter: dict[
        str,
        int,
    ] = {}

    for position, customer_index in enumerate(
        customer_indices
    ):

        customer = (
            customers.iloc[
                int(
                    customer_index
                )
            ]
        )

        customer_id = str(
            customer[
                "customer_id"
            ]
        )

        customer_lead_counter[
            customer_id
        ] = (
            customer_lead_counter.get(
                customer_id,
                0,
            )
            + 1
        )

        # ====================================================
        # DEALER ASSIGNMENT
        # ====================================================

        dealer = (
            _choose_dealer(
                rng=rng,
                customer=customer,
                city_pools=
                    city_dealer_pools,
                region_pools=
                    region_dealer_pools,
            )
        )

        # ====================================================
        # SOURCE CHANNEL QUALITY
        # ====================================================

        channel = str(
            source_channels[
                position
            ]
        )

        channel_quality = float(
            source_quality[
                channel
            ]
        )

        # ====================================================
        # URGENCY COHERENCE
        #
        # Base score comes from:
        #
        # distributions.leads.urgency_score
        #
        # Customer purchase horizon provides a small
        # coherence adjustment:
        #
        # shorter horizon -> higher urgency
        # ====================================================

        horizon_days = float(
            customer[
                "purchase_horizon_days"
            ]
        )

        horizon_urgency = (
            1.0
            - (
                min(
                    max(
                        horizon_days,
                        1.0,
                    ),
                    120.0,
                )
                / 120.0
            )
        )

        urgency_score = float(
            np.clip(
                (
                    0.70
                    * urgency_base[
                        position
                    ]
                )
                +
                (
                    0.30
                    * horizon_urgency
                ),
                0.0,
                1.0,
            )
        )

        # ====================================================
        # LATENT PURCHASE INTENT
        #
        # Exact formula components from your YAML:
        #
        # budget_fit       0.30
        # model_interest   0.20
        # engagement       0.20
        # source_quality   0.15
        # urgency          0.15
        # noise std        0.08
        # ====================================================

        noise = float(
            rng.normal(
                loc=0.0,
                scale=noise_std,
            )
        )

        latent_purchase_intent = (

            latent_weights[
                "budget_fit"
            ]
            * float(
                budget_fit[
                    position
                ]
            )

            +

            latent_weights[
                "model_interest"
            ]
            * float(
                model_interest_scores[
                    position
                ]
            )

            +

            latent_weights[
                "engagement"
            ]
            * float(
                engagement_scores[
                    position
                ]
            )

            +

            latent_weights[
                "source_quality"
            ]
            * channel_quality

            +

            latent_weights[
                "urgency"
            ]
            * urgency_score

            +

            noise
        )

        latent_purchase_intent = float(
            np.clip(
                latent_purchase_intent,
                0.0,
                1.0,
            )
        )

        # ====================================================
        # MODEL
        #
        # A lead starts from the customer's preferred
        # vehicle model.
        # ====================================================

        vehicle_model_id = str(
            customer[
                "preferred_vehicle_model_id"
            ]
        )

        if (
            vehicle_model_id
            not in model_lookup
        ):
            raise ValueError(
                f"Customer {customer_id} "
                "references unknown vehicle "
                f"model {vehicle_model_id}"
            )

        vehicle_model_name = str(
            model_lookup[
                vehicle_model_id
            ]
        )

        # ====================================================
        # EVENT TIME
        # ====================================================

        lead_created_at = (
            _generate_lead_timestamp(
                rng=rng,

                customer_created_at=
                    customer[
                        "created_at"
                    ],

                generation_end=
                    generation_end,
            )
        )

        # ====================================================
        # RECORD
        # ====================================================

        rows.append(
            {
                "lead_id":
                    make_entity_id(
                        "lead",
                        position + 1,
                        width=6,
                    ),

                "customer_id":
                    customer_id,

                "customer_lead_number":
                    customer_lead_counter[
                        customer_id
                    ],

                # --------------------------------------------
                # Dealer
                # --------------------------------------------

                "dealer_id":
                    str(
                        dealer[
                            "dealer_id"
                        ]
                    ),

                "dealer_name":
                    str(
                        dealer[
                            "dealer_name"
                        ]
                    ),

                # --------------------------------------------
                # Geography
                # --------------------------------------------

                "region_id":
                    str(
                        customer[
                            "region_id"
                        ]
                    ),

                "region_name":
                    str(
                        customer[
                            "region_name"
                        ]
                    ),

                "city_id":
                    str(
                        customer[
                            "city_id"
                        ]
                    ),

                "city_name":
                    str(
                        customer[
                            "city_name"
                        ]
                    ),

                # --------------------------------------------
                # Vehicle
                # --------------------------------------------

                "vehicle_model_id":
                    vehicle_model_id,

                "vehicle_model_name":
                    vehicle_model_name,

                # --------------------------------------------
                # Lead evidence
                # --------------------------------------------

                "source_channel":
                    channel,

                "budget_fit":
                    round(
                        float(
                            budget_fit[
                                position
                            ]
                        ),
                        6,
                    ),

                "engagement_score":
                    round(
                        float(
                            engagement_scores[
                                position
                            ]
                        ),
                        6,
                    ),

                "urgency_score":
                    round(
                        urgency_score,
                        6,
                    ),

                "model_interest_score":
                    round(
                        float(
                            model_interest_scores[
                                position
                            ]
                        ),
                        6,
                    ),

                "source_quality":
                    round(
                        channel_quality,
                        6,
                    ),

                "latent_purchase_intent":
                    round(
                        latent_purchase_intent,
                        6,
                    ),

                # --------------------------------------------
                # Time
                # --------------------------------------------

                "lead_created_at":
                    lead_created_at,

                # --------------------------------------------
                # Provenance
                # --------------------------------------------

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    leads = pd.DataFrame(
        rows,
        columns=[
            "lead_id",
            "customer_id",
            "customer_lead_number",

            "dealer_id",
            "dealer_name",

            "region_id",
            "region_name",

            "city_id",
            "city_name",

            "vehicle_model_id",
            "vehicle_model_name",

            "source_channel",

            "budget_fit",
            "engagement_score",
            "urgency_score",
            "model_interest_score",
            "source_quality",

            "latent_purchase_intent",

            "lead_created_at",

            "data_origin",
            "generator_version",
        ],
    )

    validate_leads(
        leads=leads,
        customers=customers,
        dealers=dealers,
        vehicle_models=vehicle_models,
        source_quality=
            source_quality,
        expected_count=
            lead_count,
    )

    return leads


# ============================================================
# VALIDATION
# ============================================================


def validate_leads(
    leads: pd.DataFrame,
    customers: pd.DataFrame,
    dealers: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    source_quality: Mapping[
        str,
        float,
    ],
    expected_count: int,
) -> None:
    """
    Validate generated leads.
    """

    required_columns = {
        "lead_id",
        "customer_id",
        "customer_lead_number",

        "dealer_id",
        "dealer_name",

        "region_id",
        "region_name",

        "city_id",
        "city_name",

        "vehicle_model_id",
        "vehicle_model_name",

        "source_channel",

        "budget_fit",
        "engagement_score",
        "urgency_score",
        "model_interest_score",
        "source_quality",

        "latent_purchase_intent",

        "lead_created_at",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        .difference(
            leads.columns
        )
    )

    if missing:
        raise ValueError(
            "Leads DataFrame is missing "
            "required columns: "
            + ", ".join(
                sorted(
                    missing
                )
            )
        )

    if leads.empty:
        raise ValueError(
            "Leads DataFrame cannot be empty"
        )

    # ========================================================
    # COUNT
    # ========================================================

    if len(
        leads
    ) != expected_count:
        raise ValueError(
            f"Expected {expected_count} leads "
            f"but generated {len(leads)}"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    if leads[
        "lead_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate lead_id values found"
        )

    # ========================================================
    # NULLS
    # ========================================================

    if leads.isna().any().any():

        null_columns = (
            leads.columns[
                leads.isna().any()
            ]
            .tolist()
        )

        raise ValueError(
            "Lead data contains unexpected "
            "null values in: "
            + ", ".join(
                null_columns
            )
        )

    # ========================================================
    # CUSTOMER FK
    # ========================================================

    invalid_customers = (
        set(
            leads[
                "customer_id"
            ]
        )
        .difference(
            set(
                customers[
                    "customer_id"
                ]
            )
        )
    )

    if invalid_customers:
        raise ValueError(
            "Leads reference invalid "
            "customer IDs: "
            + ", ".join(
                sorted(
                    invalid_customers
                )
            )
        )

    # ========================================================
    # DEALER FK
    # ========================================================

    invalid_dealers = (
        set(
            leads[
                "dealer_id"
            ]
        )
        .difference(
            set(
                dealers[
                    "dealer_id"
                ]
            )
        )
    )

    if invalid_dealers:
        raise ValueError(
            "Leads reference invalid dealer IDs: "
            + ", ".join(
                sorted(
                    invalid_dealers
                )
            )
        )

    # ========================================================
    # MODEL FK
    # ========================================================

    invalid_models = (
        set(
            leads[
                "vehicle_model_id"
            ]
        )
        .difference(
            set(
                vehicle_models[
                    "vehicle_model_id"
                ]
            )
        )
    )

    if invalid_models:
        raise ValueError(
            "Leads reference invalid "
            "vehicle-model IDs: "
            + ", ".join(
                sorted(
                    invalid_models
                )
            )
        )

    # ========================================================
    # SOURCE CHANNELS
    # ========================================================

    valid_channels = set(
        source_quality.keys()
    )

    invalid_channels = (
        set(
            leads[
                "source_channel"
            ]
        )
        .difference(
            valid_channels
        )
    )

    if invalid_channels:
        raise ValueError(
            "Invalid source channels: "
            + ", ".join(
                sorted(
                    invalid_channels
                )
            )
        )

    # ========================================================
    # SCORE RANGE
    # ========================================================

    score_columns = [
        "budget_fit",
        "engagement_score",
        "urgency_score",
        "model_interest_score",
        "source_quality",
        "latent_purchase_intent",
    ]

    for column in score_columns:

        values = pd.to_numeric(
            leads[
                column
            ],
            errors="raise",
        )

        if (
            (
                values < 0
            )
            |
            (
                values > 1
            )
        ).any():

            raise ValueError(
                f"{column} must contain "
                "values between 0 and 1"
            )

    # ========================================================
    # LOOKUPS
    # ========================================================

    customer_created_lookup = {

        row.customer_id:
            pd.Timestamp(
                row.created_at
            )

        for row
        in customers.itertuples(
            index=False
        )
    }

    dealer_lookup = {

        row.dealer_id: {

            "dealer_name":
                row.dealer_name,

            "city_id":
                row.city_id,

            "region_id":
                row.region_id,

            "active":
                bool(
                    row.active
                ),
        }

        for row
        in dealers.itertuples(
            index=False
        )
    }

    model_lookup = dict(
        zip(
            vehicle_models[
                "vehicle_model_id"
            ],
            vehicle_models[
                "model_name"
            ],
        )
    )

    # ========================================================
    # ROW-LEVEL CONSISTENCY
    # ========================================================

    for lead in leads.itertuples(
        index=False
    ):

        # ----------------------------------------------------
        # Lead must occur after customer exists
        # ----------------------------------------------------

        lead_time = pd.Timestamp(
            lead.lead_created_at
        )

        customer_time = (
            customer_created_lookup[
                lead.customer_id
            ]
        )

        if (
            lead_time
            < customer_time
        ):
            raise ValueError(
                f"Lead {lead.lead_id} "
                "occurs before customer creation"
            )

        # ----------------------------------------------------
        # Dealer consistency
        # ----------------------------------------------------

        dealer = dealer_lookup[
            lead.dealer_id
        ]

        if not dealer[
            "active"
        ]:
            raise ValueError(
                f"Lead {lead.lead_id} "
                "is assigned to an inactive dealer"
            )

        if (
            lead.dealer_name
            != dealer[
                "dealer_name"
            ]
        ):
            raise ValueError(
                "Dealer-name mismatch for "
                f"{lead.lead_id}"
            )

        if (
            lead.city_id
            != dealer[
                "city_id"
            ]
        ):
            raise ValueError(
                f"Lead {lead.lead_id} "
                "is assigned to a dealer "
                "outside the customer's city"
            )

        if (
            lead.region_id
            != dealer[
                "region_id"
            ]
        ):
            raise ValueError(
                "Dealer/customer region mismatch "
                f"for {lead.lead_id}"
            )

        # ----------------------------------------------------
        # Model consistency
        # ----------------------------------------------------

        if (
            lead.vehicle_model_name
            != model_lookup[
                lead.vehicle_model_id
            ]
        ):
            raise ValueError(
                "Vehicle-model name mismatch "
                f"for {lead.lead_id}"
            )

        # ----------------------------------------------------
        # Source quality must match configured channel quality
        # ----------------------------------------------------

        expected_source_quality = (
            source_quality[
                lead.source_channel
            ]
        )

        if abs(
            float(
                lead.source_quality
            )
            -
            float(
                expected_source_quality
            )
        ) > 1e-6:

            raise ValueError(
                "Source-quality mismatch "
                f"for {lead.lead_id}"
            )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_lead_master(
    customers: pd.DataFrame,
    dealers: pd.DataFrame,
    vehicle_models: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
    distributions: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Public entry point later used by generate_all.py.
    """

    return generate_leads(
        customers=customers,
        dealers=dealers,
        vehicle_models=vehicle_models,
        generation=generation,
        distributions=distributions,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.master.geography import (
        generate_geography,
    )

    from data.generators.master.vehicle_models import (
        generate_vehicle_models,
    )

    from data.generators.master.dealers import (
        generate_dealer_master,
    )

    from data.generators.auto.customers import (
        generate_customer_master,
    )

    # --------------------------------------------------------
    # Master data
    # --------------------------------------------------------

    (
        regions_df,
        cities_df,
    ) = generate_geography()

    vehicle_models_df = (
        generate_vehicle_models()
    )

    dealers_df = (
        generate_dealer_master(
            regions=regions_df,
            cities=cities_df,
        )
    )

    # --------------------------------------------------------
    # Customers
    # --------------------------------------------------------

    customers_df = (
        generate_customer_master(
            regions=regions_df,
            cities=cities_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    # --------------------------------------------------------
    # Leads
    # --------------------------------------------------------

    leads_df = (
        generate_lead_master(
            customers=customers_df,
            dealers=dealers_df,
            vehicle_models=
                vehicle_models_df,
        )
    )

    print(
        "\n=== LEADS SAMPLE ===\n"
    )

    print(
        leads_df
        .head(20)
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LEADS BY SOURCE CHANNEL ===\n"
    )

    print(
        leads_df
        .groupby(
            "source_channel"
        )
        .size()
        .reset_index(
            name="lead_count"
        )
        .sort_values(
            "lead_count",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LEADS BY REGION ===\n"
    )

    print(
        leads_df
        .groupby(
            "region_name"
        )
        .size()
        .reset_index(
            name="lead_count"
        )
        .to_string(
            index=False
        )
    )

    print(
        "\n=== LATENT PURCHASE INTENT ===\n"
    )

    print(
        leads_df[
            "latent_purchase_intent"
        ]
        .describe()
        .round(4)
        .to_string()
    )

    print(
        "\nGenerated "
        f"{len(leads_df)} "
        "synthetic leads successfully."
    )