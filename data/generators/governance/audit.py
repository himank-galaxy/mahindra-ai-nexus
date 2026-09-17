"""
Synthetic immutable governance audit-event generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Build the audit trail for the governance lifecycle that actually
exists at this point in the Synthetic Data Factory:

    Recommendation
        ↓
    Compliance checks
        ↓
    Compliance evaluation summary
        ↓
    Human review, where routed
        ↓
    Trust decision

This module does NOT fabricate:

    MODEL_SCORED
    CAUSAL_EXPLANATION_GENERATED
    SIMULATION_RUN
    ACTION_EXECUTED
    OUTCOME_CAPTURED
    LEARNING_EVENT_CREATED

unless those events really exist in upstream generated records.

Those lifecycle stages belong to later runtime/agent workflows.


============================================================
INPUTS
============================================================

recommendations
compliance_checks
trust_decisions
human_reviews


============================================================
OUTPUT
============================================================

audit_events


============================================================
CURRENT CONFIGURATION
============================================================

generation.yaml:

    governance:
        audit_events_target_count: 10000

With the currently frozen governance population:

    recommendations              2,000
    trust decisions              2,000
    human reviews                  300
    compliance checks           10,000

Mandatory audit coverage:

    recommendation recorded      2,000
    compliance summary           2,000
    trust decision recorded      2,000
    human review requested         300
    human review completed         300
                              --------
                                 6,600

The remaining configured audit-event capacity is used for
individual compliance-check audit details.

Current expected detail capacity:

    10,000 - 6,600 = 3,400

Selection guarantees:

1. Every non-PASS compliance check receives a detailed audit event.
2. Every decision receives at least one detailed compliance event.
3. Remaining detail capacity is filled deterministically from the
   strongest/relevant remaining checks.


============================================================
IMMUTABILITY
============================================================

Every recommendation receives its own ordered hash chain:

    GENESIS
       ↓
    event hash 1
       ↓
    event hash 2
       ↓
    ...
       ↓
    final decision event

Each event contains:

    previous_event_hash
    event_hash

The hash is deterministic and computed from the complete immutable
event payload plus the previous event hash.

This is a synthetic tamper-evident engineering mechanism, not a
claim of cryptographic regulatory certification.


============================================================
FACTORY RULES
============================================================

- deterministic
- no CSV writes
- DataFrame output only
- no hidden ground truth
- no fake future events
- exact FK lineage
- exact configured row count
- provenance retained
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np
import pandas as pd

from data.generators.common.helpers import (
    load_generation_config,
)

from data.generators.common.ids import (
    generate_id,
)


# ============================================================
# EVENT TYPES
# ============================================================

EVENT_RECOMMENDATION_RECORDED = (
    "RECOMMENDATION_RECORDED"
)

EVENT_COMPLIANCE_CHECK_RECORDED = (
    "COMPLIANCE_CHECK_RECORDED"
)

EVENT_COMPLIANCE_EVALUATION_COMPLETED = (
    "COMPLIANCE_EVALUATION_COMPLETED"
)

EVENT_HUMAN_REVIEW_REQUESTED = (
    "HUMAN_REVIEW_REQUESTED"
)

EVENT_HUMAN_REVIEW_COMPLETED = (
    "HUMAN_REVIEW_COMPLETED"
)

EVENT_TRUST_DECISION_RECORDED = (
    "TRUST_DECISION_RECORDED"
)


VALID_EVENT_TYPES = {
    EVENT_RECOMMENDATION_RECORDED,
    EVENT_COMPLIANCE_CHECK_RECORDED,
    EVENT_COMPLIANCE_EVALUATION_COMPLETED,
    EVENT_HUMAN_REVIEW_REQUESTED,
    EVENT_HUMAN_REVIEW_COMPLETED,
    EVENT_TRUST_DECISION_RECORDED,
}


EVENT_ORDER = {
    EVENT_RECOMMENDATION_RECORDED:
        10,

    EVENT_COMPLIANCE_CHECK_RECORDED:
        20,

    EVENT_COMPLIANCE_EVALUATION_COMPLETED:
        30,

    EVENT_HUMAN_REVIEW_REQUESTED:
        40,

    EVENT_HUMAN_REVIEW_COMPLETED:
        50,

    EVENT_TRUST_DECISION_RECORDED:
        60,
}


# ============================================================
# ACTORS
# ============================================================

ACTOR_SYSTEM = "SYSTEM"
ACTOR_HUMAN = "HUMAN"


VALID_ACTOR_TYPES = {
    ACTOR_SYSTEM,
    ACTOR_HUMAN,
}


ACTOR_RECOMMENDATION_ENGINE = (
    "RECOMMENDATION_ENGINE"
)

ACTOR_COMPLIANCE_AGENT = (
    "COMPLIANCE_AGENT"
)

ACTOR_HUMAN_REVIEW_ROUTER = (
    "HUMAN_REVIEW_ROUTER"
)

ACTOR_TRUST_POLICY_ENGINE = (
    "TRUST_POLICY_ENGINE"
)


# ============================================================
# EVENT STATUS
# ============================================================

EVENT_STATUS_RECORDED = (
    "RECORDED"
)

VALID_EVENT_STATUSES = {
    EVENT_STATUS_RECORDED,
}


# ============================================================
# COMPLIANCE RESULTS / SEVERITY
# ============================================================

RESULT_PASS = "PASS"
RESULT_WARN = "WARN"
RESULT_FAIL = "FAIL"
RESULT_REVIEW_REQUIRED = "REVIEW_REQUIRED"


RESULT_PRIORITY = {
    RESULT_FAIL:
        4,

    RESULT_REVIEW_REQUIRED:
        3,

    RESULT_WARN:
        2,

    RESULT_PASS:
        1,
}


SEVERITY_PRIORITY = {
    "CRITICAL":
        5,

    "HIGH":
        4,

    "MEDIUM":
        3,

    "LOW":
        2,

    "INFO":
        1,
}


RISK_PRIORITY = {
    "HIGH":
        3,

    "MEDIUM":
        2,

    "LOW":
        1,
}


# ============================================================
# INPUT SCHEMAS
# ============================================================

RECOMMENDATION_REQUIRED_COLUMNS = {
    "recommendation_id",

    "domain",
    "use_case",

    "target_entity_type",
    "target_entity_id",

    "recommendation_type",

    "generated_at",

    "evidence_json",
    "expected_impact",

    "confidence",
    "risk_level",

    "status",

    "data_origin",
    "generator_version",
}


COMPLIANCE_REQUIRED_COLUMNS = {
    "compliance_check_id",

    "decision_id",
    "recommendation_id",

    "domain",

    "rule_code",
    "rule_name",

    "checked_at",

    "result",
    "severity",

    "reason",
    "evidence_json",

    "data_origin",
    "generator_version",
}


DECISION_REQUIRED_COLUMNS = {
    "decision_id",
    "recommendation_id",

    "domain",
    "use_case",

    "target_entity_type",
    "target_entity_id",

    "recommendation_type",

    "recommendation_confidence",
    "recommendation_risk_level",

    "decision_mode",
    "decision",

    "decided_at",

    "compliance_checks_count",
    "compliance_pass_count",
    "compliance_warn_count",
    "compliance_fail_count",
    "compliance_review_required_count",

    "human_review_required",
    "human_review_id",

    "review_priority_score",

    "decision_reason_code",

    "data_origin",
    "generator_version",
}


HUMAN_REVIEW_REQUIRED_COLUMNS = {
    "review_id",

    "decision_id",
    "recommendation_id",

    "reviewer_role",

    "requested_at",
    "completed_at",

    "decision",

    "reason_code",
    "free_text",

    "data_origin",
    "generator_version",
}


# ============================================================
# LEAKAGE PROTECTION
# ============================================================

FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS = (
    "ground_truth",
    "true_best",
    "true_outcome",
    "actual_future",
    "future_outcome",
    "oracle_",
)


FORBIDDEN_PAYLOAD_KEY_FRAGMENTS = (
    "ground_truth",
    "true_best",
    "true_outcome",
    "actual_future",
    "future_outcome",
    "oracle_",
)


# ============================================================
# BASIC HELPERS
# ============================================================


def _is_missing(
    value: Any,
) -> bool:
    """
    Safe scalar missing-value check.
    """

    if value is None:
        return True

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        return False

    try:
        result = pd.isna(
            value
        )

        if isinstance(
            result,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(
                result
            )

    except (
        TypeError,
        ValueError,
    ):
        pass

    return False


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Convert scalar to finite float.
    """

    if _is_missing(
        value
    ):
        return float(
            default
        )

    try:
        number = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return float(
            default
        )

    if not np.isfinite(
        number
    ):
        return float(
            default
        )

    return float(
        number
    )


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Convert scalar to integer.
    """

    if _is_missing(
        value
    ):
        return int(
            default
        )

    try:
        return int(
            round(
                float(
                    value
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return int(
            default
        )


def _to_bool(
    value: Any,
) -> bool:
    """
    Normalize boolean-like scalar.
    """

    if _is_missing(
        value
    ):
        return False

    if isinstance(
        value,
        (
            bool,
            np.bool_,
        ),
    ):
        return bool(
            value
        )

    if isinstance(
        value,
        (
            int,
            float,
            np.integer,
            np.floating,
        ),
    ):
        return bool(
            value
        )

    text = str(
        value
    ).strip().upper()

    if text in {
        "TRUE",
        "YES",
        "Y",
        "1",
    }:
        return True

    if text in {
        "FALSE",
        "NO",
        "N",
        "0",
    }:
        return False

    return bool(
        text
    )


# ============================================================
# JSON HELPERS
# ============================================================


def _json_ready(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values into canonical JSON-safe values.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(
                key
            ):
            _json_ready(
                item
            )

            for key,
            item
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_ready(
                item
            )
            for item
            in value
        ]

    if isinstance(
        value,
        pd.Timestamp,
    ):

        if pd.isna(
            value
        ):
            return None

        return value.isoformat()

    if isinstance(
        value,
        np.datetime64,
    ):

        timestamp = pd.Timestamp(
            value
        )

        if pd.isna(
            timestamp
        ):
            return None

        return timestamp.isoformat()

    if isinstance(
        value,
        np.integer,
    ):
        return int(
            value
        )

    if isinstance(
        value,
        np.floating,
    ):

        if not np.isfinite(
            value
        ):
            return None

        return float(
            value
        )

    if isinstance(
        value,
        np.bool_,
    ):
        return bool(
            value
        )

    if _is_missing(
        value
    ):
        return None

    return value


def _canonical_json(
    payload: Mapping[str, Any],
) -> str:
    """
    Deterministic compact JSON.
    """

    return json.dumps(
        _json_ready(
            payload
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=False,
    )


def _parse_json_object(
    value: Any,
    field_name: str,
    record_id: str,
) -> dict[str, Any]:
    """
    Parse JSON object.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return dict(
            value
        )

    try:
        payload = json.loads(
            str(
                value
            )
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            f"{record_id}: invalid {field_name}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"{record_id}: {field_name} "
            "must contain a JSON object"
        )

    return payload


