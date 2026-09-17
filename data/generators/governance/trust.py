"""
Synthetic Trust / Compliance / Human Review generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate governance records downstream of evidence-backed
recommendations:

    recommendations
        ↓
    compliance_checks
        ↓
    human review routing
        ↓
    human_reviews
        ↓
    trust_decisions

This module creates:

    1. compliance_checks
    2. trust_decisions
    3. human_reviews

It does NOT create:

    audit_events
    action executions
    action outcomes
    agent workflow events
    hidden ground truth


============================================================
CONFIGURATION
============================================================

Current generation.yaml:

    governance:
        recommendation_target_count: 2000
        compliance_checks_per_decision: 5
        human_review_rate: 0.15
        audit_events_target_count: 10000

With 2,000 recommendations:

    trust decisions:
        2,000

    compliance checks:
        2,000 × 5
        = 10,000

    human reviews:
        round(2,000 × 0.15)
        = 300


============================================================
COMPLIANCE RULE SET
============================================================

Exactly five stable policy checks are evaluated for every
recommendation:

    LINEAGE_INTEGRITY
    EVIDENCE_SUFFICIENCY
    FAIRNESS_INPUT_SCOPE
    BUSINESS_POLICY_ALIGNMENT
    HUMAN_CONTROL_GATE

These are synthetic PoC governance policies.

They are NOT assertions of real Mahindra legal/regulatory
compliance.


============================================================
HUMAN REVIEW
============================================================

Human review is not assigned independently at random.

Recommendations are ranked using:

    recommendation risk
    confidence / uncertainty
    business-domain sensitivity
    recommendation-type sensitivity

The configured review rate determines the exact number routed
to human review.

Domain-proportional quotas preserve broad development/test
coverage without claiming a real Mahindra review distribution.


============================================================
TEMPORAL ORDER
============================================================

recommendation.generated_at
    <
compliance checks
    <
human-review request, when applicable
    <
human-review completion
    <=
trust decision

The frozen recommendation generator currently places its
governance snapshot very near the end of the generation window.

Therefore this generator dynamically compresses event offsets
into the available interval while preserving chronological
ordering.


============================================================
OUTPUT
============================================================

Public functions:

    generate_trust(...)
        -> (
            compliance_checks,
            trust_decisions,
            human_reviews,
        )

    generate_trust_records(...)
        -> alias of generate_trust(...)

Individual generators return DataFrames only.

No CSV writes occur here.
"""

from __future__ import annotations

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
# DECISION ENUMS
# ============================================================

DECISION_APPROVED = "APPROVED"
DECISION_REJECTED = "REJECTED"
DECISION_MODIFIED = "MODIFIED"
DECISION_ESCALATED = "ESCALATED"


VALID_DECISIONS = {
    DECISION_APPROVED,
    DECISION_REJECTED,
    DECISION_MODIFIED,
    DECISION_ESCALATED,
}


MODE_AUTOMATED_POLICY = (
    "AUTOMATED_POLICY"
)

MODE_HUMAN_REVIEW = (
    "HUMAN_REVIEW"
)


VALID_DECISION_MODES = {
    MODE_AUTOMATED_POLICY,
    MODE_HUMAN_REVIEW,
}


# ============================================================
# COMPLIANCE RESULTS
# ============================================================

CHECK_PASS = "PASS"
CHECK_WARN = "WARN"
CHECK_FAIL = "FAIL"

CHECK_REVIEW_REQUIRED = (
    "REVIEW_REQUIRED"
)


VALID_CHECK_RESULTS = {
    CHECK_PASS,
    CHECK_WARN,
    CHECK_FAIL,
    CHECK_REVIEW_REQUIRED,
}


SEVERITY_INFO = "INFO"
SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"


VALID_SEVERITIES = {
    SEVERITY_INFO,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    SEVERITY_HIGH,
    SEVERITY_CRITICAL,
}


# ============================================================
# COMPLIANCE RULES
# ============================================================

RULE_LINEAGE = (
    "LINEAGE_INTEGRITY"
)

RULE_EVIDENCE = (
    "EVIDENCE_SUFFICIENCY"
)

RULE_FAIRNESS = (
    "FAIRNESS_INPUT_SCOPE"
)

RULE_POLICY = (
    "BUSINESS_POLICY_ALIGNMENT"
)

RULE_HUMAN_CONTROL = (
    "HUMAN_CONTROL_GATE"
)


COMPLIANCE_RULES = (
    RULE_LINEAGE,
    RULE_EVIDENCE,
    RULE_FAIRNESS,
    RULE_POLICY,
    RULE_HUMAN_CONTROL,
)


RULE_NAMES = {
    RULE_LINEAGE:
        "Data lineage integrity",

    RULE_EVIDENCE:
        "Evidence and explainability sufficiency",

    RULE_FAIRNESS:
        "Fairness input-scope check",

    RULE_POLICY:
        "Business policy alignment",

    RULE_HUMAN_CONTROL:
        "Human-control risk gate",
}


# ============================================================
# DOMAIN REVIEW ROLES
# ============================================================

REVIEWER_ROLE_BY_DOMAIN = {
    "AUTO":
        "AUTO_OPERATIONS_REVIEWER",

    "FINANCE":
        "FINANCIAL_SERVICES_RISK_REVIEWER",

    "COLLECTIONS":
        "COLLECTIONS_GOVERNANCE_REVIEWER",

    "LOGISTICS":
        "LOGISTICS_CONTROL_TOWER_REVIEWER",

    "CIRCULARITY":
        "ESG_COMPLIANCE_REVIEWER",
}


# ============================================================
# REQUIRED RECOMMENDATION SCHEMA
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


# ============================================================
# SENSITIVE INPUT KEY SCAN
#
# This is deliberately an INPUT-SCOPE check.
#
# Absence of these keys is NOT presented as proof that a real
# model is globally fair.
# ============================================================

SENSITIVE_KEY_FRAGMENTS = {
    "race",
    "ethnicity",
    "religion",
    "caste",
    "gender",
    "sex",
    "sexual_orientation",
    "disability",
    "political_affiliation",
    "trade_union",
    "biometric",
}


