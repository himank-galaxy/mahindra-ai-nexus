"""
Synthetic agent workflow generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate runtime multi-agent activity downstream of the frozen
Governance layer.

Inputs:

    recommendations
    compliance_checks
    trust_decisions
    human_reviews
    audit_events

Outputs:

    1. agent_workflow_runs
    2. agent_events
    3. action_outcomes


============================================================
SOURCE-ALIGNED AGENT ACTIVITY
============================================================

Runtime agent activity contains:

    agent_run_id
    workflow_run_id
    agent_id
    started_at
    completed_at
    status
    input_refs
    output_refs
    human_feedback

The canonical collaboration concept is:

    Data Agent
        ↓
    Prediction Agent
        ↓
    Causal Graph Agent
        ↓
    Simulation Agent
        ↓
    Compliance Agent
        ↓
    Human Review Agent
        ↓
    Action Agent
        ↓
    Learning Agent

The live configuration also contains:

    Code Analytics Agent
    Memory Agent

Those are represented as auxiliary workflow stages.


============================================================
CRITICAL FACTORY RULE
============================================================

workflow.py MUST NOT invent model, causal or simulation artifacts
that do not exist upstream.

Therefore:

    Prediction Agent
    Causal Graph Agent
    Simulation Agent
    Code Analytics Agent

are recorded as SKIPPED when there is no real linked runtime
artifact.

This is deliberate.

A skipped real workflow stage is preferable to fabricating:

    fake prediction IDs
    fake causal edges
    fake simulations
    fake confidence
    fake analytical outputs


============================================================
ACTION RULE
============================================================

Trust decision:

    APPROVED
        → action executes

    MODIFIED
        → action executes with guardrails

    REJECTED
        → action blocked

    ESCALATED
        → action blocked pending escalation


============================================================
ACTION OUTCOMES
============================================================

At this stage, no downstream business observation exists after
the governance snapshot.

Therefore workflow.py records only:

    ACTION_EXECUTION_STATUS

and explicitly sets:

    business_outcome_observed = False

It does NOT fabricate:

    revenue uplift
    recovery uplift
    booking conversion
    SLA improvement
    credit closure
    customer response
    warranty improvement

Those require later actual operational observations / ground truth.


============================================================
WORKFLOW SELECTION
============================================================

Configured workflow count:

    generation["agents"]["workflow_runs"]["count"]

Current configured value:

    1000

Selection is deterministic.

Priority:

1. Human-reviewed recommendations
2. Non-APPROVED decisions
3. Higher governance risk
4. Higher review-priority score
5. Higher uncertainty
6. Stable ID ordering

All governance-significant decisions are retained when the
configured workflow capacity allows.

Remaining slots are filled with broad domain coverage.


============================================================
OUTPUT ONLY
============================================================

No CSV writes occur here.

All generated datasets are returned as pandas DataFrames.
"""

from __future__ import annotations

import json
import re
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
# CONFIGURED AGENT NAMES
# ============================================================

AGENT_DATA = (
    "Data Agent"
)

AGENT_PREDICTION = (
    "Prediction Agent"
)

AGENT_CAUSAL = (
    "Causal Graph Agent"
)

AGENT_SIMULATION = (
    "Simulation Agent"
)

AGENT_CODE_ANALYTICS = (
    "Code Analytics Agent"
)

AGENT_COMPLIANCE = (
    "Compliance Agent"
)

AGENT_ACTION = (
    "Action Agent"
)

AGENT_HUMAN_REVIEW = (
    "Human Review Agent"
)

AGENT_LEARNING = (
    "Learning Agent"
)

AGENT_MEMORY = (
    "Memory Agent"
)


EXPECTED_AGENT_DEFINITIONS = (
    AGENT_DATA,
    AGENT_PREDICTION,
    AGENT_CAUSAL,
    AGENT_SIMULATION,
    AGENT_CODE_ANALYTICS,
    AGENT_COMPLIANCE,
    AGENT_ACTION,
    AGENT_HUMAN_REVIEW,
    AGENT_LEARNING,
    AGENT_MEMORY,
)


# ============================================================
# WORKFLOW ORDER
# ============================================================

WORKFLOW_AGENT_ORDER = (
    AGENT_DATA,
    AGENT_PREDICTION,
    AGENT_CAUSAL,
    AGENT_SIMULATION,
    AGENT_CODE_ANALYTICS,
    AGENT_COMPLIANCE,
    AGENT_HUMAN_REVIEW,
    AGENT_ACTION,
    AGENT_LEARNING,
    AGENT_MEMORY,
)


# ============================================================
# AGENT STATUS
# ============================================================

AGENT_STATUS_COMPLETED = (
    "COMPLETED"
)

AGENT_STATUS_SKIPPED = (
    "SKIPPED"
)

AGENT_STATUS_BLOCKED = (
    "BLOCKED"
)


VALID_AGENT_STATUSES = {
    AGENT_STATUS_COMPLETED,
    AGENT_STATUS_SKIPPED,
    AGENT_STATUS_BLOCKED,
}


# ============================================================
# WORKFLOW STATUS
# ============================================================

WORKFLOW_STATUS_COMPLETED = (
    "COMPLETED"
)

WORKFLOW_STATUS_BLOCKED = (
    "BLOCKED"
)

WORKFLOW_STATUS_ESCALATED = (
    "ESCALATED"
)


VALID_WORKFLOW_STATUSES = {
    WORKFLOW_STATUS_COMPLETED,
    WORKFLOW_STATUS_BLOCKED,
    WORKFLOW_STATUS_ESCALATED,
}


# ============================================================
# TRUST DECISIONS
# ============================================================

DECISION_APPROVED = (
    "APPROVED"
)

DECISION_MODIFIED = (
    "MODIFIED"
)

DECISION_REJECTED = (
    "REJECTED"
)

DECISION_ESCALATED = (
    "ESCALATED"
)


VALID_TRUST_DECISIONS = {
    DECISION_APPROVED,
    DECISION_MODIFIED,
    DECISION_REJECTED,
    DECISION_ESCALATED,
}


EXECUTABLE_DECISIONS = {
    DECISION_APPROVED,
    DECISION_MODIFIED,
}


# ============================================================
# ACTION STATUS
# ============================================================

ACTION_EXECUTED = (
    "EXECUTED"
)

ACTION_EXECUTED_WITH_GUARDRAILS = (
    "EXECUTED_WITH_GUARDRAILS"
)

ACTION_BLOCKED_BY_REJECTION = (
    "BLOCKED_BY_REJECTION"
)

ACTION_BLOCKED_PENDING_ESCALATION = (
    "BLOCKED_PENDING_ESCALATION"
)


# ============================================================
# OUTCOME
# ============================================================

OUTCOME_ACTION_EXECUTION_STATUS = (
    "ACTION_EXECUTION_STATUS"
)

OUTCOME_SCOPE_IMMEDIATE = (
    "IMMEDIATE_EXECUTION"
)


# ============================================================
# RISK PRIORITY
# ============================================================