# ============================================================
# CONFIG
# ============================================================


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Read timezone-aware generation window.
    """

    time_config = generation.get(
        "time"
    )

    if not isinstance(
        time_config,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.time configuration"
        )

    start_value = time_config.get(
        "start_date",
        time_config.get(
            "start"
        ),
    )

    end_value = time_config.get(
        "end_date",
        time_config.get(
            "end"
        ),
    )

    timezone = str(
        time_config.get(
            "timezone",
            "Asia/Kolkata",
        )
    )

    if start_value is None:
        raise KeyError(
            "Missing generation.time.start_date"
        )

    if end_value is None:
        raise KeyError(
            "Missing generation.time.end_date"
        )

    start = pd.Timestamp(
        start_value
    )

    end = pd.Timestamp(
        end_value
    )

    if start.tzinfo is None:

        start = start.tz_localize(
            timezone
        )

    else:

        start = start.tz_convert(
            timezone
        )

    if end.tzinfo is None:

        end = end.tz_localize(
            timezone
        )

    else:

        end = end.tz_convert(
            timezone
        )

    if end <= start:
        raise ValueError(
            "Generation end must be after generation start"
        )

    return (
        start,
        end,
        timezone,
    )


def _get_audit_target_count(
    generation: Mapping[str, Any],
) -> int:
    """
    Read governance.audit_events_target_count.
    """

    governance = generation.get(
        "governance"
    )

    if not isinstance(
        governance,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.governance configuration"
        )

    value = governance.get(
        "audit_events_target_count"
    )

    if value is None:
        raise KeyError(
            "Missing governance.audit_events_target_count"
        )

    target = int(
        value
    )

    if target <= 0:
        raise ValueError(
            "audit_events_target_count must be > 0"
        )

    return target


# ============================================================
# INPUT VALIDATION
# ============================================================


def _require_columns(
    name: str,
    dataframe: pd.DataFrame,
    required: set[str],
    primary_key: str,
    allow_empty: bool = False,
) -> None:
    """
    Generic DataFrame validation.
    """

    if (
        dataframe.empty
        and
        not allow_empty
    ):
        raise ValueError(
            f"{name} DataFrame cannot be empty"
        )

    missing = (
        required
        -
        set(
            dataframe.columns
        )
    )

    if missing:
        raise ValueError(
            f"{name} DataFrame is missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if dataframe.empty:
        return

    if (
        dataframe[
            primary_key
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            f"{name}.{primary_key} cannot contain nulls"
        )

    if (
        dataframe[
            primary_key
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            f"Duplicate {primary_key} values found in {name}"
        )


def _validate_inputs(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
) -> None:
    """
    Validate frozen upstream Governance outputs.
    """

    _require_columns(
        name="recommendations",
        dataframe=recommendations,
        required=RECOMMENDATION_REQUIRED_COLUMNS,
        primary_key="recommendation_id",
    )

    _require_columns(
        name="compliance_checks",
        dataframe=compliance_checks,
        required=COMPLIANCE_REQUIRED_COLUMNS,
        primary_key="compliance_check_id",
    )

    _require_columns(
        name="trust_decisions",
        dataframe=trust_decisions,
        required=DECISION_REQUIRED_COLUMNS,
        primary_key="decision_id",
    )

    _require_columns(
        name="human_reviews",
        dataframe=human_reviews,
        required=HUMAN_REVIEW_REQUIRED_COLUMNS,
        primary_key="review_id",
        allow_empty=True,
    )

    recommendation_ids = set(
        recommendations[
            "recommendation_id"
        ]
        .astype(
            str
        )
    )

    decision_recommendation_ids = set(
        trust_decisions[
            "recommendation_id"
        ]
        .astype(
            str
        )
    )

    if (
        recommendation_ids
        !=
        decision_recommendation_ids
    ):
        raise ValueError(
            "Every recommendation must map to exactly "
            "one trust decision before audit generation"
        )

    if (
        trust_decisions[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Multiple trust decisions found for "
            "one recommendation"
        )

    decision_ids = set(
        trust_decisions[
            "decision_id"
        ]
        .astype(
            str
        )
    )

    invalid_check_decisions = (
        set(
            compliance_checks[
                "decision_id"
            ]
            .astype(
                str
            )
        )
        -
        decision_ids
    )

    if invalid_check_decisions:
        raise ValueError(
            "Compliance checks reference invalid decisions"
        )

    invalid_check_recommendations = (
        set(
            compliance_checks[
                "recommendation_id"
            ]
            .astype(
                str
            )
        )
        -
        recommendation_ids
    )

    if invalid_check_recommendations:
        raise ValueError(
            "Compliance checks reference invalid recommendations"
        )

    if not human_reviews.empty:

        invalid_review_decisions = (
            set(
                human_reviews[
                    "decision_id"
                ]
                .astype(
                    str
                )
            )
            -
            decision_ids
        )

        if invalid_review_decisions:
            raise ValueError(
                "Human reviews reference invalid decisions"
            )

        invalid_review_recommendations = (
            set(
                human_reviews[
                    "recommendation_id"
                ]
                .astype(
                    str
                )
            )
            -
            recommendation_ids
        )

        if invalid_review_recommendations:
            raise ValueError(
                "Human reviews reference invalid recommendations"
            )

    # Exact recommendation ↔ decision lineage.
    decision_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
    )

    for check in compliance_checks.itertuples(
        index=False
    ):

        linked_recommendation = str(
            decision_lookup.loc[
                str(
                    check.decision_id
                ),
                "recommendation_id",
            ]
        )

        if (
            linked_recommendation
            !=
            str(
                check.recommendation_id
            )
        ):
            raise ValueError(
                f"{check.compliance_check_id}: "
                "decision/recommendation lineage mismatch"
            )

    for review in human_reviews.itertuples(
        index=False
    ):

        linked_recommendation = str(
            decision_lookup.loc[
                str(
                    review.decision_id
                ),
                "recommendation_id",
            ]
        )

        if (
            linked_recommendation
            !=
            str(
                review.recommendation_id
            )
        ):
            raise ValueError(
                f"{review.review_id}: "
                "decision/recommendation lineage mismatch"
            )


# ============================================================
# STABLE TIE BREAK
# ============================================================


def _stable_fraction(
    value: str,
) -> float:
    """
    Stable deterministic pseudo-fraction in [0,1).

    Used only as a deterministic tie-breaker.

    It is not stochastic business logic.
    """

    digest = hashlib.sha256(
        str(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    integer = int(
        digest[
            :12
        ],
        16,
    )

    maximum = float(
        16 ** 12
    )

    return float(
        integer
        /
        maximum
    )


# ============================================================
# AUDIT EVENT BUILDER
# ============================================================


def _event(
    recommendation_id: str,
    decision_id: str,
    domain: str,
    use_case: str,
    target_entity_type: str,
    target_entity_id: str,
    event_type: str,
    event_at: pd.Timestamp,
    actor_type: str,
    actor_id: str,
    source_record_type: str,
    source_record_id: str,
    event_summary: str,
    details: Mapping[str, Any],
    data_origin: str,
    generator_version: str,
) -> dict[str, Any]:
    """
    Build pre-hash audit event.
    """

    if event_type not in (
        VALID_EVENT_TYPES
    ):
        raise ValueError(
            f"Unsupported audit event type: {event_type}"
        )

    if actor_type not in (
        VALID_ACTOR_TYPES
    ):
        raise ValueError(
            f"Unsupported actor_type: {actor_type}"
        )

    return {
        "recommendation_id":
            str(
                recommendation_id
            ),

        "decision_id":
            str(
                decision_id
            ),

        "domain":
            str(
                domain
            ),

        "use_case":
            str(
                use_case
            ),

        "target_entity_type":
            str(
                target_entity_type
            ),

        "target_entity_id":
            str(
                target_entity_id
            ),

        "event_type":
            str(
                event_type
            ),

        "event_at":
            pd.Timestamp(
                event_at
            ),

        "actor_type":
            actor_type,

        "actor_id":
            str(
                actor_id
            ),

        "source_record_type":
            str(
                source_record_type
            ),

        "source_record_id":
            str(
                source_record_id
            ),

        "event_status":
            EVENT_STATUS_RECORDED,

        "event_summary":
            str(
                event_summary
            ),

        "details_json":
            _canonical_json(
                details
            ),

        "data_origin":
            str(
                data_origin
            ),

        "generator_version":
            str(
                generator_version
            ),
    }


# ============================================================
# RECOMMENDATION EVENTS
# ============================================================


def _build_recommendation_events(
    recommendations: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    data_origin: str,
    generator_version: str,
) -> list[dict[str, Any]]:
    """
    One recommendation-recorded event per recommendation.
    """

    decision_lookup = (
        trust_decisions
        .set_index(
            "recommendation_id"
        )
        .to_dict(
            orient="index"
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for recommendation in recommendations.to_dict(
        orient="records"
    ):

        recommendation_id = str(
            recommendation[
                "recommendation_id"
            ]
        )

        decision = (
            decision_lookup[
                recommendation_id
            ]
        )

        evidence = _parse_json_object(
            value=
                recommendation[
                    "evidence_json"
                ],

            field_name=
                "evidence_json",

            record_id=
                recommendation_id,
        )

        expected_impact = _parse_json_object(
            value=
                recommendation[
                    "expected_impact"
                ],

            field_name=
                "expected_impact",

            record_id=
                recommendation_id,
        )

        rows.append(
            _event(
                recommendation_id=
                    recommendation_id,

                decision_id=
                    str(
                        decision[
                            "decision_id"
                        ]
                    ),

                domain=
                    recommendation[
                        "domain"
                    ],

                use_case=
                    recommendation[
                        "use_case"
                    ],

                target_entity_type=
                    recommendation[
                        "target_entity_type"
                    ],

                target_entity_id=
                    recommendation[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_RECOMMENDATION_RECORDED,

                event_at=
                    recommendation[
                        "generated_at"
                    ],

                actor_type=
                    ACTOR_SYSTEM,

                actor_id=
                    ACTOR_RECOMMENDATION_ENGINE,

                source_record_type=
                    "RECOMMENDATION",

                source_record_id=
                    recommendation_id,

                event_summary=
                    (
                        "Evidence-backed governance "
                        "recommendation recorded."
                    ),

                details={
                    "recommendation_type":
                        recommendation[
                            "recommendation_type"
                        ],

                    "confidence":
                        round(
                            _safe_float(
                                recommendation[
                                    "confidence"
                                ]
                            ),
                            6,
                        ),

                    "risk_level":
                        recommendation[
                            "risk_level"
                        ],

                    "recommendation_status":
                        recommendation[
                            "status"
                        ],

                    "evidence_source_record_type":
                        evidence.get(
                            "source_record_type"
                        ),

                    "evidence_source_record_id":
                        evidence.get(
                            "source_record_id"
                        ),

                    "expected_impact_metric":
                        expected_impact.get(
                            "metric"
                        ),

                    "expected_impact_direction":
                        expected_impact.get(
                            "direction"
                        ),
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

    return rows


# ============================================================
# COMPLIANCE SUMMARY EVENTS
# ============================================================


def _build_compliance_summary_events(
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    data_origin: str,
    generator_version: str,
) -> list[dict[str, Any]]:
    """
    One compliance-evaluation summary event per decision.
    """

    check_work = (
        compliance_checks
        .copy()
    )

    check_work[
        "_checked_at_utc"
    ] = pd.to_datetime(
        check_work[
            "checked_at"
        ],
        errors="raise",
        utc=True,
    )

    decision_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
        .to_dict(
            orient="index"
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for (
        decision_id,
        group,
    ) in check_work.groupby(
        "decision_id",
        sort=True,
    ):

        decision_id = str(
            decision_id
        )

        decision = (
            decision_lookup[
                decision_id
            ]
        )

        latest_check_index = (
            group[
                "_checked_at_utc"
            ]
            .idxmax()
        )

        latest_check_at = (
            compliance_checks.loc[
                latest_check_index,
                "checked_at",
            ]
        )

        result_counts = (
            group[
                "result"
            ]
            .astype(
                str
            )
            .value_counts()
        )

        rules = sorted(
            group[
                "rule_code"
            ]
            .astype(
                str
            )
            .tolist()
        )

        rows.append(
            _event(
                recommendation_id=
                    decision[
                        "recommendation_id"
                    ],

                decision_id=
                    decision_id,

                domain=
                    decision[
                        "domain"
                    ],

                use_case=
                    decision[
                        "use_case"
                    ],

                target_entity_type=
                    decision[
                        "target_entity_type"
                    ],

                target_entity_id=
                    decision[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_COMPLIANCE_EVALUATION_COMPLETED,

                event_at=
                    latest_check_at,

                actor_type=
                    ACTOR_SYSTEM,

                actor_id=
                    ACTOR_COMPLIANCE_AGENT,

                source_record_type=
                    "COMPLIANCE_SET",

                source_record_id=
                    decision_id,

                event_summary=
                    (
                        "Compliance evaluation completed "
                        "for the governance decision."
                    ),

                details={
                    "checks_count":
                        int(
                            len(
                                group
                            )
                        ),

                    "pass_count":
                        int(
                            result_counts.get(
                                RESULT_PASS,
                                0,
                            )
                        ),

                    "warn_count":
                        int(
                            result_counts.get(
                                RESULT_WARN,
                                0,
                            )
                        ),

                    "fail_count":
                        int(
                            result_counts.get(
                                RESULT_FAIL,
                                0,
                            )
                        ),

                    "review_required_count":
                        int(
                            result_counts.get(
                                RESULT_REVIEW_REQUIRED,
                                0,
                            )
                        ),

                    "rules_evaluated":
                        rules,
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

    return rows


# ============================================================
# HUMAN REVIEW EVENTS
# ============================================================


def _build_human_review_events(
    human_reviews: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    data_origin: str,
    generator_version: str,
) -> list[dict[str, Any]]:
    """
    Two audit events for every actual human review:

        requested
        completed
    """

    if human_reviews.empty:
        return []

    decision_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
        .to_dict(
            orient="index"
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for review in human_reviews.to_dict(
        orient="records"
    ):

        decision_id = str(
            review[
                "decision_id"
            ]
        )

        review_id = str(
            review[
                "review_id"
            ]
        )

        decision = (
            decision_lookup[
                decision_id
            ]
        )

        reviewer_role = str(
            review[
                "reviewer_role"
            ]
        )

        # ----------------------------------------------------
        # REQUESTED
        # ----------------------------------------------------

        rows.append(
            _event(
                recommendation_id=
                    review[
                        "recommendation_id"
                    ],

                decision_id=
                    decision_id,

                domain=
                    decision[
                        "domain"
                    ],

                use_case=
                    decision[
                        "use_case"
                    ],

                target_entity_type=
                    decision[
                        "target_entity_type"
                    ],

                target_entity_id=
                    decision[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_HUMAN_REVIEW_REQUESTED,

                event_at=
                    review[
                        "requested_at"
                    ],

                actor_type=
                    ACTOR_SYSTEM,

                actor_id=
                    ACTOR_HUMAN_REVIEW_ROUTER,

                source_record_type=
                    "HUMAN_REVIEW",

                source_record_id=
                    review_id,

                event_summary=
                    (
                        "Recommendation routed to "
                        "human governance review."
                    ),

                details={
                    "review_id":
                        review_id,

                    "reviewer_role":
                        reviewer_role,

                    "recommendation_risk_level":
                        decision[
                            "recommendation_risk_level"
                        ],

                    "review_priority_score":
                        round(
                            _safe_float(
                                decision[
                                    "review_priority_score"
                                ]
                            ),
                            6,
                        ),
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ----------------------------------------------------
        # COMPLETED
        # ----------------------------------------------------

        rows.append(
            _event(
                recommendation_id=
                    review[
                        "recommendation_id"
                    ],

                decision_id=
                    decision_id,

                domain=
                    decision[
                        "domain"
                    ],

                use_case=
                    decision[
                        "use_case"
                    ],

                target_entity_type=
                    decision[
                        "target_entity_type"
                    ],

                target_entity_id=
                    decision[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_HUMAN_REVIEW_COMPLETED,

                event_at=
                    review[
                        "completed_at"
                    ],

                actor_type=
                    ACTOR_HUMAN,

                actor_id=
                    reviewer_role,

                source_record_type=
                    "HUMAN_REVIEW",

                source_record_id=
                    review_id,

                event_summary=
                    (
                        "Human governance review completed."
                    ),

                details={
                    "review_id":
                        review_id,

                    "reviewer_role":
                        reviewer_role,

                    "review_decision":
                        review[
                            "decision"
                        ],

                    "reason_code":
                        review[
                            "reason_code"
                        ],

                    "review_comment":
                        review[
                            "free_text"
                        ],
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

    return rows


# ============================================================
# TRUST DECISION EVENTS
# ============================================================


def _build_trust_decision_events(
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    data_origin: str,
    generator_version: str,
) -> list[dict[str, Any]]:
    """
    One final trust-decision event per recommendation.
    """

    review_role_by_id: dict[
        str,
        str,
    ] = {}

    if not human_reviews.empty:

        review_role_by_id = (
            human_reviews
            .set_index(
                "review_id"
            )[
                "reviewer_role"
            ]
            .astype(
                str
            )
            .to_dict()
        )

    rows: list[
        dict[str, Any]
    ] = []

    for decision in trust_decisions.to_dict(
        orient="records"
    ):

        human_review_required = (
            _to_bool(
                decision[
                    "human_review_required"
                ]
            )
        )

        human_review_id = (
            None
            if _is_missing(
                decision[
                    "human_review_id"
                ]
            )
            else str(
                decision[
                    "human_review_id"
                ]
            )
        )

        if human_review_required:

            actor_type = (
                ACTOR_HUMAN
            )

            actor_id = (
                review_role_by_id.get(
                    str(
                        human_review_id
                    ),
                    "HUMAN_GOVERNANCE_REVIEWER",
                )
            )

        else:

            actor_type = (
                ACTOR_SYSTEM
            )

            actor_id = (
                ACTOR_TRUST_POLICY_ENGINE
            )

        rows.append(
            _event(
                recommendation_id=
                    decision[
                        "recommendation_id"
                    ],

                decision_id=
                    decision[
                        "decision_id"
                    ],

                domain=
                    decision[
                        "domain"
                    ],

                use_case=
                    decision[
                        "use_case"
                    ],

                target_entity_type=
                    decision[
                        "target_entity_type"
                    ],

                target_entity_id=
                    decision[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_TRUST_DECISION_RECORDED,

                event_at=
                    decision[
                        "decided_at"
                    ],

                actor_type=
                    actor_type,

                actor_id=
                    actor_id,

                source_record_type=
                    "TRUST_DECISION",

                source_record_id=
                    decision[
                        "decision_id"
                    ],

                event_summary=
                    (
                        "Final governance trust "
                        "decision recorded."
                    ),

                details={
                    "decision_mode":
                        decision[
                            "decision_mode"
                        ],

                    "decision":
                        decision[
                            "decision"
                        ],

                    "decision_reason_code":
                        decision[
                            "decision_reason_code"
                        ],

                    "recommendation_confidence":
                        round(
                            _safe_float(
                                decision[
                                    "recommendation_confidence"
                                ]
                            ),
                            6,
                        ),

                    "recommendation_risk_level":
                        decision[
                            "recommendation_risk_level"
                        ],

                    "human_review_required":
                        human_review_required,

                    "human_review_id":
                        human_review_id,

                    "compliance_checks_count":
                        _safe_int(
                            decision[
                                "compliance_checks_count"
                            ]
                        ),

                    "compliance_pass_count":
                        _safe_int(
                            decision[
                                "compliance_pass_count"
                            ]
                        ),

                    "compliance_warn_count":
                        _safe_int(
                            decision[
                                "compliance_warn_count"
                            ]
                        ),

                    "compliance_fail_count":
                        _safe_int(
                            decision[
                                "compliance_fail_count"
                            ]
                        ),

                    "compliance_review_required_count":
                        _safe_int(
                            decision[
                                "compliance_review_required_count"
                            ]
                        ),
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

    return rows


# ============================================================
# COMPLIANCE DETAIL PRIORITY
# ============================================================


def _prepare_compliance_detail_pool(
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add transparent deterministic ranking features.

    Detailed-event selection is an audit-storage allocation rule,
    not a business prediction.
    """

    decision_context = (
        trust_decisions[
            [
                "decision_id",
                "recommendation_risk_level",
                "review_priority_score",
                "human_review_required",
            ]
        ]
        .copy()
    )

    work = (
        compliance_checks
        .merge(
            decision_context,
            on="decision_id",
            how="left",
            validate="many_to_one",
        )
    )

    work[
        "_result_priority"
    ] = (
        work[
            "result"
        ]
        .astype(
            str
        )
        .map(
            RESULT_PRIORITY
        )
        .fillna(
            0
        )
        .astype(
            int
        )
    )

    work[
        "_severity_priority"
    ] = (
        work[
            "severity"
        ]
        .astype(
            str
        )
        .map(
            SEVERITY_PRIORITY
        )
        .fillna(
            0
        )
        .astype(
            int
        )
    )

    work[
        "_risk_priority"
    ] = (
        work[
            "recommendation_risk_level"
        ]
        .astype(
            str
        )
        .map(
            RISK_PRIORITY
        )
        .fillna(
            0
        )
        .astype(
            int
        )
    )

    work[
        "_stable_tie_break"
    ] = [
        _stable_fraction(
            value
        )
        for value
        in work[
            "compliance_check_id"
        ]
        .astype(
            str
        )
    ]

    work[
        "_detail_priority"
    ] = (
        0.36
        *
        (
            work[
                "_result_priority"
            ]
            /
            max(
                RESULT_PRIORITY.values()
            )
        )
        +
        0.18
        *
        (
            work[
                "_severity_priority"
            ]
            /
            max(
                SEVERITY_PRIORITY.values()
            )
        )
        +
        0.18
        *
        (
            work[
                "_risk_priority"
            ]
            /
            max(
                RISK_PRIORITY.values()
            )
        )
        +
        0.16
        *
        pd.to_numeric(
            work[
                "review_priority_score"
            ],
            errors="coerce",
        )
        .fillna(
            0.0
        )
        .clip(
            0.0,
            1.0,
        )
        +
        0.08
        *
        (
            work[
                "human_review_required"
            ]
            .astype(
                bool
            )
            .astype(
                int
            )
        )
        +
        0.04
        *
        work[
            "_stable_tie_break"
        ]
    )

    return work