# ============================================================
# HIDDEN TRUTH / RUNTIME LEAKAGE
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
    Safe scalar missing-value test.
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
        result = float(
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
        result
    ):
        return float(
            default
        )

    return float(
        result
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
    Normalize common boolean-like values.
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


def _clip01(
    value: float,
) -> float:
    """
    Clip to [0,1].
    """

    return float(
        np.clip(
            float(
                value
            ),
            0.0,
            1.0,
        )
    )


# ============================================================
# JSON HELPERS
# ============================================================


def _parse_json_object(
    value: Any,
    field_name: str,
    recommendation_id: str,
) -> dict[str, Any]:
    """
    Parse a recommendation JSON-object field.
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
            f"{recommendation_id}: invalid {field_name}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"{recommendation_id}: "
            f"{field_name} must contain a JSON object"
        )

    return payload


def _json_ready(
    value: Any,
) -> Any:
    """
    Convert numpy/pandas values to JSON-safe values.
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
    Deterministic JSON serialization.
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


# ============================================================
# CONFIGURATION
# ============================================================


def _get_generation_window(
    generation: Mapping[str, Any],
) -> tuple[
    pd.Timestamp,
    pd.Timestamp,
    str,
]:
    """
    Return timezone-aware synthetic generation window.
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


def _get_governance_config(
    generation: Mapping[str, Any],
) -> tuple[
    int,
    float,
]:
    """
    Return:

        compliance_checks_per_decision
        human_review_rate
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

    if (
        "compliance_checks_per_decision"
        not in governance
    ):
        raise KeyError(
            "Missing governance."
            "compliance_checks_per_decision"
        )

    if (
        "human_review_rate"
        not in governance
    ):
        raise KeyError(
            "Missing governance.human_review_rate"
        )

    checks_per_decision = int(
        governance[
            "compliance_checks_per_decision"
        ]
    )

    human_review_rate = float(
        governance[
            "human_review_rate"
        ]
    )

    if checks_per_decision <= 0:
        raise ValueError(
            "compliance_checks_per_decision must be > 0"
        )

    if checks_per_decision != len(
        COMPLIANCE_RULES
    ):
        raise ValueError(
            "Current trust policy defines exactly "
            f"{len(COMPLIANCE_RULES)} rules, but "
            "generation.yaml requests "
            f"{checks_per_decision} checks per decision"
        )

    if not (
        0.0
        <= human_review_rate
        <= 1.0
    ):
        raise ValueError(
            "human_review_rate must be within [0,1]"
        )

    return (
        checks_per_decision,
        human_review_rate,
    )


# ============================================================
# RECOMMENDATION VALIDATION
# ============================================================


def _validate_recommendation_input(
    recommendations: pd.DataFrame,
) -> None:
    """
    Validate recommendation records consumed by trust.py.
    """

    if recommendations.empty:
        raise ValueError(
            "Recommendations DataFrame cannot be empty"
        )

    missing = (
        RECOMMENDATION_REQUIRED_COLUMNS
        -
        set(
            recommendations.columns
        )
    )

    if missing:
        raise ValueError(
            "Recommendations missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    if (
        recommendations[
            "recommendation_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "recommendation_id cannot be null"
        )

    if (
        recommendations[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate recommendation IDs found"
        )

    if not (
        recommendations[
            "status"
        ]
        ==
        "PROPOSED"
    ).all():
        raise ValueError(
            "trust.py expects recommendations "
            "in PROPOSED state"
        )

    confidence = pd.to_numeric(
        recommendations[
            "confidence"
        ],
        errors="raise",
    )

    if (
        (
            confidence < 0.0
        )
        |
        (
            confidence > 1.0
        )
    ).any():
        raise ValueError(
            "Recommendation confidence outside [0,1]"
        )

    valid_risks = {
        "LOW",
        "MEDIUM",
        "HIGH",
    }

    invalid_risks = (
        set(
            recommendations[
                "risk_level"
            ]
            .astype(
                str
            )
        )
        -
        valid_risks
    )

    if invalid_risks:
        raise ValueError(
            "Unsupported recommendation risk levels: "
            +
            ", ".join(
                sorted(
                    invalid_risks
                )
            )
        )

    # Validate JSON now, before governance records are generated.

    for row in recommendations.itertuples(
        index=False
    ):
        _parse_json_object(
            value=row.evidence_json,
            field_name="evidence_json",
            recommendation_id=str(
                row.recommendation_id
            ),
        )

        _parse_json_object(
            value=row.expected_impact,
            field_name="expected_impact",
            recommendation_id=str(
                row.recommendation_id
            ),
        )


# ============================================================
# HUMAN REVIEW ROUTING SCORE
# ============================================================


def _recommendation_type_sensitivity(
    recommendation_type: str,
) -> float:
    """
    Synthetic governance sensitivity for recommendation classes.

    This is not ground truth and is not a model prediction.
    """

    text = str(
        recommendation_type
    ).upper()

    if "RESTRUCTURING" in text:
        return 1.00

    if "RELATIONSHIP_MANAGER" in text:
        return 0.90

    if "CREDIT_REPRICE" in text:
        return 0.85

    if "DMRV_EVIDENCE" in text:
        return 0.80

    if "INVENTORY_REBALANCE" in text:
        return 0.75

    if "SLA_MITIGATION" in text:
        return 0.70

    if "SUPPRESS_REPEAT_OFFER" in text:
        return 0.65

    if "CAPACITY_REVIEW" in text:
        return 0.60

    return 0.40


def _domain_sensitivity(
    domain: str,
) -> float:
    """
    Synthetic governance sensitivity by domain.
    """

    return {
        "COLLECTIONS":
            1.00,

        "FINANCE":
            0.90,

        "CIRCULARITY":
            0.75,

        "AUTO":
            0.65,

        "LOGISTICS":
            0.60,
    }.get(
        str(
            domain
        ).upper(),
        0.50,
    )


def _review_priority_score(
    recommendation: Mapping[str, Any],
) -> float:
    """
    Compute transparent human-review routing priority.

    Higher risk, greater uncertainty and more sensitive actions
    rank higher.
    """

    risk_level = str(
        recommendation[
            "risk_level"
        ]
    ).upper()

    risk_component = {
        "LOW":
            0.15,

        "MEDIUM":
            0.60,

        "HIGH":
            1.00,
    }[
        risk_level
    ]

    confidence = _clip01(
        _safe_float(
            recommendation[
                "confidence"
            ]
        )
    )

    uncertainty_component = (
        1.0
        -
        confidence
    )

    domain_component = (
        _domain_sensitivity(
            str(
                recommendation[
                    "domain"
                ]
            )
        )
    )

    type_component = (
        _recommendation_type_sensitivity(
            str(
                recommendation[
                    "recommendation_type"
                ]
            )
        )
    )

    score = (
        0.55
        * risk_component
        +
        0.20
        * uncertainty_component
        +
        0.15
        * domain_component
        +
        0.10
        * type_component
    )

    return _clip01(
        score
    )


# ============================================================
# REVIEW QUOTA
# ============================================================


def _allocate_review_quotas(
    recommendations: pd.DataFrame,
    human_review_rate: float,
) -> dict[str, int]:
    """
    Allocate configured review count proportionally by domain.

    Largest-remainder allocation preserves exact global count.
    """

    total_reviews = int(
        round(
            len(
                recommendations
            )
            *
            human_review_rate
        )
    )

    domain_counts = (
        recommendations[
            "domain"
        ]
        .astype(str)
        .value_counts()
        .sort_index()
    )

    raw_quotas = (
        domain_counts
        *
        human_review_rate
    )

    quotas = {
        str(domain):
            int(
                np.floor(
                    raw_quota
                )
            )

        for domain,
        raw_quota
        in raw_quotas.items()
    }

    allocated = sum(
        quotas.values()
    )

    remaining = (
        total_reviews
        -
        allocated
    )

    if remaining > 0:

        remainders = []

        for domain in (
            domain_counts.index
        ):

            domain_text = str(
                domain
            )

            fractional = (
                float(
                    raw_quotas.loc[
                        domain
                    ]
                )
                -
                quotas[
                    domain_text
                ]
            )

            remainders.append(
                (
                    domain_text,
                    fractional,
                )
            )

        remainders.sort(
            key=lambda item: (
                -item[1],
                item[0],
            )
        )

        for domain, _ in (
            remainders[
                :remaining
            ]
        ):
            quotas[
                domain
            ] += 1

    if sum(
        quotas.values()
    ) != total_reviews:
        raise ValueError(
            "Human-review quota allocation failed"
        )

    return quotas


def _select_human_reviews(
    recommendations: pd.DataFrame,
    human_review_rate: float,
) -> tuple[
    set[str],
    pd.DataFrame,
]:
    """
    Select exact configured human-review population.
    """

    work = recommendations.copy()

    work[
        "_review_priority_score"
    ] = [
        _review_priority_score(
            record
        )
        for record
        in work.to_dict(
            orient="records"
        )
    ]

    quotas = _allocate_review_quotas(
        recommendations=work,
        human_review_rate=human_review_rate,
    )

    selected_ids: set[str] = set()

    for domain, quota in (
        quotas.items()
    ):

        domain_rows = (
            work.loc[
                work[
                    "domain"
                ]
                .astype(str)
                ==
                domain
            ]
            .sort_values(
                [
                    "_review_priority_score",
                    "confidence",
                    "recommendation_id",
                ],
                ascending=[
                    False,
                    True,
                    True,
                ],
            )
        )

        if len(
            domain_rows
        ) < quota:
            raise ValueError(
                f"Not enough {domain} recommendations "
                "to satisfy human-review quota"
            )

        ids = (
            domain_rows[
                "recommendation_id"
            ]
            .astype(str)
            .head(
                quota
            )
            .tolist()
        )

        selected_ids.update(
            ids
        )

    expected = int(
        round(
            len(
                recommendations
            )
            *
            human_review_rate
        )
    )

    if len(
        selected_ids
    ) != expected:
        raise ValueError(
            "Human-review selection failed exact configured count"
        )

    return (
        selected_ids,
        work,
    )


# ============================================================
# LINEAGE CHECK
# ============================================================


def _evaluate_lineage_check(
    recommendation: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
]:
    """
    Check evidence-to-target lineage.
    """

    source_record_id = str(
        evidence.get(
            "source_record_id",
            ""
        )
    )

    target_entity_id = str(
        recommendation[
            "target_entity_id"
        ]
    )

    source_record_type = str(
        evidence.get(
            "source_record_type",
            ""
        )
    )

    if (
        source_record_id
        and
        source_record_id
        ==
        target_entity_id
        and
        source_record_type
    ):
        result = CHECK_PASS

        severity = SEVERITY_INFO

        reason = (
            "Evidence source record matches "
            "the recommendation target."
        )

    else:
        result = CHECK_FAIL

        severity = SEVERITY_CRITICAL

        reason = (
            "Recommendation evidence lineage "
            "does not match its target entity."
        )

    details = {
        "source_record_id":
            source_record_id,

        "target_entity_id":
            target_entity_id,

        "source_record_type":
            source_record_type,
    }

    return (
        result,
        severity,
        reason,
        details,
    )


# ============================================================
# EVIDENCE SUFFICIENCY CHECK
# ============================================================


def _evaluate_evidence_check(
    recommendation: Mapping[str, Any],
    evidence: Mapping[str, Any],
    expected_impact: Mapping[str, Any],
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
]:
    """
    Validate evidence richness and explainability metadata.
    """

    confidence = _clip01(
        _safe_float(
            recommendation[
                "confidence"
            ]
        )
    )

    evidence_field_count = len(
        [
            key
            for key,
            value
            in evidence.items()
            if not _is_missing(
                value
            )
        ]
    )

    impact_has_metric = bool(
        expected_impact.get(
            "metric"
        )
    )

    impact_has_direction = bool(
        expected_impact.get(
            "direction"
        )
    )

    if (
        evidence_field_count >= 4
        and
        impact_has_metric
        and
        impact_has_direction
        and
        confidence >= 0.70
    ):
        result = CHECK_PASS

        severity = SEVERITY_INFO

        reason = (
            "Recommendation contains sufficient "
            "evidence and impact lineage."
        )

    elif (
        evidence_field_count >= 3
        and
        impact_has_metric
        and
        confidence >= 0.60
    ):
        result = CHECK_WARN

        severity = SEVERITY_MEDIUM

        reason = (
            "Recommendation evidence is usable "
            "but weaker than the normal governance threshold."
        )

    else:
        result = CHECK_FAIL

        severity = SEVERITY_HIGH

        reason = (
            "Recommendation does not contain sufficient "
            "evidence or explainability metadata."
        )

    details = {
        "evidence_field_count":
            evidence_field_count,

        "confidence":
            round(
                confidence,
                6,
            ),

        "expected_impact_metric_present":
            impact_has_metric,

        "expected_impact_direction_present":
            impact_has_direction,
    }

    return (
        result,
        severity,
        reason,
        details,
    )


# ============================================================
# FAIRNESS INPUT SCOPE
# ============================================================


def _collect_nested_keys(
    value: Any,
) -> set[str]:
    """
    Recursively collect JSON keys.
    """

    keys: set[str] = set()

    if isinstance(
        value,
        Mapping,
    ):

        for key, item in (
            value.items()
        ):

            keys.add(
                str(
                    key
                ).lower()
            )

            keys.update(
                _collect_nested_keys(
                    item
                )
            )

    elif isinstance(
        value,
        list,
    ):

        for item in value:
            keys.update(
                _collect_nested_keys(
                    item
                )
            )

    return keys


def _evaluate_fairness_scope_check(
    evidence: Mapping[str, Any],
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
]:
    """
    Detect protected/sensitive attributes directly included in
    recommendation evidence.

    PASS means only:

        no configured sensitive attribute was found in this
        recommendation evidence payload.

    It does NOT prove real-world fairness.
    """

    observed_keys = (
        _collect_nested_keys(
            evidence
        )
    )

    matches: set[str] = set()

    for observed_key in (
        observed_keys
    ):

        for fragment in (
            SENSITIVE_KEY_FRAGMENTS
        ):

            if fragment in observed_key:
                matches.add(
                    observed_key
                )

    if matches:

        result = (
            CHECK_REVIEW_REQUIRED
        )

        severity = (
            SEVERITY_HIGH
        )

        reason = (
            "Sensitive/protected input fields were detected "
            "in recommendation evidence and require review."
        )

    else:

        result = (
            CHECK_PASS
        )

        severity = (
            SEVERITY_INFO
        )

        reason = (
            "No configured protected-attribute keys were "
            "found in the recommendation evidence payload."
        )

    details = {
        "sensitive_keys_detected":
            sorted(
                matches
            ),

        "scope_note":
            (
                "Input-scope check only; this does not "
                "constitute a full fairness assessment."
            ),
    }

    return (
        result,
        severity,
        reason,
        details,
    )


# ============================================================
# BUSINESS POLICY CHECK
# ============================================================


def _evaluate_business_policy_check(
    recommendation: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
]:
    """
    Validate that the recommendation type is supported by the
    operational facts embedded in its evidence.

    The rules mirror transparent recommendation semantics rather
    than using hidden generator truth.
    """

    domain = str(
        recommendation[
            "domain"
        ]
    ).upper()

    recommendation_type = str(
        recommendation[
            "recommendation_type"
        ]
    ).upper()

    aligned = True
    reason = (
        "Recommendation is aligned with its "
        "observable business evidence."
    )

    rule_basis: dict[str, Any] = {}

    # ========================================================
    # AUTO
    # ========================================================

    if domain == "AUTO":

        demand = _safe_float(
            evidence.get(
                "derived_demand_component"
            )
        )

        wait = _safe_float(
            evidence.get(
                "derived_wait_component"
            )
        )

        dealer_pressure = _safe_float(
            evidence.get(
                "derived_dealer_inventory_pressure"
            )
        )

        batch_pressure = _safe_float(
            evidence.get(
                "derived_batch_inventory_pressure"
            )
        )

        priority_score = _safe_float(
            evidence.get(
                "allocation_priority_score"
            )
        )

        if (
            recommendation_type
            ==
            "RECOMMEND_DEALER_INVENTORY_REBALANCE"
        ):
            aligned = (
                dealer_pressure >= 0.65
                and
                demand >= 0.60
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_ALLOCATION_CYCLE_REVIEW"
        ):
            aligned = (
                wait >= 0.70
                and
                priority_score >= 0.70
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_SOURCE_BATCH_CAPACITY_REVIEW"
        ):
            aligned = (
                batch_pressure >= 0.70
                and
                demand >= 0.60
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_DEALER_ALLOCATION_REBALANCE"
        ):
            aligned = True

        else:
            aligned = False

        rule_basis = {
            "derived_demand_component":
                round(
                    demand,
                    6,
                ),

            "derived_wait_component":
                round(
                    wait,
                    6,
                ),

            "derived_dealer_inventory_pressure":
                round(
                    dealer_pressure,
                    6,
                ),

            "derived_batch_inventory_pressure":
                round(
                    batch_pressure,
                    6,
                ),

            "allocation_priority_score":
                round(
                    priority_score,
                    6,
                ),
        }

    # ========================================================
    # FINANCE
    # ========================================================

    elif domain == "FINANCE":

        response = str(
            evidence.get(
                "customer_response_as_of_snapshot",
                ""
            )
        ).upper()

        if (
            recommendation_type
            ==
            "RECOMMEND_RELATIONSHIP_MANAGER_FOLLOWUP"
        ):
            aligned = (
                response
                ==
                "INTERESTED"
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_CROSS_SELL_OFFER_FOLLOWUP"
        ):
            aligned = (
                response
                ==
                "NO_RESPONSE"
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_SUPPRESS_REPEAT_OFFER"
        ):
            aligned = (
                response
                ==
                "DECLINED"
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_CROSS_SELL_REVIEW"
        ):
            aligned = True

        else:
            aligned = False

        rule_basis = {
            "customer_response_as_of_snapshot":
                response,
        }

    # ========================================================
    # COLLECTIONS
    # ========================================================

    elif domain == "COLLECTIONS":

        current_dpd = _safe_int(
            evidence.get(
                "current_dpd"
            )
        )

        current_arrears = _safe_float(
            evidence.get(
                "current_arrears_inr"
            )
        )

        case_status = str(
            evidence.get(
                "case_status_as_of_snapshot",
                ""
            )
        ).upper()

        if (
            recommendation_type
            ==
            "RECOMMEND_RESTRUCTURING_REVIEW"
        ):
            aligned = (
                case_status == "OPEN"
                and
                current_dpd >= 90
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_PRIORITY_COLLECTIONS_REVIEW"
        ):
            aligned = (
                case_status == "OPEN"
                and
                current_dpd >= 60
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_EARLY_DELINQUENCY_OUTREACH"
        ):
            aligned = (
                case_status == "OPEN"
                and
                current_dpd >= 0
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_COLLECTIONS_CASE_LEARNING_REVIEW"
        ):
            aligned = (
                case_status == "RESOLVED"
            )

        else:
            aligned = False

        rule_basis = {
            "case_status_as_of_snapshot":
                case_status,

            "current_dpd":
                current_dpd,

            "current_arrears_inr":
                round(
                    current_arrears,
                    2,
                ),
        }

    # ========================================================
    # LOGISTICS
    # ========================================================

    elif domain == "LOGISTICS":

        sla_breach = _to_bool(
            evidence.get(
                "sla_breach"
            )
        )

        disruption_count = _safe_int(
            evidence.get(
                "disruption_count"
            )
        )

        priority = str(
            evidence.get(
                "priority",
                ""
            )
        ).upper()

        delay_minutes = _safe_float(
            evidence.get(
                "delay_minutes"
            )
        )

        if (
            recommendation_type
            ==
            "RECOMMEND_ROUTE_SLA_MITIGATION"
        ):
            aligned = (
                sla_breach
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_ROUTE_DISRUPTION_CONTINGENCY"
        ):
            aligned = (
                disruption_count > 0
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_PRIORITY_ROUTE_REVIEW"
        ):
            aligned = (
                priority
                in {
                    "HIGH",
                    "CRITICAL",
                }
                and
                delay_minutes >= 60.0
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_ROUTE_PERFORMANCE_REVIEW"
        ):
            aligned = True

        else:
            aligned = False

        rule_basis = {
            "sla_breach":
                sla_breach,

            "disruption_count":
                disruption_count,

            "priority":
                priority,

            "delay_minutes":
                round(
                    delay_minutes,
                    3,
                ),
        }

    # ========================================================
    # CIRCULARITY
    # ========================================================

    elif domain == "CIRCULARITY":

        missing_dmrv = _safe_int(
            evidence.get(
                "dmrv_missing_records"
            )
        )

        inquiries = _safe_int(
            evidence.get(
                "buyer_inquiry_count"
            )
        )

        bids = _safe_int(
            evidence.get(
                "buyer_bid_count"
            )
        )

        price_gap = _safe_float(
            evidence.get(
                "ask_vs_reference_gap_ratio"
            )
        )

        if (
            recommendation_type
            ==
            "RECOMMEND_DMRV_EVIDENCE_REMEDIATION"
        ):
            aligned = (
                missing_dmrv > 0
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_CREDIT_REPRICE"
        ):
            aligned = (
                price_gap >= 0.10
                and
                bids <= 1
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_BUYER_ENGAGEMENT_FOLLOWUP"
        ):
            aligned = (
                bids > 0
                or
                inquiries >= 3
            )

        elif (
            recommendation_type
            ==
            "RECOMMEND_MARKETPLACE_PRICE_REVIEW"
        ):
            aligned = True

        else:
            aligned = False

        rule_basis = {
            "dmrv_missing_records":
                missing_dmrv,

            "buyer_inquiry_count":
                inquiries,

            "buyer_bid_count":
                bids,

            "ask_vs_reference_gap_ratio":
                round(
                    price_gap,
                    6,
                ),
        }

    else:

        aligned = False

        reason = (
            "Unsupported recommendation domain."
        )

    if aligned:

        result = CHECK_PASS
        severity = SEVERITY_INFO

    else:

        result = CHECK_FAIL
        severity = SEVERITY_HIGH

        reason = (
            "Recommendation type is not supported "
            "by its observable policy evidence."
        )

    details = {
        "domain":
            domain,

        "recommendation_type":
            recommendation_type,

        "policy_aligned":
            bool(
                aligned
            ),

        "rule_basis":
            rule_basis,
    }

    return (
        result,
        severity,
        reason,
        details,
    )


# ============================================================
# HUMAN CONTROL CHECK
# ============================================================


def _evaluate_human_control_check(
    recommendation: Mapping[str, Any],
    human_review_required: bool,
    review_priority_score: float,
) -> tuple[
    str,
    str,
    str,
    dict[str, Any],
]:
    """
    Record result of configured human-control routing policy.
    """

    if human_review_required:

        result = (
            CHECK_REVIEW_REQUIRED
        )

        severity = (
            SEVERITY_HIGH
            if str(
                recommendation[
                    "risk_level"
                ]
            ).upper()
            == "HIGH"
            else
            SEVERITY_MEDIUM
        )

        reason = (
            "Recommendation was routed to "
            "human review by the configured governance gate."
        )

    else:

        result = (
            CHECK_PASS
        )

        severity = (
            SEVERITY_INFO
        )

        reason = (
            "Recommendation remained within the "
            "automated policy decision population."
        )

    details = {
        "human_review_required":
            bool(
                human_review_required
            ),

        "review_priority_score":
            round(
                review_priority_score,
                6,
            ),

        "recommendation_risk_level":
            str(
                recommendation[
                    "risk_level"
                ]
            ),

        "recommendation_confidence":
            round(
                _safe_float(
                    recommendation[
                        "confidence"
                    ]
                ),
                6,
            ),
    }

    return (
        result,
        severity,
        reason,
        details,
    )


# ============================================================
# TIMELINE
# ============================================================


def _build_event_timeline(
    recommendation_generated_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> dict[str, Any]:
    """
    Build ordered governance event timestamps.

    Maximum normal governance span is four hours.

    If the recommendation occurs close to generation_end,
    timestamps are compressed proportionally into the remaining
    window while retaining correct ordering.
    """

    recommendation_time = pd.Timestamp(
        recommendation_generated_at
    )

    if recommendation_time.tzinfo is None:
        raise ValueError(
            "Recommendation generated_at must be timezone-aware"
        )

    end_time = pd.Timestamp(
        generation_end
    )

    if end_time.tzinfo is None:
        raise ValueError(
            "Generation end must be timezone-aware"
        )

    recommendation_time = (
        recommendation_time
        .tz_convert(
            end_time.tz
        )
    )

    remaining_seconds = float(
        (
            end_time
            -
            recommendation_time
        )
        .total_seconds()
    )

    if remaining_seconds <= 10.0:
        raise ValueError(
            "Recommendation timestamp leaves insufficient "
            "time for trust/compliance events"
        )

    usable_seconds = min(
        remaining_seconds
        -
        1.0,
        4.0
        *
        60.0
        *
        60.0,
    )

    fractions = {
        "check_1":
            0.10,

        "check_2":
            0.20,

        "check_3":
            0.30,

        "check_4":
            0.40,

        "check_5":
            0.50,

        "human_review_requested":
            0.60,

        "auto_decision":
            0.68,

        "human_review_completed":
            0.82,

        "human_decision":
            0.90,
    }

    return {
        key:
            (
                recommendation_time
                +
                pd.Timedelta(
                    seconds=
                        usable_seconds
                        *
                        fraction
                )
            )

        for key,
        fraction
        in fractions.items()
    }


# ============================================================
# CHECK RECORD
# ============================================================


def _make_check_record(
    compliance_check_id: str,
    decision_id: str,
    recommendation: Mapping[str, Any],
    rule_code: str,
    checked_at: pd.Timestamp,
    result: str,
    severity: str,
    reason: str,
    details: Mapping[str, Any],
    data_origin: str,
    generator_version: str,
) -> dict[str, Any]:
    """
    Build one compliance-check event.
    """

    return {
        "compliance_check_id":
            compliance_check_id,

        "decision_id":
            decision_id,

        "recommendation_id":
            str(
                recommendation[
                    "recommendation_id"
                ]
            ),

        "domain":
            str(
                recommendation[
                    "domain"
                ]
            ),

        "rule_code":
            rule_code,

        "rule_name":
            RULE_NAMES[
                rule_code
            ],

        "checked_at":
            checked_at,

        "result":
            result,

        "severity":
            severity,

        "reason":
            reason,

        "evidence_json":
            _canonical_json(
                details
            ),

        "data_origin":
            data_origin,

        "generator_version":
            generator_version,
    }


# ============================================================
# HUMAN REVIEW OUTCOME
# ============================================================


def _derive_human_review_decision(
    recommendation: Mapping[str, Any],
    compliance_fail_count: int,
    review_priority_score: float,
) -> tuple[
    str,
    str,
    str,
]:
    """
    Derive deterministic human-review outcome from governance
    evidence.

    This is synthetic reviewer behavior, not hidden recommendation
    ground truth.
    """

    risk = str(
        recommendation[
            "risk_level"
        ]
    ).upper()

    confidence = _clip01(
        _safe_float(
            recommendation[
                "confidence"
            ]
        )
    )

    if compliance_fail_count > 0:

        return (
            DECISION_REJECTED,

            "COMPLIANCE_FAILURE",

            (
                "Human reviewer rejected the recommendation "
                "because at least one compliance policy failed."
            ),
        )

    if (
        risk == "HIGH"
        and
        confidence < 0.875
    ):

        return (
            DECISION_REJECTED,

            "HIGH_RISK_LOW_EVIDENCE_CONFIDENCE",

            (
                "Human reviewer rejected the high-risk "
                "recommendation because evidence confidence "
                "was below the review threshold."
            ),
        )

    if (
        risk == "HIGH"
        and
        confidence < 0.920
    ):

        return (
            DECISION_MODIFIED,

            "HIGH_RISK_GUARDRAIL_ADDED",

            (
                "Human reviewer accepted the recommendation "
                "with additional execution guardrails."
            ),
        )

    if (
        risk == "HIGH"
        and
        review_priority_score >= 0.80
    ):

        return (
            DECISION_ESCALATED,

            "MATERIAL_HIGH_RISK_DECISION",

            (
                "Human reviewer escalated the recommendation "
                "because the action remained materially high risk."
            ),
        )

    if (
        risk == "MEDIUM"
        and
        confidence < 0.80
    ):

        return (
            DECISION_MODIFIED,

            "MEDIUM_RISK_EVIDENCE_GUARDRAIL",

            (
                "Human reviewer retained the recommendation "
                "with additional control conditions."
            ),
        )

    return (
        DECISION_APPROVED,

        "HUMAN_REVIEW_APPROVED",

        (
            "Human reviewer approved the recommendation "
            "after reviewing evidence and policy checks."
        ),
    )


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_trust(
    recommendations: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate:

        compliance_checks
        trust_decisions
        human_reviews
    """

    if generation is None:
        generation = (
            load_generation_config()
        )

    _validate_recommendation_input(
        recommendations
    )

    (
        checks_per_decision,
        human_review_rate,
    ) = _get_governance_config(
        generation
    )

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
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
    # SELECT HUMAN-REVIEW POPULATION
    # ========================================================

    (
        human_review_recommendation_ids,
        recommendation_work,
    ) = _select_human_reviews(
        recommendations=
            recommendations,

        human_review_rate=
            human_review_rate,
    )

    review_score_lookup = (
        recommendation_work
        .set_index(
            "recommendation_id"
        )[
            "_review_priority_score"
        ]
        .to_dict()
    )

    # ========================================================
    # OUTPUT ROWS
    # ========================================================

    check_rows: list[
        dict[str, Any]
    ] = []

    decision_rows: list[
        dict[str, Any]
    ] = []

    review_rows: list[
        dict[str, Any]
    ] = []

    compliance_sequence = 0
    review_sequence = 0

    # ========================================================
    # PROCESS EACH RECOMMENDATION
    # ========================================================

    ordered_recommendations = (
        recommendations
        .sort_values(
            "recommendation_id"
        )
        .reset_index(
            drop=True
        )
    )

    for (
        decision_sequence,
        recommendation,
    ) in enumerate(
        ordered_recommendations.to_dict(
            orient="records"
        ),
        start=1,
    ):

        recommendation_id = str(
            recommendation[
                "recommendation_id"
            ]
        )

        decision_id = generate_id(
            "DECISION_SYN",
            decision_sequence,
            width=7,
        )

        review_priority_score = float(
            review_score_lookup[
                recommendation_id
            ]
        )

        human_review_required = (
            recommendation_id
            in human_review_recommendation_ids
        )

        evidence = _parse_json_object(
            value=
                recommendation[
                    "evidence_json"
                ],

            field_name=
                "evidence_json",

            recommendation_id=
                recommendation_id,
        )

        expected_impact = _parse_json_object(
            value=
                recommendation[
                    "expected_impact"
                ],

            field_name=
                "expected_impact",

            recommendation_id=
                recommendation_id,
        )

        generated_at = pd.Timestamp(
            recommendation[
                "generated_at"
            ]
        )

        if generated_at.tzinfo is None:
            raise ValueError(
                f"{recommendation_id}: generated_at "
                "must be timezone-aware"
            )

        if (
            generated_at
            <
            generation_start
            or
            generated_at
            >=
            generation_end
        ):
            raise ValueError(
                f"{recommendation_id}: generated_at "
                "outside synthetic generation window"
            )

        timeline = _build_event_timeline(
            recommendation_generated_at=
                generated_at,

            generation_end=
                generation_end,
        )

        # ====================================================
        # EVALUATE FIVE CHECKS
        # ====================================================

        evaluations: list[
            tuple[
                str,
                str,
                str,
                str,
                dict[str, Any],
            ]
        ] = []

        (
            result,
            severity,
            reason,
            details,
        ) = _evaluate_lineage_check(
            recommendation=
                recommendation,

            evidence=
                evidence,
        )

        evaluations.append(
            (
                RULE_LINEAGE,
                result,
                severity,
                reason,
                details,
            )
        )

        (
            result,
            severity,
            reason,
            details,
        ) = _evaluate_evidence_check(
            recommendation=
                recommendation,

            evidence=
                evidence,

            expected_impact=
                expected_impact,
        )

        evaluations.append(
            (
                RULE_EVIDENCE,
                result,
                severity,
                reason,
                details,
            )
        )

        (
            result,
            severity,
            reason,
            details,
        ) = _evaluate_fairness_scope_check(
            evidence=
                evidence,
        )

        evaluations.append(
            (
                RULE_FAIRNESS,
                result,
                severity,
                reason,
                details,
            )
        )

        (
            result,
            severity,
            reason,
            details,
        ) = _evaluate_business_policy_check(
            recommendation=
                recommendation,

            evidence=
                evidence,
        )

        evaluations.append(
            (
                RULE_POLICY,
                result,
                severity,
                reason,
                details,
            )
        )

        (
            result,
            severity,
            reason,
            details,
        ) = _evaluate_human_control_check(
            recommendation=
                recommendation,

            human_review_required=
                human_review_required,

            review_priority_score=
                review_priority_score,
        )

        evaluations.append(
            (
                RULE_HUMAN_CONTROL,
                result,
                severity,
                reason,
                details,
            )
        )

        if len(
            evaluations
        ) != checks_per_decision:
            raise ValueError(
                f"{recommendation_id}: expected "
                f"{checks_per_decision} compliance checks, "
                f"generated {len(evaluations)}"
            )

        # ====================================================
        # WRITE CHECK ROWS
        # ====================================================

        recommendation_check_rows: list[
            dict[str, Any]
        ] = []

        for check_position, (
            rule_code,
            result,
            severity,
            reason,
            details,
        ) in enumerate(
            evaluations,
            start=1,
        ):

            compliance_sequence += 1

            check_id = generate_id(
                "COMPCHK_SYN",
                compliance_sequence,
                width=8,
            )

            check_record = _make_check_record(
                compliance_check_id=
                    check_id,

                decision_id=
                    decision_id,

                recommendation=
                    recommendation,

                rule_code=
                    rule_code,

                checked_at=
                    timeline[
                        f"check_{check_position}"
                    ],

                result=
                    result,

                severity=
                    severity,

                reason=
                    reason,

                details=
                    details,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )

            check_rows.append(
                check_record
            )

            recommendation_check_rows.append(
                check_record
            )

        # ====================================================
        # CHECK SUMMARY
        # ====================================================

        pass_count = sum(
            1
            for record
            in recommendation_check_rows
            if record[
                "result"
            ]
            ==
            CHECK_PASS
        )

        warn_count = sum(
            1
            for record
            in recommendation_check_rows
            if record[
                "result"
            ]
            ==
            CHECK_WARN
        )

        fail_count = sum(
            1
            for record
            in recommendation_check_rows
            if record[
                "result"
            ]
            ==
            CHECK_FAIL
        )

        review_required_count = sum(
            1
            for record
            in recommendation_check_rows
            if record[
                "result"
            ]
            ==
            CHECK_REVIEW_REQUIRED
        )

        # ====================================================
        # HUMAN REVIEW
        # ====================================================

        review_id: str | None = None

        if human_review_required:

            review_sequence += 1

            review_id = generate_id(
                "HREV_SYN",
                review_sequence,
                width=7,
            )

            (
                review_decision,
                review_reason_code,
                review_free_text,
            ) = _derive_human_review_decision(
                recommendation=
                    recommendation,

                compliance_fail_count=
                    fail_count,

                review_priority_score=
                    review_priority_score,
            )

            review_rows.append(
                {
                    "review_id":
                        review_id,

                    "decision_id":
                        decision_id,

                    "recommendation_id":
                        recommendation_id,

                    "reviewer_role":
                        REVIEWER_ROLE_BY_DOMAIN.get(
                            str(
                                recommendation[
                                    "domain"
                                ]
                            ),
                            "ENTERPRISE_AI_GOVERNANCE_REVIEWER",
                        ),

                    "requested_at":
                        timeline[
                            "human_review_requested"
                        ],

                    "completed_at":
                        timeline[
                            "human_review_completed"
                        ],

                    "decision":
                        review_decision,

                    "reason_code":
                        review_reason_code,

                    "free_text":
                        review_free_text,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            trust_decision = (
                review_decision
            )

            decision_mode = (
                MODE_HUMAN_REVIEW
            )

            decided_at = (
                timeline[
                    "human_decision"
                ]
            )

            decision_reason_code = (
                review_reason_code
            )

        # ====================================================
        # AUTOMATED POLICY DECISION
        # ====================================================

        else:

            if fail_count > 0:

                trust_decision = (
                    DECISION_REJECTED
                )

                decision_reason_code = (
                    "AUTOMATED_COMPLIANCE_REJECTION"
                )

            else:

                trust_decision = (
                    DECISION_APPROVED
                )

                if warn_count > 0:

                    decision_reason_code = (
                        "AUTO_APPROVED_WITH_MONITORING"
                    )

                else:

                    decision_reason_code = (
                        "AUTO_APPROVED_POLICY_PASS"
                    )

            decision_mode = (
                MODE_AUTOMATED_POLICY
            )

            decided_at = (
                timeline[
                    "auto_decision"
                ]
            )

        # ====================================================
        # TRUST DECISION
        # ====================================================

        decision_rows.append(
            {
                "decision_id":
                    decision_id,

                "recommendation_id":
                    recommendation_id,

                "domain":
                    str(
                        recommendation[
                            "domain"
                        ]
                    ),

                "use_case":
                    str(
                        recommendation[
                            "use_case"
                        ]
                    ),

                "target_entity_type":
                    str(
                        recommendation[
                            "target_entity_type"
                        ]
                    ),

                "target_entity_id":
                    str(
                        recommendation[
                            "target_entity_id"
                        ]
                    ),

                "recommendation_type":
                    str(
                        recommendation[
                            "recommendation_type"
                        ]
                    ),

                "recommendation_confidence":
                    round(
                        _safe_float(
                            recommendation[
                                "confidence"
                            ]
                        ),
                        6,
                    ),

                "recommendation_risk_level":
                    str(
                        recommendation[
                            "risk_level"
                        ]
                    ),

                "decision_mode":
                    decision_mode,

                "decision":
                    trust_decision,

                "decided_at":
                    decided_at,

                "compliance_checks_count":
                    len(
                        recommendation_check_rows
                    ),

                "compliance_pass_count":
                    pass_count,

                "compliance_warn_count":
                    warn_count,

                "compliance_fail_count":
                    fail_count,

                "compliance_review_required_count":
                    review_required_count,

                "human_review_required":
                    bool(
                        human_review_required
                    ),

                "human_review_id":
                    review_id,

                "review_priority_score":
                    round(
                        review_priority_score,
                        6,
                    ),

                "decision_reason_code":
                    decision_reason_code,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    # ========================================================
    # DATAFRAMES
    # ========================================================

    compliance_checks = pd.DataFrame(
        check_rows
    )

    trust_decisions = pd.DataFrame(
        decision_rows
    )

    human_reviews = pd.DataFrame(
        review_rows
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    validate_trust(
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

    return (
        compliance_checks,
        trust_decisions,
        human_reviews,
    )


# ============================================================
# PAYLOAD LEAKAGE SCAN
# ============================================================


def _scan_payload_keys(
    value: Any,
    path: str = "",
) -> list[str]:
    """
    Locate forbidden hidden-truth keys recursively.
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


def validate_trust(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate trust/compliance/human-review records.
    """

    _validate_recommendation_input(
        recommendations
    )

    (
        checks_per_decision,
        human_review_rate,
    ) = _get_governance_config(
        generation
    )

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    expected_decisions = len(
        recommendations
    )

    expected_checks = (
        expected_decisions
        *
        checks_per_decision
    )

    expected_reviews = int(
        round(
            expected_decisions
            *
            human_review_rate
        )
    )

    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    required_check_columns = {
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

    required_decision_columns = {
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

    required_review_columns = {
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

    missing_checks = (
        required_check_columns
        -
        set(
            compliance_checks.columns
        )
    )

    missing_decisions = (
        required_decision_columns
        -
        set(
            trust_decisions.columns
        )
    )

    missing_reviews = (
        required_review_columns
        -
        set(
            human_reviews.columns
        )
    )

    if missing_checks:
        raise ValueError(
            "Compliance checks missing columns: "
            +
            ", ".join(
                sorted(
                    missing_checks
                )
            )
        )

    if missing_decisions:
        raise ValueError(
            "Trust decisions missing columns: "
            +
            ", ".join(
                sorted(
                    missing_decisions
                )
            )
        )

    if missing_reviews:
        raise ValueError(
            "Human reviews missing columns: "
            +
            ", ".join(
                sorted(
                    missing_reviews
                )
            )
        )

    # ========================================================
    # EXACT COUNTS
    # ========================================================

    if len(
        trust_decisions
    ) != expected_decisions:
        raise ValueError(
            "Trust-decision count must equal "
            "recommendation count"
        )

    if len(
        compliance_checks
    ) != expected_checks:
        raise ValueError(
            "Compliance-check count mismatch. "
            f"Expected={expected_checks}, "
            f"actual={len(compliance_checks)}"
        )

    if len(
        human_reviews
    ) != expected_reviews:
        raise ValueError(
            "Human-review count mismatch. "
            f"Expected={expected_reviews}, "
            f"actual={len(human_reviews)}"
        )

    # ========================================================
    # UNIQUE IDS
    # ========================================================

    for dataframe, id_column in (
        (
            compliance_checks,
            "compliance_check_id",
        ),
        (
            trust_decisions,
            "decision_id",
        ),
        (
            human_reviews,
            "review_id",
        ),
    ):

        if (
            dataframe[
                id_column
            ]
            .isna()
            .any()
        ):
            raise ValueError(
                f"{id_column} cannot contain null values"
            )

        if (
            dataframe[
                id_column
            ]
            .duplicated()
            .any()
        ):
            raise ValueError(
                f"Duplicate {id_column} values found"
            )

    # ========================================================
    # RECOMMENDATION FK
    # ========================================================

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
        decision_recommendation_ids
        !=
        recommendation_ids
    ):
        raise ValueError(
            "Every recommendation must have exactly "
            "one trust decision"
        )

    if (
        trust_decisions[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "A recommendation has more than one "
            "trust decision"
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

    # ========================================================
    # DECISION FK
    # ========================================================

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

    # ========================================================
    # EXACTLY FIVE DISTINCT CHECKS PER DECISION
    # ========================================================

    checks_per_group = (
        compliance_checks
        .groupby(
            "decision_id"
        )
        .size()
    )

    if not (
        checks_per_group
        ==
        checks_per_decision
    ).all():
        raise ValueError(
            "Every trust decision must have exactly "
            f"{checks_per_decision} compliance checks"
        )

    distinct_rules = (
        compliance_checks
        .groupby(
            "decision_id"
        )[
            "rule_code"
        ]
        .nunique()
    )

    if not (
        distinct_rules
        ==
        checks_per_decision
    ).all():
        raise ValueError(
            "Every decision must contain five "
            "distinct compliance rules"
        )

    for decision_id, group in (
        compliance_checks.groupby(
            "decision_id"
        )
    ):

        observed_rules = set(
            group[
                "rule_code"
            ]
            .astype(
                str
            )
        )

        if observed_rules != set(
            COMPLIANCE_RULES
        ):
            raise ValueError(
                f"{decision_id}: compliance rule set mismatch"
            )

    # ========================================================
    # CHECK ENUMS
    # ========================================================

    invalid_results = (
        set(
            compliance_checks[
                "result"
            ]
            .astype(
                str
            )
        )
        -
        VALID_CHECK_RESULTS
    )

    if invalid_results:
        raise ValueError(
            "Invalid compliance-check results found"
        )

    invalid_severities = (
        set(
            compliance_checks[
                "severity"
            ]
            .astype(
                str
            )
        )
        -
        VALID_SEVERITIES
    )

    if invalid_severities:
        raise ValueError(
            "Invalid compliance severity found"
        )

    # ========================================================
    # TRUST DECISION ENUMS
    # ========================================================

    invalid_decisions = (
        set(
            trust_decisions[
                "decision"
            ]
            .astype(
                str
            )
        )
        -
        VALID_DECISIONS
    )

    if invalid_decisions:
        raise ValueError(
            "Invalid trust decision found"
        )

    invalid_modes = (
        set(
            trust_decisions[
                "decision_mode"
            ]
            .astype(
                str
            )
        )
        -
        VALID_DECISION_MODES
    )

    if invalid_modes:
        raise ValueError(
            "Invalid trust decision mode found"
        )

    invalid_review_decisions = (
        set(
            human_reviews[
                "decision"
            ]
            .astype(
                str
            )
        )
        -
        VALID_DECISIONS
    )

    if invalid_review_decisions:
        raise ValueError(
            "Invalid human-review decision found"
        )

    # ========================================================
    # REVIEW FK / MODE CONSISTENCY
    # ========================================================

    reviewed_decisions = trust_decisions.loc[
        trust_decisions[
            "human_review_required"
        ].astype(
            bool
        )
    ]

    automated_decisions = trust_decisions.loc[
        ~trust_decisions[
            "human_review_required"
        ].astype(
            bool
        )
    ]

    if len(
        reviewed_decisions
    ) != expected_reviews:
        raise ValueError(
            "Human-review-required decision count mismatch"
        )

    if (
        reviewed_decisions[
            "human_review_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Human-reviewed decisions require human_review_id"
        )

    if (
        automated_decisions[
            "human_review_id"
        ]
        .notna()
        .any()
    ):
        raise ValueError(
            "Automated decisions cannot reference "
            "a human review"
        )

    if not (
        reviewed_decisions[
            "decision_mode"
        ]
        ==
        MODE_HUMAN_REVIEW
    ).all():
        raise ValueError(
            "Human-reviewed decisions require HUMAN_REVIEW mode"
        )

    if not (
        automated_decisions[
            "decision_mode"
        ]
        ==
        MODE_AUTOMATED_POLICY
    ).all():
        raise ValueError(
            "Non-reviewed decisions require "
            "AUTOMATED_POLICY mode"
        )

    review_ids = set(
        human_reviews[
            "review_id"
        ]
        .astype(
            str
        )
    )

    decision_review_ids = set(
        reviewed_decisions[
            "human_review_id"
        ]
        .astype(
            str
        )
    )

    if review_ids != decision_review_ids:
        raise ValueError(
            "Human-review IDs and reviewed decisions do not match"
        )

    # ========================================================
    # HUMAN REVIEW DECISION = TRUST DECISION
    # ========================================================

    decision_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
    )

    for review in human_reviews.itertuples(
        index=False
    ):

        decision = decision_lookup.loc[
            str(
                review.decision_id
            )
        ]

        if (
            str(
                decision[
                    "recommendation_id"
                ]
            )
            !=
            str(
                review.recommendation_id
            )
        ):
            raise ValueError(
                f"{review.review_id}: recommendation mismatch"
            )

        if (
            str(
                decision[
                    "decision"
                ]
            )
            !=
            str(
                review.decision
            )
        ):
            raise ValueError(
                f"{review.review_id}: human-review decision "
                "does not match trust decision"
            )

    # ========================================================
    # CHECK SUMMARY COUNTS
    # ========================================================

    result_count_table = (
        compliance_checks
        .groupby(
            [
                "decision_id",
                "result",
            ]
        )
        .size()
        .unstack(
            fill_value=0
        )
    )

    for decision in trust_decisions.itertuples(
        index=False
    ):

        decision_id = str(
            decision.decision_id
        )

        counts = (
            result_count_table.loc[
                decision_id
            ]
            if decision_id
            in result_count_table.index
            else pd.Series(
                dtype=int
            )
        )

        expected_pass = int(
            counts.get(
                CHECK_PASS,
                0,
            )
        )

        expected_warn = int(
            counts.get(
                CHECK_WARN,
                0,
            )
        )

        expected_fail = int(
            counts.get(
                CHECK_FAIL,
                0,
            )
        )

        expected_review = int(
            counts.get(
                CHECK_REVIEW_REQUIRED,
                0,
            )
        )

        if (
            int(
                decision.compliance_pass_count
            )
            != expected_pass
        ):
            raise ValueError(
                f"{decision_id}: PASS count mismatch"
            )

        if (
            int(
                decision.compliance_warn_count
            )
            != expected_warn
        ):
            raise ValueError(
                f"{decision_id}: WARN count mismatch"
            )

        if (
            int(
                decision.compliance_fail_count
            )
            != expected_fail
        ):
            raise ValueError(
                f"{decision_id}: FAIL count mismatch"
            )

        if (
            int(
                decision.compliance_review_required_count
            )
            != expected_review
        ):
            raise ValueError(
                f"{decision_id}: REVIEW_REQUIRED count mismatch"
            )

        if (
            int(
                decision.compliance_checks_count
            )
            != checks_per_decision
        ):
            raise ValueError(
                f"{decision_id}: total compliance count mismatch"
            )

    # ========================================================
    # HUMAN CONTROL GATE CONSISTENCY
    # ========================================================

    human_gate = compliance_checks.loc[
        compliance_checks[
            "rule_code"
        ]
        ==
        RULE_HUMAN_CONTROL
    ]

    human_gate_lookup = (
        human_gate
        .set_index(
            "decision_id"
        )[
            "result"
        ]
    )

    for decision in trust_decisions.itertuples(
        index=False
    ):

        gate_result = str(
            human_gate_lookup.loc[
                str(
                    decision.decision_id
                )
            ]
        )

        if bool(
            decision.human_review_required
        ):

            if gate_result != CHECK_REVIEW_REQUIRED:
                raise ValueError(
                    f"{decision.decision_id}: reviewed decision "
                    "missing REVIEW_REQUIRED gate"
                )

        else:

            if gate_result != CHECK_PASS:
                raise ValueError(
                    f"{decision.decision_id}: automated decision "
                    "has inconsistent human-control gate"
                )

    # ========================================================
    # TIMESTAMP ORDER
    # ========================================================

    recommendation_time_lookup = (
        recommendations
        .assign(
            _generated_at_utc=
                pd.to_datetime(
                    recommendations[
                        "generated_at"
                    ],
                    errors="raise",
                    utc=True,
                )
        )
        .set_index(
            "recommendation_id"
        )[
            "_generated_at_utc"
        ]
    )

    checked_at = pd.to_datetime(
        compliance_checks[
            "checked_at"
        ],
        errors="raise",
        utc=True,
    )

    decided_at = pd.to_datetime(
        trust_decisions[
            "decided_at"
        ],
        errors="raise",
        utc=True,
    )

    requested_at = pd.to_datetime(
        human_reviews[
            "requested_at"
        ],
        errors="raise",
        utc=True,
    )

    completed_at = pd.to_datetime(
        human_reviews[
            "completed_at"
        ],
        errors="raise",
        utc=True,
    )

    generation_end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    if (
        checked_at
        >= generation_end_utc
    ).any():
        raise ValueError(
            "Compliance check occurs outside generation window"
        )

    if (
        decided_at
        >= generation_end_utc
    ).any():
        raise ValueError(
            "Trust decision occurs outside generation window"
        )

    if (
        requested_at
        >= generation_end_utc
    ).any():
        raise ValueError(
            "Human review request outside generation window"
        )

    if (
        completed_at
        >= generation_end_utc
    ).any():
        raise ValueError(
            "Human review completion outside generation window"
        )

    for check in compliance_checks.itertuples(
        index=False
    ):

        recommendation_time = (
            recommendation_time_lookup.loc[
                str(
                    check.recommendation_id
                )
            ]
        )

        check_time = pd.Timestamp(
            check.checked_at
        )

        if check_time.tzinfo is None:
            raise ValueError(
                "Compliance timestamp must be timezone-aware"
            )

        check_time = (
            check_time
            .tz_convert(
                "UTC"
            )
        )

        if check_time <= recommendation_time:
            raise ValueError(
                f"{check.compliance_check_id}: "
                "compliance check must occur after recommendation"
            )

    for decision in trust_decisions.itertuples(
        index=False
    ):

        recommendation_time = (
            recommendation_time_lookup.loc[
                str(
                    decision.recommendation_id
                )
            ]
        )

        decision_time = pd.Timestamp(
            decision.decided_at
        )

        if decision_time.tzinfo is None:
            raise ValueError(
                "Trust decision timestamp must be timezone-aware"
            )

        decision_time = (
            decision_time
            .tz_convert(
                "UTC"
            )
        )

        if decision_time <= recommendation_time:
            raise ValueError(
                f"{decision.decision_id}: decision must "
                "occur after recommendation"
            )

        latest_check = (
            pd.to_datetime(
                compliance_checks.loc[
                    compliance_checks[
                        "decision_id"
                    ]
                    ==
                    str(
                        decision.decision_id
                    ),
                    "checked_at",
                ],
                utc=True,
            )
            .max()
        )

        if decision_time <= latest_check:
            raise ValueError(
                f"{decision.decision_id}: decision must "
                "occur after all compliance checks"
            )

    for review in human_reviews.itertuples(
        index=False
    ):

        requested = pd.Timestamp(
            review.requested_at
        ).tz_convert(
            "UTC"
        )

        completed = pd.Timestamp(
            review.completed_at
        ).tz_convert(
            "UTC"
        )

        decision_time = pd.Timestamp(
            decision_lookup.loc[
                str(
                    review.decision_id
                ),
                "decided_at",
            ]
        ).tz_convert(
            "UTC"
        )

        if completed <= requested:
            raise ValueError(
                f"{review.review_id}: review completion "
                "must follow request"
            )

        if decision_time < completed:
            raise ValueError(
                f"{review.review_id}: trust decision "
                "cannot precede review completion"
            )

    # ========================================================
    # APPROVED RECOMMENDATION MUST HAVE DECISION RECORD
    # ========================================================

    approved = trust_decisions.loc[
        trust_decisions[
            "decision"
        ]
        ==
        DECISION_APPROVED
    ]

    if (
        approved[
            "decision_id"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Approved recommendation without decision record"
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

    for name, dataframe in (
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
    ):

        if not (
            dataframe[
                "data_origin"
            ]
            ==
            expected_origin
        ).all():
            raise ValueError(
                f"{name}: data_origin mismatch"
            )

        if not (
            dataframe[
                "generator_version"
            ]
            ==
            expected_version
        ).all():
            raise ValueError(
                f"{name}: generator_version mismatch"
            )

    # ========================================================
    # JSON PAYLOAD VALIDATION
    # ========================================================

    for check in compliance_checks.itertuples(
        index=False
    ):

        payload = _parse_json_object(
            value=
                check.evidence_json,

            field_name=
                "compliance evidence_json",

            recommendation_id=
                str(
                    check.recommendation_id
                ),
        )

        violations = _scan_payload_keys(
            payload,
            "evidence_json",
        )

        if violations:
            raise ValueError(
                f"{check.compliance_check_id}: "
                "hidden truth leaked into compliance evidence"
            )

    # ========================================================
    # COLUMN LEAKAGE
    # ========================================================

    for name, dataframe in (
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
    ):

        leakage_columns = [
            column

            for column
            in dataframe.columns

            if any(
                fragment
                in column.lower()

                for fragment
                in FORBIDDEN_OUTPUT_COLUMN_FRAGMENTS
            )
        ]

        if leakage_columns:
            raise ValueError(
                f"{name}: hidden truth/runtime leakage: "
                +
                ", ".join(
                    leakage_columns
                )
            )


# ============================================================
# PUBLIC ALIAS
# ============================================================


def generate_trust_records(
    recommendations: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Alias for generate_all.py orchestration.
    """

    return generate_trust(
        recommendations=
            recommendations,

        generation=
            generation,
    )


# ============================================================
# LOCAL TEST
# ============================================================


if __name__ == "__main__":

    from data.generators.governance.recommendations import (
        _build_local_validation_fixture,
        generate_recommendations,
    )

    generation_config = (
        load_generation_config()
    )

    (
        checks_per_decision,
        human_review_rate,
    ) = _get_governance_config(
        generation_config
    )

    # ========================================================
    # BUILD RECOMMENDATION FIXTURE
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

    print(
        "\n=== TRUST GOVERNANCE CONFIG ===\n"
    )

    print(
        "Recommendations:",
        len(
            recommendations_df
        ),
    )

    print(
        "Compliance checks per decision:",
        checks_per_decision,
    )

    print(
        "Human review rate:",
        human_review_rate,
    )

    print(
        "Expected compliance checks:",
        len(
            recommendations_df
        )
        *
        checks_per_decision,
    )

    print(
        "Expected human reviews:",
        int(
            round(
                len(
                    recommendations_df
                )
                *
                human_review_rate
            )
        ),
    )

    # ========================================================
    # GENERATE
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

    # ========================================================
    # DETERMINISM
    # ========================================================

    (
        compliance_checks_repeat_df,
        trust_decisions_repeat_df,
        human_reviews_repeat_df,
    ) = generate_trust(
        recommendations=
            recommendations_df,

        generation=
            generation_config,
    )

    pd.testing.assert_frame_equal(
        compliance_checks_df,
        compliance_checks_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        trust_decisions_df,
        trust_decisions_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        human_reviews_df,
        human_reviews_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    # ========================================================
    # SAMPLE TRUST DECISIONS
    # ========================================================

    print(
        "\n=== TRUST DECISION SAMPLE ===\n"
    )

    decision_sample_columns = [
        "decision_id",
        "recommendation_id",
        "domain",
        "recommendation_type",
        "recommendation_confidence",
        "recommendation_risk_level",
        "decision_mode",
        "decision",
        "human_review_required",
        "compliance_pass_count",
        "compliance_warn_count",
        "compliance_fail_count",
        "compliance_review_required_count",
        "decision_reason_code",
    ]

    print(
        trust_decisions_df[
            decision_sample_columns
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # COMPLIANCE RESULT MIX
    # ========================================================

    print(
        "\n=== COMPLIANCE CHECK RESULT MIX ===\n"
    )

    compliance_mix = (
        compliance_checks_df
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
                    "checks"
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
        compliance_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # TRUST DECISION MIX
    # ========================================================

    print(
        "\n=== TRUST DECISION MIX ===\n"
    )

    decision_mix = (
        trust_decisions_df
        .groupby(
            [
                "decision_mode",
                "decision",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "decisions"
            }
        )
        .sort_values(
            [
                "decision_mode",
                "decision",
            ]
        )
    )

    print(
        decision_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # DOMAIN DECISIONS
    # ========================================================

    print(
        "\n=== TRUST DECISIONS BY DOMAIN ===\n"
    )

    domain_decisions = (
        trust_decisions_df
        .groupby(
            [
                "domain",
                "decision",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "decisions"
            }
        )
        .sort_values(
            [
                "domain",
                "decision",
            ]
        )
    )

    print(
        domain_decisions.to_string(
            index=False
        )
    )

    # ========================================================
    # HUMAN REVIEW ROUTING
    # ========================================================

    print(
        "\n=== HUMAN REVIEW ROUTING BY DOMAIN ===\n"
    )

    review_routing = (
        trust_decisions_df
        .groupby(
            "domain",
            as_index=False,
        )
        .agg(
            decisions=(
                "decision_id",
                "count",
            ),

            human_reviews=(
                "human_review_required",
                "sum",
            ),

            average_review_priority=(
                "review_priority_score",
                "mean",
            ),
        )
    )

    review_routing[
        "human_review_rate"
    ] = (
        review_routing[
            "human_reviews"
        ]
        /
        review_routing[
            "decisions"
        ]
    ).round(
        4
    )

    review_routing[
        "average_review_priority"
    ] = (
        review_routing[
            "average_review_priority"
        ]
        .round(
            4
        )
    )

    print(
        review_routing.to_string(
            index=False
        )
    )

    # ========================================================
    # HUMAN REVIEW OUTCOMES
    # ========================================================

    print(
        "\n=== HUMAN REVIEW OUTCOMES ===\n"
    )

    human_outcome_mix = (
        human_reviews_df
        .groupby(
            "decision",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "reviews"
            }
        )
        .sort_values(
            "decision"
        )
    )

    print(
        human_outcome_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # HUMAN REVIEW ROLE MIX
    # ========================================================

    print(
        "\n=== HUMAN REVIEW ROLE MIX ===\n"
    )

    reviewer_mix = (
        human_reviews_df
        .groupby(
            "reviewer_role",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "reviews"
            }
        )
        .sort_values(
            "reviews",
            ascending=False,
        )
    )

    print(
        reviewer_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # TEMPORAL CHECK
    # ========================================================

    recommendation_times = (
        recommendations_df
        .assign(
            generated_at_utc=
                pd.to_datetime(
                    recommendations_df[
                        "generated_at"
                    ],
                    utc=True,
                )
        )
        .set_index(
            "recommendation_id"
        )[
            "generated_at_utc"
        ]
    )

    checks_after_recommendation = 0

    for check in (
        compliance_checks_df
        .itertuples(
            index=False
        )
    ):

        if (
            pd.Timestamp(
                check.checked_at
            )
            .tz_convert(
                "UTC"
            )
            >
            recommendation_times.loc[
                str(
                    check.recommendation_id
                )
            ]
        ):
            checks_after_recommendation += 1

    # ========================================================
    # LEAKAGE CHECK
    # ========================================================

    leakage: dict[
        str,
        list[str],
    ] = {}

    for name, dataframe in (
        (
            "compliance_checks",
            compliance_checks_df,
        ),
        (
            "trust_decisions",
            trust_decisions_df,
        ),
        (
            "human_reviews",
            human_reviews_df,
        ),
    ):

        leakage[
            name
        ] = [
            column
            for column
            in dataframe.columns
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
        "\n=== TRUST GOVERNANCE VALIDATION ===\n"
    )

    print(
        "Recommendation rows:",
        len(
            recommendations_df
        ),
    )

    print(
        "Trust decision rows:",
        len(
            trust_decisions_df
        ),
    )

    print(
        "Unique decision IDs:",
        trust_decisions_df[
            "decision_id"
        ]
        .nunique(),
    )

    print(
        "Recommendations with decisions:",
        trust_decisions_df[
            "recommendation_id"
        ]
        .nunique(),
    )

    print(
        "Compliance check rows:",
        len(
            compliance_checks_df
        ),
    )

    print(
        "Unique compliance-check IDs:",
        compliance_checks_df[
            "compliance_check_id"
        ]
        .nunique(),
    )

    print(
        "Decisions with exactly five checks:",
        int(
            (
                compliance_checks_df
                .groupby(
                    "decision_id"
                )
                .size()
                ==
                checks_per_decision
            )
            .sum()
        ),
    )

    print(
        "Human review rows:",
        len(
            human_reviews_df
        ),
    )

    print(
        "Unique human-review IDs:",
        human_reviews_df[
            "review_id"
        ]
        .nunique(),
    )

    print(
        "Human-review rate:",
        round(
            len(
                human_reviews_df
            )
            /
            len(
                trust_decisions_df
            ),
            4,
        ),
    )

    print(
        "Checks occurring after recommendation:",
        checks_after_recommendation,
    )

    print(
        "Compliance checks expected:",
        len(
            recommendations_df
        )
        *
        checks_per_decision,
    )

    print(
        "Compliance checks actual:",
        len(
            compliance_checks_df
        ),
    )

    print(
        "Duplicate decision IDs:",
        int(
            trust_decisions_df[
                "decision_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate compliance-check IDs:",
        int(
            compliance_checks_df[
                "compliance_check_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate human-review IDs:",
        int(
            human_reviews_df[
                "review_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Invalid recommendation FK in decisions:",
        len(
            set(
                trust_decisions_df[
                    "recommendation_id"
                ]
                .astype(str)
            )
            -
            set(
                recommendations_df[
                    "recommendation_id"
                ]
                .astype(str)
            )
        ),
    )

    print(
        "Hidden truth/runtime leakage:",
        leakage,
    )

    print(
        "Deterministic rerun:",
        "PASS",
    )

    print(
        "\nGenerated "
        f"{len(compliance_checks_df)} compliance checks, "
        f"{len(trust_decisions_df)} trust decisions and "
        f"{len(human_reviews_df)} human reviews successfully."
    )