RISK_PRIORITY = {
    "LOW":
        0.20,

    "MEDIUM":
        0.60,

    "HIGH":
        1.00,
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


TRUST_REQUIRED_COLUMNS = {
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


AUDIT_REQUIRED_COLUMNS = {
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


# ============================================================
# LEAKAGE
# ============================================================

FORBIDDEN_COLUMN_FRAGMENTS = (
    "ground_truth",
    "true_best",
    "true_outcome",
    "actual_future",
    "future_outcome",
    "oracle_",
)


FORBIDDEN_PAYLOAD_FRAGMENTS = (
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
    Convert to finite float.
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
    Convert to integer.
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
    Normalize boolean-like values.
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
    Clip numeric scalar to [0,1].
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
# JSON
# ============================================================


def _json_ready(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values to JSON-safe values.
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
    payload: Any,
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
            f"{record_id}: "
            f"{field_name} must contain a JSON object"
        )

    return payload


# ============================================================
# AGENT IDS
# ============================================================


def _agent_id(
    agent_name: str,
) -> str:
    """
    Build deterministic ID from configured agent name.
    """

    normalized = str(
        agent_name
    ).strip()

    normalized = re.sub(
        r"\s+Agent$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    normalized = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        normalized,
    )

    normalized = (
        normalized
        .strip(
            "_"
        )
        .upper()
    )

    return (
        "AGENT_"
        +
        normalized
    )


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
    Read synthetic generation window.
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


def _get_agent_config(
    generation: Mapping[str, Any],
) -> tuple[
    tuple[str, ...],
    int,
]:
    """
    Read:

        agents.definitions
        agents.workflow_runs.count
    """

    agents = generation.get(
        "agents"
    )

    if not isinstance(
        agents,
        Mapping,
    ):

        raise KeyError(
            "Missing generation.agents configuration"
        )

    definitions = agents.get(
        "definitions"
    )

    if not isinstance(
        definitions,
        list,
    ):

        raise KeyError(
            "Missing or invalid agents.definitions"
        )

    definitions_tuple = tuple(
        str(
            value
        )
        for value
        in definitions
    )

    missing_agents = (
        set(
            EXPECTED_AGENT_DEFINITIONS
        )
        -
        set(
            definitions_tuple
        )
    )

    if missing_agents:

        raise ValueError(
            "Live agent definitions are missing: "
            +
            ", ".join(
                sorted(
                    missing_agents
                )
            )
        )

    workflow_runs = agents.get(
        "workflow_runs"
    )

    if not isinstance(
        workflow_runs,
        Mapping,
    ):

        raise KeyError(
            "Missing agents.workflow_runs configuration"
        )

    count_value = workflow_runs.get(
        "count"
    )

    if count_value is None:

        raise KeyError(
            "Missing agents.workflow_runs.count"
        )

    count = int(
        count_value
    )

    if count <= 0:

        raise ValueError(
            "agents.workflow_runs.count must be > 0"
        )

    return (
        definitions_tuple,
        count,
    )


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
    Generic schema/PK validation.
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
            f"{name}.{primary_key} cannot contain null values"
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
    audit_events: pd.DataFrame,
) -> None:
    """
    Validate frozen Governance inputs.
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
        required=TRUST_REQUIRED_COLUMNS,
        primary_key="decision_id",
    )

    _require_columns(
        name="human_reviews",
        dataframe=human_reviews,
        required=HUMAN_REVIEW_REQUIRED_COLUMNS,
        primary_key="review_id",
        allow_empty=True,
    )

    _require_columns(
        name="audit_events",
        dataframe=audit_events,
        required=AUDIT_REQUIRED_COLUMNS,
        primary_key="audit_event_id",
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
            "Recommendation/trust-decision coverage mismatch"
        )

    if (
        trust_decisions[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Recommendation has multiple trust decisions"
        )

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
        VALID_TRUST_DECISIONS
    )

    if invalid_decisions:

        raise ValueError(
            "Unsupported trust decisions: "
            +
            ", ".join(
                sorted(
                    invalid_decisions
                )
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

    audit_recommendation_ids = set(
        audit_events[
            "recommendation_id"
        ]
        .astype(
            str
        )
    )

    if (
        recommendation_ids
        -
        audit_recommendation_ids
    ):

        raise ValueError(
            "Not every recommendation has audit lineage"
        )

    trust_audit = audit_events.loc[
        audit_events[
            "event_type"
        ]
        ==
        "TRUST_DECISION_RECORDED"
    ]

    if (
        set(
            trust_audit[
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
            "Every trust decision must have a "
            "TRUST_DECISION_RECORDED audit event"
        )


# ============================================================
# WORKFLOW SELECTION PRIORITY
# ============================================================


def _workflow_priority_score(
    decision: Mapping[str, Any],
) -> float:
    """
    Transparent workflow sampling priority.

    Used only to select which synthetic workflow records are
    retained when workflow count < recommendation count.

    It is not a business model score.
    """

    human_review = _to_bool(
        decision[
            "human_review_required"
        ]
    )

    final_decision = str(
        decision[
            "decision"
        ]
    ).upper()

    risk = str(
        decision[
            "recommendation_risk_level"
        ]
    ).upper()

    confidence = _clip01(
        _safe_float(
            decision[
                "recommendation_confidence"
            ]
        )
    )

    review_priority = _clip01(
        _safe_float(
            decision[
                "review_priority_score"
            ]
        )
    )

    non_approved_component = (
        1.0
        if final_decision
        != DECISION_APPROVED
        else 0.0
    )

    human_component = (
        1.0
        if human_review
        else 0.0
    )

    risk_component = (
        RISK_PRIORITY.get(
            risk,
            0.0,
        )
    )

    uncertainty_component = (
        1.0
        -
        confidence
    )

    return _clip01(
        0.40
        * human_component
        +
        0.25
        * non_approved_component
        +
        0.18
        * risk_component
        +
        0.10
        * review_priority
        +
        0.07
        * uncertainty_component
    )


# ============================================================
# DOMAIN QUOTAS
# ============================================================


def _allocate_domain_quotas(
    trust_decisions: pd.DataFrame,
    target_count: int,
) -> dict[str, int]:
    """
    Proportional largest-remainder domain allocation.
    """

    counts = (
        trust_decisions[
            "domain"
        ]
        .astype(
            str
        )
        .value_counts()
        .sort_index()
    )

    total = int(
        counts.sum()
    )

    raw = (
        counts
        /
        total
        *
        target_count
    )

    quotas = {
        str(
            domain
        ):
            int(
                np.floor(
                    value
                )
            )

        for domain,
        value
        in raw.items()
    }

    remaining = (
        target_count
        -
        sum(
            quotas.values()
        )
    )

    fractional = [
        (
            str(
                domain
            ),
            float(
                raw.loc[
                    domain
                ]
            )
            -
            quotas[
                str(
                    domain
                )
            ],
        )

        for domain
        in counts.index
    ]

    fractional.sort(
        key=lambda item: (
            -item[
                1
            ],
            item[
                0
            ],
        )
    )

    for domain, _ in (
        fractional[
            :remaining
        ]
    ):

        quotas[
            domain
        ] += 1

    if sum(
        quotas.values()
    ) != target_count:

        raise ValueError(
            "Workflow domain quota allocation failed"
        )

    return quotas


# ============================================================
# SELECT WORKFLOWS
# ============================================================


def _select_workflow_decisions(
    trust_decisions: pd.DataFrame,
    target_count: int,
) -> pd.DataFrame:
    """
    Select exact deterministic workflow population.

    Governance-significant records are mandatory when capacity
    allows:

        human-reviewed
        OR
        final decision != APPROVED
    """

    if target_count > len(
        trust_decisions
    ):

        raise ValueError(
            "Configured workflow count exceeds "
            "available trust decisions"
        )

    work = (
        trust_decisions
        .copy()
    )

    work[
        "_workflow_priority_score"
    ] = [
        _workflow_priority_score(
            row
        )

        for row
        in work.to_dict(
            orient="records"
        )
    ]

    significant_mask = (
        work[
            "human_review_required"
        ]
        .astype(
            bool
        )
        |
        (
            work[
                "decision"
            ]
            .astype(
                str
            )
            !=
            DECISION_APPROVED
        )
    )

    significant = (
        work.loc[
            significant_mask
        ]
        .copy()
    )

    if len(
        significant
    ) > target_count:

        raise ValueError(
            "Configured workflow capacity is too small "
            "to preserve every human-reviewed/non-approved "
            "governance decision"
        )

    selected_ids: set[str] = set(
        significant[
            "decision_id"
        ]
        .astype(
            str
        )
        .tolist()
    )

    quotas = _allocate_domain_quotas(
        trust_decisions=
            work,

        target_count=
            target_count,
    )

    # ========================================================
    # FILL EACH DOMAIN TOWARD TARGET QUOTA
    # ========================================================

    for domain, quota in (
        quotas.items()
    ):

        already_selected = int(
            (
                work[
                    "decision_id"
                ]
                .astype(
                    str
                )
                .isin(
                    selected_ids
                )
                &
                (
                    work[
                        "domain"
                    ]
                    .astype(
                        str
                    )
                    ==
                    domain
                )
            )
            .sum()
        )

        needed = max(
            0,
            quota
            -
            already_selected,
        )

        if needed == 0:
            continue

        candidates = (
            work.loc[
                (
                    work[
                        "domain"
                    ]
                    .astype(
                        str
                    )
                    ==
                    domain
                )
                &
                ~work[
                    "decision_id"
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
                    "_workflow_priority_score",
                    "review_priority_score",
                    "recommendation_confidence",
                    "decision_id",
                ],
                ascending=[
                    False,
                    False,
                    True,
                    True,
                ],
            )
        )

        selected_ids.update(
            candidates[
                "decision_id"
            ]
            .astype(
                str
            )
            .head(
                needed
            )
            .tolist()
        )

    # ========================================================
    # GLOBAL FILL IF NEEDED
    # ========================================================

    shortfall = (
        target_count
        -
        len(
            selected_ids
        )
    )

    if shortfall > 0:

        remaining = (
            work.loc[
                ~work[
                    "decision_id"
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
                    "_workflow_priority_score",
                    "review_priority_score",
                    "recommendation_confidence",
                    "domain",
                    "decision_id",
                ],
                ascending=[
                    False,
                    False,
                    True,
                    True,
                    True,
                ],
            )
        )

        selected_ids.update(
            remaining[
                "decision_id"
            ]
            .astype(
                str
            )
            .head(
                shortfall
            )
            .tolist()
        )

    if len(
        selected_ids
    ) != target_count:

        raise ValueError(
            "Workflow selection failed exact configured count"
        )

    selected = (
        work.loc[
            work[
                "decision_id"
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
                "domain",
                "_workflow_priority_score",
                "decision_id",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    return selected


# ============================================================
# TIMELINE
# ============================================================


def _split_interval(
    start: pd.Timestamp,
    end: pd.Timestamp,
    parts: int,
) -> list[
    tuple[
        pd.Timestamp,
        pd.Timestamp,
    ]
]:
    """
    Split interval into deterministic sequential slices.
    """

    if parts <= 0:

        raise ValueError(
            "parts must be > 0"
        )

    start_ts = pd.Timestamp(
        start
    )

    end_ts = pd.Timestamp(
        end
    )

    if end_ts <= start_ts:

        end_ts = (
            start_ts
            +
            pd.Timedelta(
                milliseconds=
                    100
                    *
                    parts
            )
        )

    total_seconds = float(
        (
            end_ts
            -
            start_ts
        )
        .total_seconds()
    )

    output = []

    for index in range(
        parts
    ):

        part_start = (
            start_ts
            +
            pd.Timedelta(
                seconds=
                    total_seconds
                    *
                    index
                    /
                    parts
            )
        )

        part_end = (
            start_ts
            +
            pd.Timedelta(
                seconds=
                    total_seconds
                    *
                    (
                        index
                        +
                        1
                    )
                    /
                    parts
            )
        )

        output.append(
            (
                part_start,
                part_end,
            )
        )

    return output


def _post_decision_timeline(
    decision_at: pd.Timestamp,
    generation_end: pd.Timestamp,
) -> dict[
    str,
    pd.Timestamp,
]:
    """
    Allocate Action → Learning → Memory timing after trust decision.
    """

    decision_ts = pd.Timestamp(
        decision_at
    )

    end_ts = pd.Timestamp(
        generation_end
    )

    remaining_seconds = float(
        (
            end_ts
            -
            decision_ts
        )
        .total_seconds()
    )

    if remaining_seconds <= 0.5:

        raise ValueError(
            "Trust decision leaves insufficient time "
            "for downstream workflow events"
        )

    usable = (
        remaining_seconds
        -
        0.05
    )

    return {
        "action_start":
            (
                decision_ts
                +
                pd.Timedelta(
                    seconds=
                        usable
                        *
                        0.12
                )
            ),

        "action_end":
            (
                decision_ts
                +
                pd.Timedelta(
                    seconds=
                        usable
                        *
                        0.42
                )
            ),

        "learning_start":
            (
                decision_ts
                +
                pd.Timedelta(
                    seconds=
                        usable
                        *
                        0.50
                )
            ),

        "learning_end":
            (
                decision_ts
                +
                pd.Timedelta(
                    seconds=
                        usable
                        *
                        0.72
                )
            ),

        "memory_time":
            (
                decision_ts
                +
                pd.Timedelta(
                    seconds=
                        usable
                        *
                        0.82
                )
            ),
    }


# ============================================================
# AGENT EVENT
# ============================================================


def _agent_event(
    agent_run_id: str,
    workflow_run_id: str,
    recommendation_id: str,
    decision_id: str,
    domain: str,
    event_sequence: int,
    agent_name: str,
    started_at: pd.Timestamp,
    completed_at: pd.Timestamp,
    status: str,
    input_refs: Mapping[str, Any],
    output_refs: Mapping[str, Any],
    human_feedback: str | None,
    data_origin: str,
    generator_version: str,
) -> dict[str, Any]:
    """
    Build runtime agent activity row.
    """

    if status not in (
        VALID_AGENT_STATUSES
    ):

        raise ValueError(
            f"Invalid agent status: {status}"
        )

    return {
        "agent_run_id":
            str(
                agent_run_id
            ),

        "workflow_run_id":
            str(
                workflow_run_id
            ),

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

        "event_sequence":
            int(
                event_sequence
            ),

        "agent_id":
            _agent_id(
                agent_name
            ),

        "agent_name":
            str(
                agent_name
            ),

        "started_at":
            pd.Timestamp(
                started_at
            ),

        "completed_at":
            pd.Timestamp(
                completed_at
            ),

        "status":
            str(
                status
            ),

        "input_refs":
            _canonical_json(
                input_refs
            ),

        "output_refs":
            _canonical_json(
                output_refs
            ),

        "human_feedback":
            (
                None
                if human_feedback is None
                else str(
                    human_feedback
                )
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
# MAIN GENERATOR
# ============================================================


def generate_workflow(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    audit_events: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate:

        agent_workflow_runs
        agent_events
        action_outcomes
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

        audit_events=
            audit_events,
    )

    (
        configured_agents,
        workflow_target_count,
    ) = _get_agent_config(
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
    # SELECT WORKFLOW POPULATION
    # ========================================================

    selected_decisions = (
        _select_workflow_decisions(
            trust_decisions=
                trust_decisions,

            target_count=
                workflow_target_count,
        )
    )

    # ========================================================
    # LOOKUPS
    # ========================================================

    recommendation_lookup = (
        recommendations
        .set_index(
            "recommendation_id"
        )
        .to_dict(
            orient="index"
        )
    )

    review_lookup = (
        human_reviews
        .set_index(
            "decision_id"
        )
        .to_dict(
            orient="index"
        )
        if not human_reviews.empty
        else {}
    )

    trust_audit = (
        audit_events.loc[
            audit_events[
                "event_type"
            ]
            ==
            "TRUST_DECISION_RECORDED"
        ]
    )

    trust_audit_lookup = (
        trust_audit
        .set_index(
            "decision_id"
        )
        .to_dict(
            orient="index"
        )
    )

    compliance_groups = {
        str(
            decision_id
        ):
            group.copy()

        for decision_id,
        group
        in compliance_checks.groupby(
            "decision_id",
            sort=False,
        )
    }

    # ========================================================
    # OUTPUT ROWS
    # ========================================================

    workflow_rows: list[
        dict[str, Any]
    ] = []

    agent_event_rows: list[
        dict[str, Any]
    ] = []

    action_outcome_rows: list[
        dict[str, Any]
    ] = []

    agent_run_sequence = 0
    action_sequence = 0

    # ========================================================
    # EACH SELECTED WORKFLOW
    # ========================================================

    for (
        workflow_sequence,
        decision,
    ) in enumerate(
        selected_decisions.to_dict(
            orient="records"
        ),
        start=1,
    ):

        workflow_run_id = (
            generate_id(
                "WFLOW_SYN",
                workflow_sequence,
                width=7,
            )
        )

        decision_id = str(
            decision[
                "decision_id"
            ]
        )

        recommendation_id = str(
            decision[
                "recommendation_id"
            ]
        )

        recommendation = (
            recommendation_lookup[
                recommendation_id
            ]
        )

        domain = str(
            decision[
                "domain"
            ]
        )

        final_decision = str(
            decision[
                "decision"
            ]
        ).upper()

        if (
            final_decision
            not in
            VALID_TRUST_DECISIONS
        ):

            raise ValueError(
                f"{decision_id}: unsupported trust decision"
            )

        human_review_required = (
            _to_bool(
                decision[
                    "human_review_required"
                ]
            )
        )

        recommendation_generated_at = pd.Timestamp(
            recommendation[
                "generated_at"
            ]
        )

        decision_at = pd.Timestamp(
            decision[
                "decided_at"
            ]
        )

        if (
            recommendation_generated_at.tzinfo
            is None
        ):

            raise ValueError(
                f"{recommendation_id}: generated_at "
                "must be timezone-aware"
            )

        if (
            decision_at.tzinfo
            is None
        ):

            raise ValueError(
                f"{decision_id}: decided_at "
                "must be timezone-aware"
            )

        checks = (
            compliance_groups[
                decision_id
            ]
            .sort_values(
                [
                    "checked_at",
                    "compliance_check_id",
                ]
            )
        )

        first_check_at = pd.to_datetime(
            checks[
                "checked_at"
            ],
            errors="raise",
            utc=True,
        ).min()

        last_check_at = pd.to_datetime(
            checks[
                "checked_at"
            ],
            errors="raise",
            utc=True,
        ).max()

        recommendation_generated_utc = (
            recommendation_generated_at
            .tz_convert(
                "UTC"
            )
        )

        decision_at_utc = (
            decision_at
            .tz_convert(
                "UTC"
            )
        )

        generation_end_utc = (
            generation_end
            .tz_convert(
                "UTC"
            )
        )

        # ====================================================
        # PRE-COMPLIANCE STAGES
        # ====================================================

        pre_intervals = _split_interval(
            start=
                recommendation_generated_utc,

            end=
                first_check_at,

            parts=
                5,
        )

        # ====================================================
        # HUMAN REVIEW SOURCE
        # ====================================================

        review = (
            review_lookup.get(
                decision_id
            )
        )

        if (
            human_review_required
            and
            review is None
        ):

            raise ValueError(
                f"{decision_id}: human review required "
                "but review record missing"
            )

        if (
            not human_review_required
            and
            review is not None
        ):

            raise ValueError(
                f"{decision_id}: unexpected human review"
            )

        # ====================================================
        # AUDIT SOURCE
        # ====================================================

        trust_audit_event = (
            trust_audit_lookup[
                decision_id
            ]
        )

        trust_audit_event_id = str(
            trust_audit_event[
                "audit_event_id"
            ]
        )

        # ====================================================
        # ACTION DECISION
        # ====================================================

        executable = (
            final_decision
            in
            EXECUTABLE_DECISIONS
        )

        action_id: str | None = None

        if final_decision == (
            DECISION_APPROVED
        ):

            action_status = (
                ACTION_EXECUTED
            )

            workflow_status = (
                WORKFLOW_STATUS_COMPLETED
            )

        elif final_decision == (
            DECISION_MODIFIED
        ):

            action_status = (
                ACTION_EXECUTED_WITH_GUARDRAILS
            )

            workflow_status = (
                WORKFLOW_STATUS_COMPLETED
            )

        elif final_decision == (
            DECISION_REJECTED
        ):

            action_status = (
                ACTION_BLOCKED_BY_REJECTION
            )

            workflow_status = (
                WORKFLOW_STATUS_BLOCKED
            )

        else:

            action_status = (
                ACTION_BLOCKED_PENDING_ESCALATION
            )

            workflow_status = (
                WORKFLOW_STATUS_ESCALATED
            )

        post_timeline = (
            _post_decision_timeline(
                decision_at=
                    decision_at_utc,

                generation_end=
                    generation_end_utc,
            )
        )

        # ====================================================
        # ACTION ID / OUTCOME
        # ====================================================

        if executable:

            action_sequence += 1

            action_id = generate_id(
                "ACTION_SYN",
                action_sequence,
                width=7,
            )

            action_outcome_rows.append(
                {
                    "action_id":
                        action_id,

                    "workflow_run_id":
                        workflow_run_id,

                    "recommendation_id":
                        recommendation_id,

                    "decision_id":
                        decision_id,

                    "domain":
                        domain,

                    "target_entity_type":
                        str(
                            decision[
                                "target_entity_type"
                            ]
                        ),

                    "target_entity_id":
                        str(
                            decision[
                                "target_entity_id"
                            ]
                        ),

                    "action_type":
                        str(
                            decision[
                                "recommendation_type"
                            ]
                        ),

                    "action_status":
                        action_status,

                    "outcome_type":
                        OUTCOME_ACTION_EXECUTION_STATUS,

                    "outcome_value":
                        action_status,

                    "outcome_scope":
                        OUTCOME_SCOPE_IMMEDIATE,

                    "business_outcome_observed":
                        False,

                    "business_outcome_note":
                        (
                            "Immediate execution evidence only; "
                            "workflow.py does not infer downstream "
                            "business impact."
                        ),

                    "observed_at":
                        post_timeline[
                            "action_end"
                        ],

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

        # ====================================================
        # HUMAN FEEDBACK
        # ====================================================

        human_feedback: str | None = None
        human_review_id: str | None = None

        if review is not None:

            human_review_id = str(
                review[
                    "review_id"
                ]
            )

            review_text = review.get(
                "free_text"
            )

            if not _is_missing(
                review_text
            ):

                human_feedback = str(
                    review_text
                )

        # ====================================================
        # DATA AGENT
        # ====================================================

        agent_run_sequence += 1

        evidence = _parse_json_object(
            value=
                recommendation[
                    "evidence_json"
                ],

            field_name=
                "recommendation.evidence_json",

            record_id=
                recommendation_id,
        )

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    1,

                agent_name=
                    AGENT_DATA,

                started_at=
                    pre_intervals[
                        0
                    ][
                        0
                    ],

                completed_at=
                    pre_intervals[
                        0
                    ][
                        1
                    ],

                status=
                    AGENT_STATUS_COMPLETED,

                input_refs={
                    "target_entity_type":
                        decision[
                            "target_entity_type"
                        ],

                    "target_entity_id":
                        decision[
                            "target_entity_id"
                        ],

                    "recommendation_id":
                        recommendation_id,
                },

                output_refs={
                    "evidence_source_record_type":
                        evidence.get(
                            "source_record_type"
                        ),

                    "evidence_source_record_id":
                        evidence.get(
                            "source_record_id"
                        ),

                    "recommendation_id":
                        recommendation_id,
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # PREDICTION AGENT
        # ====================================================

        agent_run_sequence += 1

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    2,

                agent_name=
                    AGENT_PREDICTION,

                started_at=
                    pre_intervals[
                        1
                    ][
                        0
                    ],

                completed_at=
                    pre_intervals[
                        1
                    ][
                        1
                    ],

                status=
                    AGENT_STATUS_SKIPPED,

                input_refs={
                    "recommendation_id":
                        recommendation_id,
                },

                output_refs={
                    "skip_reason":
                        "NO_LINKED_RUNTIME_PREDICTION_ARTIFACT",
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # CAUSAL GRAPH AGENT
        # ====================================================

        agent_run_sequence += 1

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    3,

                agent_name=
                    AGENT_CAUSAL,

                started_at=
                    pre_intervals[
                        2
                    ][
                        0
                    ],

                completed_at=
                    pre_intervals[
                        2
                    ][
                        1
                    ],

                status=
                    AGENT_STATUS_SKIPPED,

                input_refs={
                    "recommendation_id":
                        recommendation_id,
                },

                output_refs={
                    "skip_reason":
                        "NO_LINKED_RUNTIME_CAUSAL_ARTIFACT",
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # SIMULATION AGENT
        # ====================================================

        agent_run_sequence += 1

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    4,

                agent_name=
                    AGENT_SIMULATION,

                started_at=
                    pre_intervals[
                        3
                    ][
                        0
                    ],

                completed_at=
                    pre_intervals[
                        3
                    ][
                        1
                    ],

                status=
                    AGENT_STATUS_SKIPPED,

                input_refs={
                    "recommendation_id":
                        recommendation_id,
                },

                output_refs={
                    "skip_reason":
                        "NO_LINKED_RUNTIME_SIMULATION_ARTIFACT",
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # CODE ANALYTICS AGENT
        # ====================================================

        agent_run_sequence += 1

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    5,

                agent_name=
                    AGENT_CODE_ANALYTICS,

                started_at=
                    pre_intervals[
                        4
                    ][
                        0
                    ],

                completed_at=
                    pre_intervals[
                        4
                    ][
                        1
                    ],

                status=
                    AGENT_STATUS_SKIPPED,

                input_refs={
                    "recommendation_id":
                        recommendation_id,
                },

                output_refs={
                    "skip_reason":
                        "CODE_ANALYTICS_NOT_REQUIRED_FOR_GOVERNANCE_EXECUTION",
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # COMPLIANCE AGENT
        # ====================================================

        agent_run_sequence += 1

        compliance_check_ids = (
            checks[
                "compliance_check_id"
            ]
            .astype(
                str
            )
            .tolist()
        )

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    6,

                agent_name=
                    AGENT_COMPLIANCE,

                started_at=
                    first_check_at,

                completed_at=
                    last_check_at,

                status=
                    AGENT_STATUS_COMPLETED,

                input_refs={
                    "recommendation_id":
                        recommendation_id,

                    "decision_id":
                        decision_id,
                },

                output_refs={
                    "compliance_check_ids":
                        compliance_check_ids,

                    "checks_count":
                        len(
                            compliance_check_ids
                        ),

                    "pass_count":
                        _safe_int(
                            decision[
                                "compliance_pass_count"
                            ]
                        ),

                    "warn_count":
                        _safe_int(
                            decision[
                                "compliance_warn_count"
                            ]
                        ),

                    "fail_count":
                        _safe_int(
                            decision[
                                "compliance_fail_count"
                            ]
                        ),

                    "review_required_count":
                        _safe_int(
                            decision[
                                "compliance_review_required_count"
                            ]
                        ),
                },

                human_feedback=
                    None,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # HUMAN REVIEW AGENT
        # ====================================================

        agent_run_sequence += 1

        if review is not None:

            review_start = pd.Timestamp(
                review[
                    "requested_at"
                ]
            )

            review_end = pd.Timestamp(
                review[
                    "completed_at"
                ]
            )

            human_agent_status = (
                AGENT_STATUS_COMPLETED
            )

            human_input_refs = {
                "decision_id":
                    decision_id,

                "review_id":
                    human_review_id,

                "recommendation_id":
                    recommendation_id,
            }

            human_output_refs = {
                "review_id":
                    human_review_id,

                "review_decision":
                    review[
                        "decision"
                    ],

                "reason_code":
                    review[
                        "reason_code"
                    ],
            }

        else:

            gap_seconds = max(
                0.0,
                float(
                    (
                        decision_at_utc
                        -
                        last_check_at
                    )
                    .total_seconds()
                ),
            )

            review_start = (
                last_check_at
                +
                pd.Timedelta(
                    seconds=
                        gap_seconds
                        *
                        0.30
                )
            )

            review_end = (
                review_start
            )

            human_agent_status = (
                AGENT_STATUS_SKIPPED
            )

            human_input_refs = {
                "decision_id":
                    decision_id,
            }

            human_output_refs = {
                "skip_reason":
                    "NOT_ROUTED_TO_HUMAN_REVIEW",
            }

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    7,

                agent_name=
                    AGENT_HUMAN_REVIEW,

                started_at=
                    review_start,

                completed_at=
                    review_end,

                status=
                    human_agent_status,

                input_refs=
                    human_input_refs,

                output_refs=
                    human_output_refs,

                human_feedback=
                    human_feedback,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # ACTION AGENT
        # ====================================================

        agent_run_sequence += 1

        if executable:

            action_agent_status = (
                AGENT_STATUS_COMPLETED
            )

            action_output_refs = {
                "action_id":
                    action_id,

                "action_type":
                    decision[
                        "recommendation_type"
                    ],

                "action_status":
                    action_status,

                "business_outcome_observed":
                    False,
            }

        else:

            action_agent_status = (
                AGENT_STATUS_BLOCKED
            )

            action_output_refs = {
                "action_id":
                    None,

                "action_status":
                    action_status,

                "blocking_decision":
                    final_decision,
            }

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    8,

                agent_name=
                    AGENT_ACTION,

                started_at=
                    post_timeline[
                        "action_start"
                    ],

                completed_at=
                    post_timeline[
                        "action_end"
                    ],

                status=
                    action_agent_status,

                input_refs={
                    "recommendation_id":
                        recommendation_id,

                    "decision_id":
                        decision_id,

                    "trust_decision":
                        final_decision,

                    "trust_audit_event_id":
                        trust_audit_event_id,
                },

                output_refs=
                    action_output_refs,

                human_feedback=
                    human_feedback,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # LEARNING AGENT
        # ====================================================

        agent_run_sequence += 1

        if executable:

            learning_signal = (
                "ACTION_EXECUTION_FEEDBACK"
            )

            learning_input_refs = {
                "recommendation_id":
                    recommendation_id,

                "decision_id":
                    decision_id,

                "action_id":
                    action_id,

                "outcome_type":
                    OUTCOME_ACTION_EXECUTION_STATUS,

                "outcome_value":
                    action_status,
            }

        else:

            learning_signal = (
                "GOVERNANCE_DECISION_FEEDBACK"
            )

            learning_input_refs = {
                "recommendation_id":
                    recommendation_id,

                "decision_id":
                    decision_id,

                "decision":
                    final_decision,

                "human_review_id":
                    human_review_id,
            }

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    9,

                agent_name=
                    AGENT_LEARNING,

                started_at=
                    post_timeline[
                        "learning_start"
                    ],

                completed_at=
                    post_timeline[
                        "learning_end"
                    ],

                status=
                    AGENT_STATUS_COMPLETED,

                input_refs=
                    learning_input_refs,

                output_refs={
                    "learning_signal":
                        learning_signal,

                    "business_outcome_observed":
                        False,

                    "note":
                        (
                            "Governance/execution feedback captured; "
                            "no downstream business impact inferred."
                        ),
                },

                human_feedback=
                    human_feedback,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # MEMORY AGENT
        # ====================================================

        agent_run_sequence += 1

        agent_event_rows.append(
            _agent_event(
                agent_run_id=
                    generate_id(
                        "AGRUN_SYN",
                        agent_run_sequence,
                        width=8,
                    ),

                workflow_run_id=
                    workflow_run_id,

                recommendation_id=
                    recommendation_id,

                decision_id=
                    decision_id,

                domain=
                    domain,

                event_sequence=
                    10,

                agent_name=
                    AGENT_MEMORY,

                started_at=
                    post_timeline[
                        "memory_time"
                    ],

                completed_at=
                    post_timeline[
                        "memory_time"
                    ],

                status=
                    AGENT_STATUS_SKIPPED,

                input_refs={
                    "workflow_run_id":
                        workflow_run_id,

                    "decision_id":
                        decision_id,
                },

                output_refs={
                    "skip_reason":
                        "NO_PERSISTENT_AGENT_MEMORY_DATASET_IN_FACTORY",
                },

                human_feedback=
                    human_feedback,

                data_origin=
                    data_origin,

                generator_version=
                    generator_version,
            )
        )

        # ====================================================
        # WORKFLOW SUMMARY
        # ====================================================

        workflow_rows.append(
            {
                "workflow_run_id":
                    workflow_run_id,

                "recommendation_id":
                    recommendation_id,

                "decision_id":
                    decision_id,

                "domain":
                    domain,

                "use_case":
                    str(
                        decision[
                            "use_case"
                        ]
                    ),

                "target_entity_type":
                    str(
                        decision[
                            "target_entity_type"
                        ]
                    ),

                "target_entity_id":
                    str(
                        decision[
                            "target_entity_id"
                        ]
                    ),

                "recommendation_type":
                    str(
                        decision[
                            "recommendation_type"
                        ]
                    ),

                "trigger_type":
                    "GOVERNANCE_DECISION",

                "started_at":
                    recommendation_generated_utc,

                "completed_at":
                    post_timeline[
                        "memory_time"
                    ],

                "status":
                    workflow_status,

                "trust_decision":
                    final_decision,

                "decision_mode":
                    str(
                        decision[
                            "decision_mode"
                        ]
                    ),

                "human_review_required":
                    human_review_required,

                "human_review_id":
                    human_review_id,

                "action_id":
                    action_id,

                "action_status":
                    action_status,

                "agent_event_count":
                    len(
                        WORKFLOW_AGENT_ORDER
                    ),

                "workflow_priority_score":
                    round(
                        _safe_float(
                            decision[
                                "_workflow_priority_score"
                            ]
                        ),
                        6,
                    ),

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    # ========================================================
    # DATAFRAMES
    # ========================================================

    workflow_runs = pd.DataFrame(
        workflow_rows
    )

    agent_events = pd.DataFrame(
        agent_event_rows
    )

    action_outcomes = pd.DataFrame(
        action_outcome_rows
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_workflow(
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

        workflow_runs=
            workflow_runs,

        agent_events=
            agent_events,

        action_outcomes=
            action_outcomes,

        generation=
            generation,
    )

    return (
        workflow_runs,
        agent_events,
        action_outcomes,
    )


# ============================================================
# PUBLIC ALIAS
# ============================================================


def generate_agent_workflow_runs(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    audit_events: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Alias for later generate_all.py orchestration.
    """

    return generate_workflow(
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


# ============================================================
# PAYLOAD SCAN
# ============================================================


def _scan_payload_keys(
    value: Any,
    path: str = "",
) -> list[str]:
    """
    Detect hidden-truth payload leakage.
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
                FORBIDDEN_PAYLOAD_FRAGMENTS
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


def validate_workflow(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    human_reviews: pd.DataFrame,
    audit_events: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    agent_events: pd.DataFrame,
    action_outcomes: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate full agent workflow layer.
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

        audit_events=
            audit_events,
    )

    (
        configured_agents,
        expected_workflow_count,
    ) = _get_agent_config(
        generation
    )

    (
        generation_start,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    expected_agent_count = len(
        WORKFLOW_AGENT_ORDER
    )

    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    workflow_required = {
        "workflow_run_id",

        "recommendation_id",
        "decision_id",

        "domain",
        "use_case",

        "target_entity_type",
        "target_entity_id",

        "recommendation_type",

        "trigger_type",

        "started_at",
        "completed_at",

        "status",

        "trust_decision",
        "decision_mode",

        "human_review_required",
        "human_review_id",

        "action_id",
        "action_status",

        "agent_event_count",
        "workflow_priority_score",

        "data_origin",
        "generator_version",
    }

    event_required = {
        "agent_run_id",
        "workflow_run_id",

        "recommendation_id",
        "decision_id",
        "domain",

        "event_sequence",

        "agent_id",
        "agent_name",

        "started_at",
        "completed_at",

        "status",

        "input_refs",
        "output_refs",

        "human_feedback",

        "data_origin",
        "generator_version",
    }

    outcome_required = {
        "action_id",

        "workflow_run_id",

        "recommendation_id",
        "decision_id",

        "domain",

        "target_entity_type",
        "target_entity_id",

        "action_type",
        "action_status",

        "outcome_type",
        "outcome_value",
        "outcome_scope",

        "business_outcome_observed",
        "business_outcome_note",

        "observed_at",

        "data_origin",
        "generator_version",
    }

    missing_workflow = (
        workflow_required
        -
        set(
            workflow_runs.columns
        )
    )

    missing_events = (
        event_required
        -
        set(
            agent_events.columns
        )
    )

    missing_outcomes = (
        outcome_required
        -
        set(
            action_outcomes.columns
        )
    )

    if missing_workflow:

        raise ValueError(
            "Workflow runs missing columns: "
            +
            ", ".join(
                sorted(
                    missing_workflow
                )
            )
        )

    if missing_events:

        raise ValueError(
            "Agent events missing columns: "
            +
            ", ".join(
                sorted(
                    missing_events
                )
            )
        )

    if missing_outcomes:

        raise ValueError(
            "Action outcomes missing columns: "
            +
            ", ".join(
                sorted(
                    missing_outcomes
                )
            )
        )

    # ========================================================
    # EXACT WORKFLOW COUNT
    # ========================================================

    if len(
        workflow_runs
    ) != expected_workflow_count:

        raise ValueError(
            "Workflow count mismatch. "
            f"Expected={expected_workflow_count}, "
            f"actual={len(workflow_runs)}"
        )

    # ========================================================
    # PRIMARY KEYS
    # ========================================================

    for dataframe, column in (
        (
            workflow_runs,
            "workflow_run_id",
        ),
        (
            agent_events,
            "agent_run_id",
        ),
        (
            action_outcomes,
            "action_id",
        ),
    ):

        if dataframe.empty:

            if column == "action_id":
                continue

            raise ValueError(
                f"{column} dataset cannot be empty"
            )

        if (
            dataframe[
                column
            ]
            .isna()
            .any()
        ):

            raise ValueError(
                f"{column} cannot contain null values"
            )

        if (
            dataframe[
                column
            ]
            .duplicated()
            .any()
        ):

            raise ValueError(
                f"Duplicate {column} values found"
            )

    # ========================================================
    # ONE WORKFLOW PER RECOMMENDATION / DECISION
    # ========================================================

    if (
        workflow_runs[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Recommendation appears in multiple workflow runs"
        )

    if (
        workflow_runs[
            "decision_id"
        ]
        .duplicated()
        .any()
    ):

        raise ValueError(
            "Decision appears in multiple workflow runs"
        )

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

    if (
        set(
            workflow_runs[
                "recommendation_id"
            ]
            .astype(
                str
            )
        )
        -
        recommendation_ids
    ):

        raise ValueError(
            "Workflow references invalid recommendation"
        )

    if (
        set(
            workflow_runs[
                "decision_id"
            ]
            .astype(
                str
            )
        )
        -
        decision_ids
    ):

        raise ValueError(
            "Workflow references invalid trust decision"
        )

    # ========================================================
    # GOVERNANCE-SIGNIFICANT DECISIONS PRESERVED
    # ========================================================

    mandatory_decisions = set(
        trust_decisions.loc[
            trust_decisions[
                "human_review_required"
            ]
            .astype(
                bool
            )
            |
            (
                trust_decisions[
                    "decision"
                ]
                .astype(
                    str
                )
                !=
                DECISION_APPROVED
            ),
            "decision_id",
        ]
        .astype(
            str
        )
    )

    workflow_decision_ids = set(
        workflow_runs[
            "decision_id"
        ]
        .astype(
            str
        )
    )

    missing_mandatory = (
        mandatory_decisions
        -
        workflow_decision_ids
    )

    if missing_mandatory:

        raise ValueError(
            "Governance-significant decisions missing "
            "from workflow population"
        )

    # ========================================================
    # WORKFLOW STATUS
    # ========================================================

    invalid_workflow_status = (
        set(
            workflow_runs[
                "status"
            ]
            .astype(
                str
            )
        )
        -
        VALID_WORKFLOW_STATUSES
    )

    if invalid_workflow_status:

        raise ValueError(
            "Invalid workflow status found"
        )

    # ========================================================
    # EXACT AGENT EVENTS
    # ========================================================

    expected_event_rows = (
        expected_workflow_count
        *
        expected_agent_count
    )

    if len(
        agent_events
    ) != expected_event_rows:

        raise ValueError(
            "Agent-event count mismatch. "
            f"Expected={expected_event_rows}, "
            f"actual={len(agent_events)}"
        )

    events_per_workflow = (
        agent_events
        .groupby(
            "workflow_run_id"
        )
        .size()
    )

    if not (
        events_per_workflow
        ==
        expected_agent_count
    ).all():

        raise ValueError(
            "Every workflow must contain exactly "
            f"{expected_agent_count} agent events"
        )

    # ========================================================
    # AGENT ENUM / IDS
    # ========================================================

    invalid_agent_names = (
        set(
            agent_events[
                "agent_name"
            ]
            .astype(
                str
            )
        )
        -
        set(
            configured_agents
        )
    )

    if invalid_agent_names:

        raise ValueError(
            "Agent events contain unconfigured agents"
        )

    for agent_name in (
        WORKFLOW_AGENT_ORDER
    ):

        expected_id = _agent_id(
            agent_name
        )

        rows = agent_events.loc[
            agent_events[
                "agent_name"
            ]
            ==
            agent_name
        ]

        if rows.empty:

            raise ValueError(
                f"No runtime events generated for {agent_name}"
            )

        if not (
            rows[
                "agent_id"
            ]
            ==
            expected_id
        ).all():

            raise ValueError(
                f"{agent_name}: agent_id mismatch"
            )

    invalid_agent_status = (
        set(
            agent_events[
                "status"
            ]
            .astype(
                str
            )
        )
        -
        VALID_AGENT_STATUSES
    )

    if invalid_agent_status:

        raise ValueError(
            "Invalid agent status found"
        )

    # ========================================================
    # EXACT STAGE ORDER
    # ========================================================

    for (
        workflow_run_id,
        group,
    ) in agent_events.groupby(
        "workflow_run_id",
        sort=True,
    ):

        ordered = (
            group
            .sort_values(
                "event_sequence"
            )
        )

        actual_sequence = (
            ordered[
                "event_sequence"
            ]
            .astype(
                int
            )
            .tolist()
        )

        expected_sequence = list(
            range(
                1,
                expected_agent_count
                +
                1,
            )
        )

        if (
            actual_sequence
            !=
            expected_sequence
        ):

            raise ValueError(
                f"{workflow_run_id}: invalid event sequence"
            )

        actual_agents = (
            ordered[
                "agent_name"
            ]
            .astype(
                str
            )
            .tolist()
        )

        if (
            actual_agents
            !=
            list(
                WORKFLOW_AGENT_ORDER
            )
        ):

            raise ValueError(
                f"{workflow_run_id}: invalid agent stage order"
            )

    # ========================================================
    # JSON REF VALIDATION
    # ========================================================

    for event in agent_events.itertuples(
        index=False
    ):

        try:

            input_refs = json.loads(
                event.input_refs
            )

            output_refs = json.loads(
                event.output_refs
            )

        except json.JSONDecodeError as exc:

            raise ValueError(
                f"{event.agent_run_id}: invalid refs JSON"
            ) from exc

        if not isinstance(
            input_refs,
            dict,
        ):

            raise ValueError(
                f"{event.agent_run_id}: input_refs must be object"
            )

        if not isinstance(
            output_refs,
            dict,
        ):

            raise ValueError(
                f"{event.agent_run_id}: output_refs must be object"
            )

        violations = (
            _scan_payload_keys(
                input_refs,
                "input_refs",
            )
            +
            _scan_payload_keys(
                output_refs,
                "output_refs",
            )
        )

        if violations:

            raise ValueError(
                f"{event.agent_run_id}: "
                "hidden truth leaked into agent refs"
            )

    # ========================================================
    # WORKFLOW / EVENT FK
    # ========================================================

    workflow_ids = set(
        workflow_runs[
            "workflow_run_id"
        ]
        .astype(
            str
        )
    )

    invalid_event_workflows = (
        set(
            agent_events[
                "workflow_run_id"
            ]
            .astype(
                str
            )
        )
        -
        workflow_ids
    )

    if invalid_event_workflows:

        raise ValueError(
            "Agent events reference invalid workflows"
        )

    # ========================================================
    # HUMAN REVIEW AGENT CONSISTENCY
    # ========================================================

    workflow_lookup = (
        workflow_runs
        .set_index(
            "workflow_run_id"
        )
    )

    human_agent_rows = (
        agent_events.loc[
            agent_events[
                "agent_name"
            ]
            ==
            AGENT_HUMAN_REVIEW
        ]
    )

    for row in human_agent_rows.itertuples(
        index=False
    ):

        workflow = workflow_lookup.loc[
            str(
                row.workflow_run_id
            )
        ]

        review_required = _to_bool(
            workflow[
                "human_review_required"
            ]
        )

        if review_required:

            if (
                row.status
                !=
                AGENT_STATUS_COMPLETED
            ):

                raise ValueError(
                    f"{row.workflow_run_id}: "
                    "human-review agent must complete"
                )

        else:

            if (
                row.status
                !=
                AGENT_STATUS_SKIPPED
            ):

                raise ValueError(
                    f"{row.workflow_run_id}: "
                    "human-review agent should be skipped"
                )

    # ========================================================
    # ACTION AGENT / TRUST DECISION CONSISTENCY
    # ========================================================

    action_agent_rows = (
        agent_events.loc[
            agent_events[
                "agent_name"
            ]
            ==
            AGENT_ACTION
        ]
    )

    trust_lookup = (
        trust_decisions
        .set_index(
            "decision_id"
        )
    )

    executable_workflow_ids: set[str] = set()

    for row in action_agent_rows.itertuples(
        index=False
    ):

        trust_row = trust_lookup.loc[
            str(
                row.decision_id
            )
        ]

        final_decision = str(
            trust_row[
                "decision"
            ]
        )

        if (
            final_decision
            in
            EXECUTABLE_DECISIONS
        ):

            executable_workflow_ids.add(
                str(
                    row.workflow_run_id
                )
            )

            if (
                row.status
                !=
                AGENT_STATUS_COMPLETED
            ):

                raise ValueError(
                    f"{row.workflow_run_id}: executable "
                    "decision has blocked Action Agent"
                )

        else:

            if (
                row.status
                !=
                AGENT_STATUS_BLOCKED
            ):

                raise ValueError(
                    f"{row.workflow_run_id}: rejected/escalated "
                    "decision executed Action Agent"
                )

    # ========================================================
    # ACTION OUTCOME COVERAGE
    # ========================================================

    outcome_workflow_ids = set(
        action_outcomes[
            "workflow_run_id"
        ]
        .astype(
            str
        )
    )

    if (
        outcome_workflow_ids
        !=
        executable_workflow_ids
    ):

        raise ValueError(
            "Action outcomes must exist exactly for "
            "executable selected workflows"
        )

    if not action_outcomes.empty:

        if not (
            action_outcomes[
                "outcome_type"
            ]
            ==
            OUTCOME_ACTION_EXECUTION_STATUS
        ).all():

            raise ValueError(
                "workflow.py may create only immediate "
                "execution outcomes"
            )

        if not (
            action_outcomes[
                "outcome_scope"
            ]
            ==
            OUTCOME_SCOPE_IMMEDIATE
        ).all():

            raise ValueError(
                "Unexpected action outcome scope"
            )

        if (
            action_outcomes[
                "business_outcome_observed"
            ]
            .astype(
                bool
            )
            .any()
        ):

            raise ValueError(
                "workflow.py must not fabricate downstream "
                "business outcomes"
            )

        invalid_action_recommendations = (
            set(
                action_outcomes[
                    "recommendation_id"
                ]
                .astype(
                    str
                )
            )
            -
            recommendation_ids
        )

        if invalid_action_recommendations:

            raise ValueError(
                "Action outcome references invalid recommendation"
            )

        invalid_action_decisions = (
            set(
                action_outcomes[
                    "decision_id"
                ]
                .astype(
                    str
                )
            )
            -
            decision_ids
        )

        if invalid_action_decisions:

            raise ValueError(
                "Action outcome references invalid decision"
            )

    # ========================================================
    # TIMESTAMPS
    # ========================================================

    workflow_start = pd.to_datetime(
        workflow_runs[
            "started_at"
        ],
        errors="raise",
        utc=True,
    )

    workflow_end = pd.to_datetime(
        workflow_runs[
            "completed_at"
        ],
        errors="raise",
        utc=True,
    )

    event_start = pd.to_datetime(
        agent_events[
            "started_at"
        ],
        errors="raise",
        utc=True,
    )

    event_end = pd.to_datetime(
        agent_events[
            "completed_at"
        ],
        errors="raise",
        utc=True,
    )

    generation_start_utc = (
        generation_start
        .tz_convert(
            "UTC"
        )
    )

    generation_end_utc = (
        generation_end
        .tz_convert(
            "UTC"
        )
    )

    if (
        workflow_end
        <
        workflow_start
    ).any():

        raise ValueError(
            "Workflow completed before it started"
        )

    if (
        event_end
        <
        event_start
    ).any():

        raise ValueError(
            "Agent event completed before it started"
        )

    if (
        workflow_start
        <
        generation_start_utc
    ).any():

        raise ValueError(
            "Workflow starts outside generation window"
        )

    if (
        workflow_end
        >=
        generation_end_utc
    ).any():

        raise ValueError(
            "Workflow completes outside generation window"
        )

    if (
        event_start
        <
        generation_start_utc
    ).any():

        raise ValueError(
            "Agent event starts outside generation window"
        )

    if (
        event_end
        >=
        generation_end_utc
    ).any():

        raise ValueError(
            "Agent event completes outside generation window"
        )

    if not action_outcomes.empty:

        observed_at = pd.to_datetime(
            action_outcomes[
                "observed_at"
            ],
            errors="raise",
            utc=True,
        )

        if (
            observed_at
            >=
            generation_end_utc
        ).any():

            raise ValueError(
                "Action outcome occurs outside generation window"
            )

    # ========================================================
    # EVENT WITHIN WORKFLOW
    # ========================================================

    workflow_time_lookup = (
        workflow_runs
        .assign(
            _start_utc=
                pd.to_datetime(
                    workflow_runs[
                        "started_at"
                    ],
                    utc=True,
                ),

            _end_utc=
                pd.to_datetime(
                    workflow_runs[
                        "completed_at"
                    ],
                    utc=True,
                ),
        )
        .set_index(
            "workflow_run_id"
        )
    )

    for event in agent_events.itertuples(
        index=False
    ):

        workflow = workflow_time_lookup.loc[
            str(
                event.workflow_run_id
            )
        ]

        start = pd.Timestamp(
            event.started_at
        ).tz_convert(
            "UTC"
        )

        end = pd.Timestamp(
            event.completed_at
        ).tz_convert(
            "UTC"
        )

        if (
            start
            <
            workflow[
                "_start_utc"
            ]
            or
            end
            >
            workflow[
                "_end_utc"
            ]
        ):

            raise ValueError(
                f"{event.agent_run_id}: agent event "
                "outside workflow interval"
            )

    # ========================================================
    # ACTION AFTER TRUST DECISION
    # ========================================================

    if not action_outcomes.empty:

        trust_decision_time = (
            trust_decisions
            .assign(
                _decided_at_utc=
                    pd.to_datetime(
                        trust_decisions[
                            "decided_at"
                        ],
                        errors="raise",
                        utc=True,
                    )
            )
            .set_index(
                "decision_id"
            )[
                "_decided_at_utc"
            ]
        )

        for outcome in action_outcomes.itertuples(
            index=False
        ):

            if (
                pd.Timestamp(
                    outcome.observed_at
                )
                .tz_convert(
                    "UTC"
                )
                <=
                trust_decision_time.loc[
                    str(
                        outcome.decision_id
                    )
                ]
            ):

                raise ValueError(
                    f"{outcome.action_id}: action outcome "
                    "must occur after trust decision"
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
            "workflow_runs",
            workflow_runs,
        ),
        (
            "agent_events",
            agent_events,
        ),
        (
            "action_outcomes",
            action_outcomes,
        ),
    ):

        if dataframe.empty:
            continue

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
    # COLUMN LEAKAGE
    # ========================================================

    for name, dataframe in (
        (
            "workflow_runs",
            workflow_runs,
        ),
        (
            "agent_events",
            agent_events,
        ),
        (
            "action_outcomes",
            action_outcomes,
        ),
    ):

        leakage = [
            column

            for column
            in dataframe.columns

            if any(
                fragment
                in column.lower()

                for fragment
                in FORBIDDEN_COLUMN_FRAGMENTS
            )
        ]

        if leakage:

            raise ValueError(
                f"{name}: hidden truth/runtime leakage: "
                +
                ", ".join(
                    leakage
                )
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

    from data.generators.governance.audit import (
        generate_audit_events,
    )

    generation_config = (
        load_generation_config()
    )

    (
        configured_agents,
        configured_workflow_count,
    ) = _get_agent_config(
        generation_config
    )

    # ========================================================
    # GOVERNANCE FIXTURE
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

    print(
        "\n=== AGENT WORKFLOW CONFIG ===\n"
    )

    print(
        "Configured agent definitions:",
        len(
            configured_agents
        ),
    )

    for agent in configured_agents:

        print(
            " -",
            agent,
        )

    print(
        "\nConfigured workflow runs:",
        configured_workflow_count,
    )

    print(
        "\n=== UPSTREAM GOVERNANCE ===\n"
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
        "Audit events:",
        len(
            audit_events_df
        ),
    )

    # ========================================================
    # GENERATE
    # ========================================================

    (
        workflow_runs_df,
        agent_events_df,
        action_outcomes_df,
    ) = generate_workflow(
        recommendations=
            recommendations_df,

        compliance_checks=
            compliance_checks_df,

        trust_decisions=
            trust_decisions_df,

        human_reviews=
            human_reviews_df,

        audit_events=
            audit_events_df,

        generation=
            generation_config,
    )

    # ========================================================
    # DETERMINISM
    # ========================================================

    (
        workflow_runs_repeat_df,
        agent_events_repeat_df,
        action_outcomes_repeat_df,
    ) = generate_workflow(
        recommendations=
            recommendations_df,

        compliance_checks=
            compliance_checks_df,

        trust_decisions=
            trust_decisions_df,

        human_reviews=
            human_reviews_df,

        audit_events=
            audit_events_df,

        generation=
            generation_config,
    )

    pd.testing.assert_frame_equal(
        workflow_runs_df,
        workflow_runs_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        agent_events_df,
        agent_events_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        action_outcomes_df,
        action_outcomes_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    # ========================================================
    # WORKFLOW SAMPLE
    # ========================================================

    print(
        "\n=== WORKFLOW SAMPLE ===\n"
    )

    print(
        workflow_runs_df[
            [
                "workflow_run_id",
                "recommendation_id",
                "decision_id",
                "domain",
                "trust_decision",
                "decision_mode",
                "human_review_required",
                "status",
                "action_id",
                "action_status",
            ]
        ]
        .head(
            40
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # WORKFLOW STATUS
    # ========================================================

    print(
        "\n=== WORKFLOW STATUS MIX ===\n"
    )

    print(
        workflow_runs_df
        .groupby(
            "status",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "workflows"
            }
        )
        .sort_values(
            "status"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SELECTED TRUST DECISION MIX
    # ========================================================

    print(
        "\n=== SELECTED TRUST DECISION MIX ===\n"
    )

    print(
        workflow_runs_df
        .groupby(
            "trust_decision",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "workflows"
            }
        )
        .sort_values(
            "trust_decision"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # WORKFLOWS BY DOMAIN
    # ========================================================

    print(
        "\n=== WORKFLOWS BY DOMAIN ===\n"
    )

    print(
        workflow_runs_df
        .groupby(
            "domain",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "workflows"
            }
        )
        .sort_values(
            "domain"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # AGENT STATUS MIX
    #
    # FIXED:
    #
    # The grouped DataFrame no longer contains event_sequence.
    # Therefore we use an explicit lookup based on
    # WORKFLOW_AGENT_ORDER for reporting order.
    # ========================================================

    print(
        "\n=== AGENT STATUS MIX ===\n"
    )

    agent_status_mix = (
        agent_events_df
        .groupby(
            [
                "agent_name",
                "status",
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
    )

    agent_order_lookup = {
        agent_name:
            index

        for index, agent_name
        in enumerate(
            WORKFLOW_AGENT_ORDER,
            start=1,
        )
    }

    agent_status_mix[
        "_agent_order"
    ] = (
        agent_status_mix[
            "agent_name"
        ]
        .map(
            agent_order_lookup
        )
    )

    agent_status_mix = (
        agent_status_mix
        .sort_values(
            [
                "_agent_order",
                "status",
            ]
        )
        .drop(
            columns=[
                "_agent_order",
            ]
        )
    )

    print(
        agent_status_mix.to_string(
            index=False
        )
    )

    # ========================================================
    # HUMAN REVIEW COVERAGE
    # ========================================================

    selected_human_review_count = int(
        workflow_runs_df[
            "human_review_required"
        ]
        .astype(
            bool
        )
        .sum()
    )

    # ========================================================
    # ACTION OUTCOMES
    # ========================================================

    print(
        "\n=== ACTION OUTCOME MIX ===\n"
    )

    if action_outcomes_df.empty:

        print(
            "No executable action outcomes generated."
        )

    else:

        print(
            action_outcomes_df
            .groupby(
                [
                    "action_status",
                    "outcome_value",
                ],
                as_index=False,
            )
            .size()
            .rename(
                columns={
                    "size":
                        "outcomes"
                }
            )
            .sort_values(
                "action_status"
            )
            .to_string(
                index=False
            )
        )

    # ========================================================
    # BUSINESS OUTCOME GUARD
    # ========================================================

    observed_business_outcomes = int(
        action_outcomes_df[
            "business_outcome_observed"
        ]
        .astype(
            bool
        )
        .sum()
    )

    # ========================================================
    # SKIPPED INTELLIGENCE STAGES
    # ========================================================

    intelligence_agents = [
        AGENT_PREDICTION,
        AGENT_CAUSAL,
        AGENT_SIMULATION,
        AGENT_CODE_ANALYTICS,
    ]

    skipped_intelligence_events = int(
        (
            agent_events_df[
                "agent_name"
            ]
            .isin(
                intelligence_agents
            )
            &
            (
                agent_events_df[
                    "status"
                ]
                ==
                AGENT_STATUS_SKIPPED
            )
        )
        .sum()
    )

    # ========================================================
    # LEAKAGE SUMMARY
    # ========================================================

    leakage = {}

    for name, dataframe in (
        (
            "workflow_runs",
            workflow_runs_df,
        ),
        (
            "agent_events",
            agent_events_df,
        ),
        (
            "action_outcomes",
            action_outcomes_df,
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
                in FORBIDDEN_COLUMN_FRAGMENTS
            )
        ]

    # ========================================================
    # FINAL VALIDATION SUMMARY
    # ========================================================

    print(
        "\n=== AGENT WORKFLOW VALIDATION ===\n"
    )

    print(
        "Workflow rows:",
        len(
            workflow_runs_df
        ),
    )

    print(
        "Unique workflow IDs:",
        workflow_runs_df[
            "workflow_run_id"
        ]
        .nunique(),
    )

    print(
        "Recommendations represented:",
        workflow_runs_df[
            "recommendation_id"
        ]
        .nunique(),
    )

    print(
        "Trust decisions represented:",
        workflow_runs_df[
            "decision_id"
        ]
        .nunique(),
    )

    print(
        "Agent event rows:",
        len(
            agent_events_df
        ),
    )

    print(
        "Unique agent-run IDs:",
        agent_events_df[
            "agent_run_id"
        ]
        .nunique(),
    )

    print(
        "Agent events per workflow:",
        int(
            len(
                agent_events_df
            )
            /
            len(
                workflow_runs_df
            )
        ),
    )

    print(
        "Configured agents represented:",
        agent_events_df[
            "agent_name"
        ]
        .nunique(),
    )

    print(
        "Selected human reviews:",
        selected_human_review_count,
    )

    print(
        "Available human reviews:",
        len(
            human_reviews_df
        ),
    )

    print(
        "Action outcome rows:",
        len(
            action_outcomes_df
        ),
    )

    print(
        "Business outcomes fabricated:",
        observed_business_outcomes,
    )

    print(
        "Skipped unsupported intelligence stages:",
        skipped_intelligence_events,
    )

    print(
        "Duplicate workflow IDs:",
        int(
            workflow_runs_df[
                "workflow_run_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate agent-run IDs:",
        int(
            agent_events_df[
                "agent_run_id"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "Duplicate action IDs:",
        int(
            action_outcomes_df[
                "action_id"
            ]
            .duplicated()
            .sum()
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
        f"{len(workflow_runs_df)} workflow runs, "
        f"{len(agent_events_df)} agent events and "
        f"{len(action_outcomes_df)} immediate action outcomes "
        "successfully."
    )