# ============================================================
# SELECT DETAILED COMPLIANCE EVENTS
# ============================================================


def _select_detailed_checks(
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    detail_target_count: int,
) -> pd.DataFrame:
    """
    Deterministically choose exact detailed check population.

    Hard guarantees:

    - every non-PASS check is retained;
    - every decision receives at least one detailed check;
    - remaining capacity is filled by audit significance.
    """

    if detail_target_count < 0:
        raise ValueError(
            "detail_target_count cannot be negative"
        )

    if detail_target_count == 0:

        return (
            compliance_checks
            .iloc[
                0:0
            ]
            .copy()
        )

    if (
        detail_target_count
        >
        len(
            compliance_checks
        )
    ):
        raise ValueError(
            "Audit detail target exceeds available "
            "compliance checks"
        )

    work = (
        _prepare_compliance_detail_pool(
            compliance_checks=
                compliance_checks,

            trust_decisions=
                trust_decisions,
        )
    )

    selected_ids: set[str] = set()

    # ========================================================
    # 1. ALL NON-PASS CHECKS
    # ========================================================

    exceptions = (
        work.loc[
            work[
                "result"
            ]
            .astype(
                str
            )
            !=
            RESULT_PASS
        ]
        .sort_values(
            [
                "_result_priority",
                "_severity_priority",
                "_detail_priority",
                "compliance_check_id",
            ],
            ascending=[
                False,
                False,
                False,
                True,
            ],
        )
    )

    if len(
        exceptions
    ) > detail_target_count:
        raise ValueError(
            "Configured audit target is too small "
            "to retain every non-PASS compliance event"
        )

    selected_ids.update(
        exceptions[
            "compliance_check_id"
        ]
        .astype(
            str
        )
        .tolist()
    )

    # ========================================================
    # 2. AT LEAST ONE CHECK PER DECISION
    # ========================================================

    decisions_already_covered = set(
        work.loc[
            work[
                "compliance_check_id"
            ]
            .astype(
                str
            )
            .isin(
                selected_ids
            ),
            "decision_id",
        ]
        .astype(
            str
        )
    )

    all_decision_ids = sorted(
        work[
            "decision_id"
        ]
        .astype(
            str
        )
        .unique()
        .tolist()
    )

    missing_decisions = [
        decision_id
        for decision_id
        in all_decision_ids
        if decision_id
        not in decisions_already_covered
    ]

    minimum_needed = (
        len(
            selected_ids
        )
        +
        len(
            missing_decisions
        )
    )

    if minimum_needed > detail_target_count:
        raise ValueError(
            "Configured audit target is too small to "
            "retain every compliance exception AND "
            "at least one detailed check per decision"
        )

    for decision_id in (
        missing_decisions
    ):

        group = (
            work.loc[
                work[
                    "decision_id"
                ]
                .astype(
                    str
                )
                ==
                decision_id
            ]
            .sort_values(
                [
                    "_detail_priority",
                    "_stable_tie_break",
                    "compliance_check_id",
                ],
                ascending=[
                    False,
                    False,
                    True,
                ],
            )
        )

        selected_ids.add(
            str(
                group.iloc[
                    0
                ][
                    "compliance_check_id"
                ]
            )
        )

    # ========================================================
    # 3. FILL REMAINING CAPACITY
    # ========================================================

    remaining_needed = (
        detail_target_count
        -
        len(
            selected_ids
        )
    )

    if remaining_needed > 0:

        remaining = (
            work.loc[
                ~work[
                    "compliance_check_id"
                ]
                .astype(
                    str
                )
                .isin(
                    selected_ids
                )
            ]
            .sort_values(
                [
                    "_detail_priority",
                    "_result_priority",
                    "_severity_priority",
                    "_stable_tie_break",
                    "compliance_check_id",
                ],
                ascending=[
                    False,
                    False,
                    False,
                    False,
                    True,
                ],
            )
        )

        additional_ids = (
            remaining[
                "compliance_check_id"
            ]
            .astype(
                str
            )
            .head(
                remaining_needed
            )
            .tolist()
        )

        selected_ids.update(
            additional_ids
        )

    if len(
        selected_ids
    ) != detail_target_count:
        raise ValueError(
            "Detailed compliance-event selection "
            "failed exact target count"
        )

    selected = (
        compliance_checks.loc[
            compliance_checks[
                "compliance_check_id"
            ]
            .astype(
                str
            )
            .isin(
                selected_ids
            )
        ]
        .copy()
    )

    selected = (
        selected
        .sort_values(
            [
                "decision_id",
                "checked_at",
                "compliance_check_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    return selected


# ============================================================
# BUILD DETAILED COMPLIANCE AUDIT EVENTS
# ============================================================


def _build_compliance_detail_events(
    selected_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    data_origin: str,
    generator_version: str,
) -> list[dict[str, Any]]:
    """
    Audit selected individual compliance checks.
    """

    decision_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
        .to_dict(
            orient="index"
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for check in selected_checks.to_dict(
        orient="records"
    ):

        decision_id = str(
            check[
                "decision_id"
            ]
        )

        decision = (
            decision_lookup[
                decision_id
            ]
        )

        check_details = _parse_json_object(
            value=
                check[
                    "evidence_json"
                ],

            field_name=
                "compliance evidence_json",

            record_id=
                str(
                    check[
                        "compliance_check_id"
                    ]
                ),
        )

        rows.append(
            _event(
                recommendation_id=
                    check[
                        "recommendation_id"
                    ],

                decision_id=
                    decision_id,

                domain=
                    decision[
                        "domain"
                    ],

                use_case=
                    decision[
                        "use_case"
                    ],

                target_entity_type=
                    decision[
                        "target_entity_type"
                    ],

                target_entity_id=
                    decision[
                        "target_entity_id"
                    ],

                event_type=
                    EVENT_COMPLIANCE_CHECK_RECORDED,

                event_at=
                    check[
                        "checked_at"
                    ],

                actor_type=
                    ACTOR_SYSTEM,

                actor_id=
                    ACTOR_COMPLIANCE_AGENT,

                source_record_type=
                    "COMPLIANCE_CHECK",

                source_record_id=
                    check[
                        "compliance_check_id"
                    ],

                event_summary=
                    (
                        f"{check['rule_code']} evaluated "
                        f"as {check['result']}."
                    ),

                details={
                    "rule_code":
                        check[
                            "rule_code"
                        ],

                    "rule_name":
                        check[
                            "rule_name"
                        ],

                    "result":
                        check[
                            "result"
                        ],

                    "severity":
                        check[
                            "severity"
                        ],

                    "reason":
                        check[
                            "reason"
                        ],

                    "check_evidence":
                        check_details,
                },

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

    return rows


# ============================================================
# HASH MATERIAL
# ============================================================


def _hash_material(
    row: Mapping[str, Any],
    previous_event_hash: str,
) -> str:
    """
    Canonical payload used to calculate event_hash.
    """

    payload = {
        "audit_event_id":
            row[
                "audit_event_id"
            ],

        "recommendation_id":
            row[
                "recommendation_id"
            ],

        "decision_id":
            row[
                "decision_id"
            ],

        "domain":
            row[
                "domain"
            ],

        "use_case":
            row[
                "use_case"
            ],

        "target_entity_type":
            row[
                "target_entity_type"
            ],

        "target_entity_id":
            row[
                "target_entity_id"
            ],

        "event_sequence":
            _safe_int(
                row[
                    "event_sequence"
                ]
            ),

        "event_type":
            row[
                "event_type"
            ],

        "event_at":
            row[
                "event_at"
            ],

        "actor_type":
            row[
                "actor_type"
            ],

        "actor_id":
            row[
                "actor_id"
            ],

        "source_record_type":
            row[
                "source_record_type"
            ],

        "source_record_id":
            row[
                "source_record_id"
            ],

        "event_status":
            row[
                "event_status"
            ],

        "event_summary":
            row[
                "event_summary"
            ],

        "details_json":
            row[
                "details_json"
            ],

        "previous_event_hash":
            previous_event_hash,

        "data_origin":
            row[
                "data_origin"
            ],

        "generator_version":
            row[
                "generator_version"
            ],
    }

    return _canonical_json(
        payload
    )


def _calculate_event_hash(
    row: Mapping[str, Any],
    previous_event_hash: str,
) -> str:
    """
    SHA-256 hash of canonical immutable audit material.
    """

    material = _hash_material(
        row=
            row,

        previous_event_hash=
            previous_event_hash,
    )

    return hashlib.sha256(
        material.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# SEAL AUDIT EVENTS
# ============================================================


def _seal_events(
    audit_events: pd.DataFrame,
) -> pd.DataFrame:
    """
    Sort audit events, assign IDs, assign recommendation-local
    sequence numbers and create chained SHA-256 integrity hashes.
    """

    work = audit_events.copy()

    work[
        "_event_at_utc"
    ] = pd.to_datetime(
        work[
            "event_at"
        ],
        errors="raise",
        utc=True,
    )

    work[
        "_event_order"
    ] = (
        work[
            "event_type"
        ]
        .map(
            EVENT_ORDER
        )
    )

    if (
        work[
            "_event_order"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Unknown audit event type during sealing"
        )

    # Global chronological ledger order.
    work = (
        work
        .sort_values(
            [
                "_event_at_utc",
                "_event_order",
                "recommendation_id",
                "source_record_id",
            ],
            ascending=[
                True,
                True,
                True,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    work[
        "audit_event_id"
    ] = [
        generate_id(
            "AUDIT_SYN",
            sequence,
            width=8,
        )
        for sequence
        in range(
            1,
            len(
                work
            )
            + 1,
        )
    ]

    # Recommendation-local chronological sequence.
    work[
        "event_sequence"
    ] = (
        work
        .groupby(
            "recommendation_id",
            sort=False,
        )
        .cumcount()
        +
        1
    )

    work[
        "previous_event_hash"
    ] = ""

    work[
        "event_hash"
    ] = ""

    for (
        recommendation_id,
        group_indices,
    ) in work.groupby(
        "recommendation_id",
        sort=False,
    ).groups.items():

        previous_hash = (
            "GENESIS"
        )

        ordered_indices = (
            list(
                group_indices
            )
        )

        ordered_indices.sort(
            key=lambda index: int(
                work.loc[
                    index,
                    "event_sequence",
                ]
            )
        )

        for index in ordered_indices:

            row = (
                work.loc[
                    index
                ]
                .to_dict()
            )

            work.loc[
                index,
                "previous_event_hash",
            ] = previous_hash

            event_hash = (
                _calculate_event_hash(
                    row=row,
                    previous_event_hash=
                        previous_hash,
                )
            )

            work.loc[
                index,
                "event_hash",
            ] = event_hash

            previous_hash = (
                event_hash
            )

    work = work.drop(
        columns=[
            "_event_at_utc",
            "_event_order",
        ]
    )

    output_columns = [
        "audit_event_id",

        "recommendation_id",
        "decision_id",

        "domain",
        "use_case",

        "target_entity_type",
        "target_entity_id",

        "event_sequence",

        "event_type",
        "event_at",

        "actor_type",
        "actor_id",

        "source_record_type",
        "source_record_id",

        "event_status",

        "event_summary",
        "details_json",

        "previous_event_hash",
        "event_hash",

        "data_origin",
        "generator_version",
    ]

    return (
        work[
            output_columns
        ]
        .copy()
    )


# ============================================================
# PUBLIC GENERATOR
# ============================================================


def generate_audit_events(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Generate deterministic tamper-evident governance audit events.
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    _validate_inputs(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        human_reviews=
            human_reviews,
    )

    target_count = (
        _get_audit_target_count(
            generation
        )
    )

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
    # MANDATORY LIFECYCLE EVENTS
    # ========================================================

    recommendation_events = (
        _build_recommendation_events(
            recommendations=
                recommendations,

            trust_decisions=
                trust_decisions,

            data_origin=
                data_origin,

            generator_version=
                generator_version,
        )
    )

    compliance_summary_events = (
        _build_compliance_summary_events(
            compliance_checks=
                compliance_checks,

            trust_decisions=
                trust_decisions,

            data_origin=
                data_origin,

            generator_version=
                generator_version,
        )
    )

    human_review_events = (
        _build_human_review_events(
            human_reviews=
                human_reviews,

            trust_decisions=
                trust_decisions,

            data_origin=
                data_origin,

            generator_version=
                generator_version,
        )
    )

    trust_decision_events = (
        _build_trust_decision_events(
            trust_decisions=
                trust_decisions,

            human_reviews=
                human_reviews,

            data_origin=
                data_origin,

            generator_version=
                generator_version,
        )
    )

    mandatory_events = (
        recommendation_events
        +
        compliance_summary_events
        +
        human_review_events
        +
        trust_decision_events
    )

    mandatory_count = len(
        mandatory_events
    )

    detail_target_count = (
        target_count
        -
        mandatory_count
    )

    if detail_target_count < 0:

        raise ValueError(
            "Configured audit_events_target_count is smaller "
            "than mandatory governance lifecycle coverage. "
            f"Target={target_count}, "
            f"mandatory={mandatory_count}"
        )

    # ========================================================
    # SELECT DETAILED COMPLIANCE CHECKS
    # ========================================================

    selected_checks = (
        _select_detailed_checks(
            compliance_checks=
                compliance_checks,

            trust_decisions=
                trust_decisions,

            detail_target_count=
                detail_target_count,
        )
    )

    detailed_check_events = (
        _build_compliance_detail_events(
            selected_checks=
                selected_checks,

            trust_decisions=
                trust_decisions,

            data_origin=
                data_origin,

            generator_version=
                generator_version,
        )
    )

    all_events = (
        mandatory_events
        +
        detailed_check_events
    )

    if len(
        all_events
    ) != target_count:

        raise ValueError(
            "Audit event assembly failed exact configured count. "
            f"Expected={target_count}, "
            f"actual={len(all_events)}"
        )

    audit_events = (
        _seal_events(
            pd.DataFrame(
                all_events
            )
        )
    )

    validate_audit_events(
        audit_events=
            audit_events,

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

    return audit_events


# ============================================================
# PUBLIC ALIAS
# ============================================================


def generate_audit(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Alias for generate_all.py orchestration.
    """

    return generate_audit_events(
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


# ============================================================
# PAYLOAD LEAKAGE SCAN
# ============================================================


def _scan_payload_keys(
    value: Any,
    path: str = "",
) -> list[str]:
    """
    Recursively detect forbidden hidden-truth payload keys.
    """

    violations: list[
        str
    ] = []

    if isinstance(
        value,
        Mapping,
    ):

        for key, item in (
            value.items()
        ):

            key_text = str(
                key
            ).lower()

            current_path = (
                f"{path}.{key}"
                if path
                else str(
                    key
                )
            )

            for fragment in (
                FORBIDDEN_PAYLOAD_KEY_FRAGMENTS
            ):

                if fragment in key_text:

                    violations.append(
                        current_path
                    )

            violations.extend(
                _scan_payload_keys(
                    item,
                    current_path,
                )
            )

    elif isinstance(
        value,
        list,
    ):

        for index, item in enumerate(
            value
        ):

            violations.extend(
                _scan_payload_keys(
                    item,
                    f"{path}[{index}]",
                )
            )

    return violations


# ============================================================
# VALIDATION
# ============================================================


def validate_audit_events(
    audit_events: pd.DataFrame,
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate complete audit ledger.
    """

    _validate_inputs(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        human_reviews=
            human_reviews,
    )

    target_count = (
        _get_audit_target_count(
            generation
        )
    )

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    required_columns = {
        "audit_event_id",

        "recommendation_id",
        "decision_id",

        "domain",
        "use_case",

        "target_entity_type",
        "target_entity_id",

        "event_sequence",

        "event_type",
        "event_at",

        "actor_type",
        "actor_id",

        "source_record_type",
        "source_record_id",

        "event_status",

        "event_summary",
        "details_json",

        "previous_event_hash",
        "event_hash",

        "data_origin",
        "generator_version",
    }

    missing = (
        required_columns
        -
        set(
            audit_events.columns
        )
    )

    if missing:
        raise ValueError(
            "Audit events missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    # ========================================================
    # EXACT COUNT
    # ========================================================

    if len(
        audit_events
    ) != target_count:

        raise ValueError(
            "Audit-event count does not match configured target"
        )

    # ========================================================
    # PRIMARY KEY
    # ========================================================

    if (
        audit_events[
            "audit_event_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "audit_event_id cannot be null"
        )

    if (
        audit_events[
            "audit_event_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate audit_event_id values found"
        )

    # ========================================================
    # EVENT ENUMS
    # ========================================================

    invalid_event_types = (
        set(
            audit_events[
                "event_type"
            ]
            .astype(
                str
            )
        )
        -
        VALID_EVENT_TYPES
    )

    if invalid_event_types:
        raise ValueError(
            "Invalid audit event types: "
            +
            ", ".join(
                sorted(
                    invalid_event_types
                )
            )
        )

    invalid_actor_types = (
        set(
            audit_events[
                "actor_type"
            ]
            .astype(
                str
            )
        )
        -
        VALID_ACTOR_TYPES
    )

    if invalid_actor_types:
        raise ValueError(
            "Invalid audit actor types found"
        )

    invalid_statuses = (
        set(
            audit_events[
                "event_status"
            ]
            .astype(
                str
            )
        )
        -
        VALID_EVENT_STATUSES
    )

    if invalid_statuses:
        raise ValueError(
            "Invalid audit event status found"
        )

    # ========================================================
    # FK SETS
    # ========================================================

    recommendation_ids = set(
        recommendations[
            "recommendation_id"
        ]
        .astype(
            str
        )
    )

    decision_ids = set(
        trust_decisions[
            "decision_id"
        ]
        .astype(
            str
        )
    )

    check_ids = set(
        compliance_checks[
            "compliance_check_id"
        ]
        .astype(
            str
        )
    )

    review_ids = set(
        human_reviews[
            "review_id"
        ]
        .astype(
            str
        )
    )

    invalid_recommendation_ids = (
        set(
            audit_events[
                "recommendation_id"
            ]
            .astype(
                str
            )
        )
        -
        recommendation_ids
    )

    if invalid_recommendation_ids:
        raise ValueError(
            "Audit events reference invalid recommendations"
        )

    invalid_decision_ids = (
        set(
            audit_events[
                "decision_id"
            ]
            .astype(
                str
            )
        )
        -
        decision_ids
    )

    if invalid_decision_ids:
        raise ValueError(
            "Audit events reference invalid trust decisions"
        )

    # ========================================================
    # MANDATORY RECOMMENDATION EVENT
    # ========================================================

    recommendation_event_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_RECOMMENDATION_RECORDED
        ]
    )

    if len(
        recommendation_event_rows
    ) != len(
        recommendations
    ):
        raise ValueError(
            "Expected exactly one recommendation audit event "
            "per recommendation"
        )

    if (
        recommendation_event_rows[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Recommendation has duplicate "
            "RECOMMENDATION_RECORDED events"
        )

    if (
        set(
            recommendation_event_rows[
                "recommendation_id"
            ]
            .astype(
                str
            )
        )
        !=
        recommendation_ids
    ):
        raise ValueError(
            "Not every recommendation appears in audit ledger"
        )

    # ========================================================
    # MANDATORY COMPLIANCE SUMMARY
    # ========================================================

    compliance_summary_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_COMPLIANCE_EVALUATION_COMPLETED
        ]
    )

    if len(
        compliance_summary_rows
    ) != len(
        trust_decisions
    ):
        raise ValueError(
            "Expected exactly one compliance summary "
            "per trust decision"
        )

    if (
        compliance_summary_rows[
            "decision_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Decision has duplicate compliance summary events"
        )

    # ========================================================
    # MANDATORY TRUST DECISION EVENT
    # ========================================================

    trust_event_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_TRUST_DECISION_RECORDED
        ]
    )

    if len(
        trust_event_rows
    ) != len(
        trust_decisions
    ):
        raise ValueError(
            "Every trust decision must appear once "
            "in audit ledger"
        )

    if (
        trust_event_rows[
            "decision_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate trust-decision audit event"
        )

    if (
        set(
            trust_event_rows[
                "decision_id"
            ]
            .astype(
                str
            )
        )
        !=
        decision_ids
    ):
        raise ValueError(
            "Not every trust decision appears in audit ledger"
        )

    # ========================================================
    # HUMAN REVIEW COVERAGE
    # ========================================================

    requested_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_HUMAN_REVIEW_REQUESTED
        ]
    )

    completed_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_HUMAN_REVIEW_COMPLETED
        ]
    )

    if len(
        requested_rows
    ) != len(
        human_reviews
    ):
        raise ValueError(
            "Every human review must have exactly one "
            "requested audit event"
        )

    if len(
        completed_rows
    ) != len(
        human_reviews
    ):
        raise ValueError(
            "Every human review must have exactly one "
            "completed audit event"
        )

    if not human_reviews.empty:

        if (
            set(
                requested_rows[
                    "source_record_id"
                ]
                .astype(
                    str
                )
            )
            !=
            review_ids
        ):
            raise ValueError(
                "Human-review request event coverage mismatch"
            )

        if (
            set(
                completed_rows[
                    "source_record_id"
                ]
                .astype(
                    str
                )
            )
            !=
            review_ids
        ):
            raise ValueError(
                "Human-review completion event coverage mismatch"
            )

    # ========================================================
    # COMPLIANCE DETAIL COVERAGE
    # ========================================================

    mandatory_count = (
        len(
            recommendations
        )
        +
        len(
            trust_decisions
        )
        +
        len(
            trust_decisions
        )
        +
        (
            2
            *
            len(
                human_reviews
            )
        )
    )

    expected_detail_count = (
        target_count
        -
        mandatory_count
    )

    detail_rows = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            EVENT_COMPLIANCE_CHECK_RECORDED
        ]
    )

    if len(
        detail_rows
    ) != expected_detail_count:
        raise ValueError(
            "Detailed compliance audit-event count mismatch. "
            f"Expected={expected_detail_count}, "
            f"actual={len(detail_rows)}"
        )

    if (
        detail_rows[
            "source_record_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Same compliance check audited more than once"
        )

    invalid_detailed_check_ids = (
        set(
            detail_rows[
                "source_record_id"
            ]
            .astype(
                str
            )
        )
        -
        check_ids
    )

    if invalid_detailed_check_ids:
        raise ValueError(
            "Detailed audit event references invalid "
            "compliance check"
        )

    # Every non-PASS check must be retained in detail.
    non_pass_check_ids = set(
        compliance_checks.loc[
            compliance_checks[
                "result"
            ]
            .astype(
                str
            )
            !=
            RESULT_PASS,
            "compliance_check_id",
        ]
        .astype(
            str
        )
    )

    audited_check_ids = set(
        detail_rows[
            "source_record_id"
        ]
        .astype(
            str
        )
    )

    missing_exception_checks = (
        non_pass_check_ids
        -
        audited_check_ids
    )

    if missing_exception_checks:
        raise ValueError(
            "Some non-PASS compliance checks are absent "
            "from detailed audit trail"
        )

    # Current design also requires one detailed check per decision.
    detailed_decisions = set(
        detail_rows[
            "decision_id"
        ]
        .astype(
            str
        )
    )

    if detailed_decisions != decision_ids:
        raise ValueError(
            "Every trust decision must have at least "
            "one detailed compliance audit event"
        )

    # ========================================================
    # SOURCE TIMESTAMP EXACTNESS
    # ========================================================

    recommendation_time_lookup = (
        recommendations
        .set_index(
            "recommendation_id"
        )[
            "generated_at"
        ]
    )

    decision_time_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )[
            "decided_at"
        ]
    )

    check_time_lookup = (
        compliance_checks
        .set_index(
            "compliance_check_id"
        )[
            "checked_at"
        ]
    )

    review_requested_lookup = (
        human_reviews
        .set_index(
            "review_id"
        )[
            "requested_at"
        ]
        if not human_reviews.empty
        else pd.Series(
            dtype=object
        )
    )

    review_completed_lookup = (
        human_reviews
        .set_index(
            "review_id"
        )[
            "completed_at"
        ]
        if not human_reviews.empty
        else pd.Series(
            dtype=object
        )
    )

    latest_check_lookup = (
        compliance_checks
        .assign(
            _checked_at_utc=
                pd.to_datetime(
                    compliance_checks[
                        "checked_at"
                    ],
                    errors="raise",
                    utc=True,
                )
        )
        .groupby(
            "decision_id"
        )[
            "_checked_at_utc"
        ]
        .max()
    )

    for event in audit_events.itertuples(
        index=False
    ):

        event_time = pd.Timestamp(
            event.event_at
        )

        if event_time.tzinfo is None:
            raise ValueError(
                f"{event.audit_event_id}: "
                "event_at must be timezone-aware"
            )

        event_time_utc = (
            event_time
            .tz_convert(
                "UTC"
            )
        )

        if (
            event.event_type
            ==
            EVENT_RECOMMENDATION_RECORDED
        ):

            source_time = pd.Timestamp(
                recommendation_time_lookup.loc[
                    str(
                        event.recommendation_id
                    )
                ]
            ).tz_convert(
                "UTC"
            )

        elif (
            event.event_type
            ==
            EVENT_COMPLIANCE_CHECK_RECORDED
        ):

            source_time = pd.Timestamp(
                check_time_lookup.loc[
                    str(
                        event.source_record_id
                    )
                ]
            ).tz_convert(
                "UTC"
            )

        elif (
            event.event_type
            ==
            EVENT_COMPLIANCE_EVALUATION_COMPLETED
        ):

            source_time = pd.Timestamp(
                latest_check_lookup.loc[
                    str(
                        event.decision_id
                    )
                ]
            )

        elif (
            event.event_type
            ==
            EVENT_HUMAN_REVIEW_REQUESTED
        ):

            source_time = pd.Timestamp(
                review_requested_lookup.loc[
                    str(
                        event.source_record_id
                    )
                ]
            ).tz_convert(
                "UTC"
            )

        elif (
            event.event_type
            ==
            EVENT_HUMAN_REVIEW_COMPLETED
        ):

            source_time = pd.Timestamp(
                review_completed_lookup.loc[
                    str(
                        event.source_record_id
                    )
                ]
            ).tz_convert(
                "UTC"
            )

        elif (
            event.event_type
            ==
            EVENT_TRUST_DECISION_RECORDED
        ):

            source_time = pd.Timestamp(
                decision_time_lookup.loc[
                    str(
                        event.decision_id
                    )
                ]
            ).tz_convert(
                "UTC"
            )

        else:

            raise ValueError(
                "Unexpected event type during "
                "timestamp validation"
            )

        if event_time_utc != source_time:

            raise ValueError(
                f"{event.audit_event_id}: audit timestamp "
                "does not match source event timestamp"
            )

    # ========================================================
    # TEMPORAL WINDOW
    # ========================================================

    event_times = pd.to_datetime(
        audit_events[
            "event_at"
        ],
        errors="raise",
        utc=True,
    )

    start_utc = (
        generation_start
        .tz_convert(
            "UTC"
        )
    )

    end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    if (
        event_times
        <
        start_utc
    ).any():
        raise ValueError(
            "Audit event occurs before generation window"
        )

    if (
        event_times
        >=
        end_utc
    ).any():
        raise ValueError(
            "Audit event occurs outside generation window"
        )

    # ========================================================
    # PER-RECOMMENDATION ORDERING
    # ========================================================

    for (
        recommendation_id,
        group,
    ) in audit_events.groupby(
        "recommendation_id",
        sort=True,
    ):

        ordered = (
            group
            .sort_values(
                "event_sequence"
            )
            .reset_index(
                drop=True
            )
        )

        expected_sequences = list(
            range(
                1,
                len(
                    ordered
                )
                + 1,
            )
        )

        actual_sequences = (
            ordered[
                "event_sequence"
            ]
            .astype(
                int
            )
            .tolist()
        )

        if (
            actual_sequences
            !=
            expected_sequences
        ):
            raise ValueError(
                f"{recommendation_id}: "
                "event_sequence is not contiguous"
            )

        ordered_times = pd.to_datetime(
            ordered[
                "event_at"
            ],
            errors="raise",
            utc=True,
        )

        if not (
            ordered_times
            .is_monotonic_increasing
        ):
            raise ValueError(
                f"{recommendation_id}: "
                "audit timeline is not chronological"
            )

        if (
            ordered.iloc[
                0
            ][
                "event_type"
            ]
            !=
            EVENT_RECOMMENDATION_RECORDED
        ):
            raise ValueError(
                f"{recommendation_id}: "
                "recommendation event must start audit chain"
            )

        if (
            ordered.iloc[
                -1
            ][
                "event_type"
            ]
            !=
            EVENT_TRUST_DECISION_RECORDED
        ):
            raise ValueError(
                f"{recommendation_id}: "
                "trust decision must close audit chain"
            )

        event_types = (
            ordered[
                "event_type"
            ]
            .tolist()
        )

        if (
            EVENT_HUMAN_REVIEW_COMPLETED
            in event_types
        ):

            request_position = (
                event_types.index(
                    EVENT_HUMAN_REVIEW_REQUESTED
                )
            )

            complete_position = (
                event_types.index(
                    EVENT_HUMAN_REVIEW_COMPLETED
                )
            )

            decision_position = (
                event_types.index(
                    EVENT_TRUST_DECISION_RECORDED
                )
            )

            if not (
                request_position
                <
                complete_position
                <
                decision_position
            ):
                raise ValueError(
                    f"{recommendation_id}: "
                    "human-review audit ordering invalid"
                )

    # ========================================================
    # HASH CHAIN
    # ========================================================

    for (
        recommendation_id,
        group,
    ) in audit_events.groupby(
        "recommendation_id",
        sort=True,
    ):

        ordered = (
            group
            .sort_values(
                "event_sequence"
            )
        )

        expected_previous_hash = (
            "GENESIS"
        )

        for row in ordered.to_dict(
            orient="records"
        ):

            if (
                str(
                    row[
                        "previous_event_hash"
                    ]
                )
                !=
                expected_previous_hash
            ):

                raise ValueError(
                    f"{recommendation_id}: broken "
                    "previous_event_hash chain"
                )

            expected_hash = (
                _calculate_event_hash(
                    row=
                        row,

                    previous_event_hash=
                        expected_previous_hash,
                )
            )

            if (
                str(
                    row[
                        "event_hash"
                    ]
                )
                !=
                expected_hash
            ):

                raise ValueError(
                    f"{recommendation_id}: "
                    "audit event hash mismatch"
                )

            expected_previous_hash = (
                expected_hash
            )

    if (
        audit_events[
            "event_hash"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate event_hash values found"
        )

    # ========================================================
    # JSON + HIDDEN TRUTH
    # ========================================================

    for event in audit_events.itertuples(
        index=False
    ):

        details = _parse_json_object(
            value=
                event.details_json,

            field_name=
                "details_json",

            record_id=
                str(
                    event.audit_event_id
                ),
        )

        violations = _scan_payload_keys(
            details,
            "details_json",
        )

        if violations:

            raise ValueError(
                f"{event.audit_event_id}: hidden truth "
                "leaked into audit payload: "
                +
                ", ".join(
                    violations
                )
            )

    leakage_columns = [
        column
        for column
        in audit_events.columns
        if any(
            fragment
            in column.lower()
            for fragment
            in FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS
        )
    ]

    if leakage_columns:

        raise ValueError(
            "Hidden truth/runtime leakage found "
            "in audit columns: "
            +
            ", ".join(
                leakage_columns
            )
        )

    # ========================================================
    # PROVENANCE
    # ========================================================

    expected_origin = str(
        generation.get(
            "provenance",
            {},
        ).get(
            "data_origin",
            "SYNTHETIC",
        )
    )

    expected_version = str(
        generation.get(
            "generator_version",
            "1.0.0",
        )
    )

    if not (
        audit_events[
            "data_origin"
        ]
        ==
        expected_origin
    ).all():

        raise ValueError(
            "Audit data_origin mismatch"
        )

    if not (
        audit_events[
            "generator_version"
        ]
        ==
        expected_version
    ).all():

        raise ValueError(
            "Audit generator_version mismatch"
        )


# ============================================================
# LOCAL VALIDATION
# ============================================================


if __name__ == "__main__":

    from data.generators.governance.recommendations import (
        _build_local_validation_fixture,
        generate_recommendations,
    )

    from data.generators.governance.trust import (
        generate_trust,
    )

    generation_config = (
        load_generation_config()
    )

    audit_target = (
        _get_audit_target_count(
            generation_config
        )
    )

    # ========================================================
    # RECOMMENDATIONS
    # ========================================================

    (
        allocations_df,
        cross_sell_events_df,
        collection_cases_df,
        shipments_df,
        credit_listings_df,
    ) = _build_local_validation_fixture(
        generation_config
    )

    recommendations_df = (
        generate_recommendations(
            allocations=
                allocations_df,

            cross_sell_events=
                cross_sell_events_df,

            collection_cases=
                collection_cases_df,

            shipments=
                shipments_df,

            credit_listings=
                credit_listings_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # TRUST
    # ========================================================

    (
        compliance_checks_df,
        trust_decisions_df,
        human_reviews_df,
    ) = generate_trust(
        recommendations=
            recommendations_df,

        generation=
            generation_config,
    )

    print(
        "\n=== AUDIT GOVERNANCE CONFIG ===\n"
    )

    print(
        "Recommendations:",
        len(
            recommendations_df
        ),
    )

    print(
        "Compliance checks:",
        len(
            compliance_checks_df
        ),
    )

    print(
        "Trust decisions:",
        len(
            trust_decisions_df
        ),
    )

    print(
        "Human reviews:",
        len(
            human_reviews_df
        ),
    )

    print(
        "Configured audit events:",
        audit_target,
    )

    # ========================================================
    # GENERATE
    # ========================================================

    audit_events_df = (
        generate_audit_events(
            recommendations=
                recommendations_df,

            compliance_checks=
                compliance_checks_df,

            trust_decisions=
                trust_decisions_df,

            human_reviews=
                human_reviews_df,

            generation=
                generation_config,
        )
    )

    # ========================================================
    # DETERMINISM
    # ========================================================

    audit_events_repeat_df = (
        generate_audit_events(
            recommendations=
                recommendations_df,

            compliance_checks=
                compliance_checks_df,

            trust_decisions=
                trust_decisions_df,

            human_reviews=
                human_reviews_df,

            generation=
                generation_config,
        )
    )

    pd.testing.assert_frame_equal(
        audit_events_df,
        audit_events_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    # ========================================================
    # EVENT SAMPLE
    # ========================================================

    print(
        "\n=== AUDIT EVENT SAMPLE ===\n"
    )

    sample_columns = [
        "audit_event_id",
        "recommendation_id",
        "decision_id",
        "domain",
        "event_sequence",
        "event_type",
        "actor_type",
        "actor_id",
        "source_record_type",
        "source_record_id",
        "event_at",
    ]

    print(
        audit_events_df[
            sample_columns
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # EVENT TYPE MIX
    # ========================================================

    print(
        "\n=== AUDIT EVENT TYPE MIX ===\n"
    )

    event_mix = (
        audit_events_df
        .groupby(
            "event_type",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "events"
            }
        )
        .sort_values(
            [
                "events",
                "event_type",
            ],
            ascending=[
                False,
                True,
            ],
        )
    )

    print(
        event_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # DOMAIN MIX
    # ========================================================

    print(
        "\n=== AUDIT EVENTS BY DOMAIN ===\n"
    )

    domain_mix = (
        audit_events_df
        .groupby(
            "domain",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "events"
            }
        )
        .sort_values(
            "domain"
        )
    )

    print(
        domain_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # ACTOR MIX
    # ========================================================

    print(
        "\n=== AUDIT ACTOR MIX ===\n"
    )

    actor_mix = (
        audit_events_df
        .groupby(
            [
                "actor_type",
                "actor_id",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "events"
            }
        )
        .sort_values(
            [
                "actor_type",
                "events",
                "actor_id",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
    )

    print(
        actor_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # DETAILED CHECK MIX
    # ========================================================

    detailed_events = (
        audit_events_df.loc[
            audit_events_df[
                "event_type"
            ]
            ==
            EVENT_COMPLIANCE_CHECK_RECORDED
        ]
    )

    detailed_check_ids = set(
        detailed_events[
            "source_record_id"
        ]
        .astype(
            str
        )
    )

    selected_check_rows = (
        compliance_checks_df.loc[
            compliance_checks_df[
                "compliance_check_id"
            ]
            .astype(
                str
            )
            .isin(
                detailed_check_ids
            )
        ]
    )

    print(
        "\n=== DETAILED COMPLIANCE AUDIT MIX ===\n"
    )

    detailed_mix = (
        selected_check_rows
        .groupby(
            [
                "rule_code",
                "result",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "events"
            }
        )
        .sort_values(
            [
                "rule_code",
                "result",
            ]
        )
    )

    print(
        detailed_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # PER-RECOMMENDATION EVENT DEPTH
    # ========================================================

    print(
        "\n=== AUDIT EVENTS PER RECOMMENDATION ===\n"
    )

    events_per_recommendation = (
        audit_events_df
        .groupby(
            "recommendation_id"
        )
        .size()
    )

    print(
        events_per_recommendation
        .describe()
        .round(
            4
        )
        .to_string()
    )

    # ========================================================
    # EXCEPTION COVERAGE
    # ========================================================

    non_pass_checks = (
        compliance_checks_df.loc[
            compliance_checks_df[
                "result"
            ]
            !=
            RESULT_PASS
        ]
    )

    non_pass_check_ids = set(
        non_pass_checks[
            "compliance_check_id"
        ]
        .astype(
            str
        )
    )

    missing_non_pass_audit = (
        non_pass_check_ids
        -
        detailed_check_ids
    )

    # ========================================================
    # HASH CHECK
    # ========================================================

    first_event_per_recommendation = (
        audit_events_df
        .sort_values(
            [
                "recommendation_id",
                "event_sequence",
            ]
        )
        .groupby(
            "recommendation_id",
            as_index=False,
        )
        .first()
    )

    genesis_rows = int(
        (
            first_event_per_recommendation[
                "previous_event_hash"
            ]
            ==
            "GENESIS"
        )
        .sum()
    )

    unique_hashes = (
        audit_events_df[
            "event_hash"
        ]
        .nunique()
    )

    # ========================================================
    # LEAKAGE
    # ========================================================

    leakage_columns = [
        column
        for column
        in audit_events_df.columns
        if any(
            fragment
            in column.lower()
            for fragment
            in FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS
        )
    ]

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== AUDIT GOVERNANCE VALIDATION ===\n"
    )

    print(
        "Audit event rows:",
        len(
            audit_events_df
        ),
    )

    print(
        "Unique audit event IDs:",
        audit_events_df[
            "audit_event_id"
        ]
        .nunique(),
    )

    print(
        "Recommendations represented:",
        audit_events_df[
            "recommendation_id"
        ]
        .nunique(),
    )

    print(
        "Trust decisions represented:",
        audit_events_df[
            "decision_id"
        ]
        .nunique(),
    )

    print(
        "Recommendation recorded events:",
        int(
            (
                audit_events_df[
                    "event_type"
                ]
                ==
                EVENT_RECOMMENDATION_RECORDED
            )
            .sum()
        ),
    )

    print(
        "Compliance summary events:",
        int(
            (
                audit_events_df[
                    "event_type"
                ]
                ==
                EVENT_COMPLIANCE_EVALUATION_COMPLETED
            )
            .sum()
        ),
    )

    print(
        "Detailed compliance events:",
        len(
            detailed_events
        ),
    )

    print(
        "Human review requested events:",
        int(
            (
                audit_events_df[
                    "event_type"
                ]
                ==
                EVENT_HUMAN_REVIEW_REQUESTED
            )
            .sum()
        ),
    )

    print(
        "Human review completed events:",
        int(
            (
                audit_events_df[
                    "event_type"
                ]
                ==
                EVENT_HUMAN_REVIEW_COMPLETED
            )
            .sum()
        ),
    )

    print(
        "Trust decision events:",
        int(
            (
                audit_events_df[
                    "event_type"
                ]
                ==
                EVENT_TRUST_DECISION_RECORDED
            )
            .sum()
        ),
    )

    print(
        "Non-PASS compliance checks:",
        len(
            non_pass_checks
        ),
    )

    print(
        "Non-PASS checks missing detailed audit:",
        len(
            missing_non_pass_audit
        ),
    )

    print(
        "Decisions with detailed compliance evidence:",
        detailed_events[
            "decision_id"
        ]
        .nunique(),
    )

    print(
        "Genesis chains:",
        genesis_rows,
    )

    print(
        "Unique event hashes:",
        unique_hashes,
    )

    print(
        "Duplicate audit event IDs:",
        int(
            audit_events_df[
                "audit_event_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate event hashes:",
        int(
            audit_events_df[
                "event_hash"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        leakage_columns,
    )

    print(
        "Deterministic rerun:",
        "PASS",
    )

    print(
        "\nGenerated "
        f"{len(audit_events_df)} "
        "immutable synthetic governance "
        "audit events successfully."
    )