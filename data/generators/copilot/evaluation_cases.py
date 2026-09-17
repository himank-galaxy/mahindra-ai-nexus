"""
Synthetic Analytics Copilot evaluation-case generator
for Mahindra AI Nexus.

============================================================
PURPOSE
============================================================

Generate a deterministic Copilot evaluation suite grounded in
the Synthetic Data Factory.

Outputs:

    1. suggested_prompts
    2. copilot_eval_questions
    3. copilot_eval_ground_truth


============================================================
CRITICAL SEPARATION
============================================================

copilot_eval_questions
    -> evaluation/runtime input

copilot_eval_ground_truth
    -> evaluator-only
    -> MUST NOT be read by runtime Copilot

The runtime Copilot must independently query operational/runtime
data and produce an answer.

Evaluation compares that answer to hidden expected truth.


============================================================
LIVE CONFIGURATION
============================================================

generation["copilot"]:

    evaluation_questions:
        count: 100

    supported_domains:
        auto
        dealer
        manufacturing
        warranty
        finance
        collections
        logistics
        circularity
        compliance
        simulation


============================================================
SPLITS
============================================================

generation["splits"]["entity_data"]:

    train       0.70
    validation  0.15
    test        0.15


============================================================
EVALUATION PHILOSOPHY
============================================================

Cases evaluate:

    grounded aggregation
    entity identification
    status interpretation
    lineage
    governance reasoning
    anti-hallucination
    causal restraint
    simulation restraint
    business-outcome restraint

A Copilot must not fabricate:

    causal edges
    simulations
    model outputs
    revenue uplift
    downstream business impact
    unsupported approvals


============================================================
NO CSV WRITES
============================================================

This generator returns DataFrames only.

Export is handled later by scripts/export_csv.py.
"""

from __future__ import annotations

import json
from collections import Counter
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
# DOMAINS
# ============================================================

DOMAIN_AUTO = "auto"
DOMAIN_DEALER = "dealer"
DOMAIN_MANUFACTURING = "manufacturing"
DOMAIN_WARRANTY = "warranty"
DOMAIN_FINANCE = "finance"
DOMAIN_COLLECTIONS = "collections"
DOMAIN_LOGISTICS = "logistics"
DOMAIN_CIRCULARITY = "circularity"
DOMAIN_COMPLIANCE = "compliance"
DOMAIN_SIMULATION = "simulation"


EXPECTED_SUPPORTED_DOMAINS = (
    DOMAIN_AUTO,
    DOMAIN_DEALER,
    DOMAIN_MANUFACTURING,
    DOMAIN_WARRANTY,
    DOMAIN_FINANCE,
    DOMAIN_COLLECTIONS,
    DOMAIN_LOGISTICS,
    DOMAIN_CIRCULARITY,
    DOMAIN_COMPLIANCE,
    DOMAIN_SIMULATION,
)


# ============================================================
# GOVERNANCE DOMAIN MAP
# ============================================================

GOVERNANCE_DOMAIN_MAP = {
    DOMAIN_AUTO: "AUTO",
    DOMAIN_FINANCE: "FINANCE",
    DOMAIN_COLLECTIONS: "COLLECTIONS",
    DOMAIN_LOGISTICS: "LOGISTICS",
    DOMAIN_CIRCULARITY: "CIRCULARITY",
}


# ============================================================
# SPLITS
# ============================================================

SPLIT_TRAIN = "TRAIN"
SPLIT_VALIDATION = "VALIDATION"
SPLIT_TEST = "TEST"


VALID_SPLITS = {
    SPLIT_TRAIN,
    SPLIT_VALIDATION,
    SPLIT_TEST,
}


# ============================================================
# TASK TYPES
# ============================================================

TASK_AGGREGATION = "AGGREGATION"
TASK_ENTITY_RANKING = "ENTITY_RANKING"
TASK_LINEAGE = "LINEAGE"
TASK_GOVERNANCE = "GOVERNANCE_REASONING"
TASK_ANTI_HALLUCINATION = "ANTI_HALLUCINATION"
TASK_CAUSAL_RESTRAINT = "CAUSAL_RESTRAINT"
TASK_SIMULATION_RESTRAINT = "SIMULATION_RESTRAINT"
TASK_SOURCE_ROUTING = "SOURCE_ROUTING"


# ============================================================
# RESPONSE TYPES
# ============================================================

RESPONSE_NUMBER = "NUMBER"
RESPONSE_ENTITY = "ENTITY"
RESPONSE_ENTITY_AND_METRIC = "ENTITY_AND_METRIC"
RESPONSE_BOOLEAN = "BOOLEAN"
RESPONSE_STRUCTURED = "STRUCTURED"
RESPONSE_ABSTENTION = "ABSTENTION"


# ============================================================
# DIFFICULTY
# ============================================================

DIFFICULTY_EASY = "EASY"
DIFFICULTY_MEDIUM = "MEDIUM"
DIFFICULTY_HARD = "HARD"


# ============================================================
# REQUIRED INPUT SCHEMAS
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
    "human_review_required",
    "human_review_id",
    "review_priority_score",
    "decision_reason_code",
    "data_origin",
    "generator_version",
}


AUDIT_REQUIRED_COLUMNS = {
    "audit_event_id",
    "recommendation_id",
    "decision_id",
    "domain",
    "event_type",
    "event_at",
    "source_record_type",
    "source_record_id",
    "event_hash",
    "data_origin",
    "generator_version",
}


WORKFLOW_REQUIRED_COLUMNS = {
    "workflow_run_id",
    "recommendation_id",
    "decision_id",
    "domain",
    "status",
    "trust_decision",
    "human_review_required",
    "action_id",
    "action_status",
    "data_origin",
    "generator_version",
}


AGENT_EVENT_REQUIRED_COLUMNS = {
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
    "data_origin",
    "generator_version",
}


ACTION_OUTCOME_REQUIRED_COLUMNS = {
    "action_id",
    "workflow_run_id",
    "recommendation_id",
    "decision_id",
    "domain",
    "action_type",
    "action_status",
    "outcome_type",
    "outcome_value",
    "business_outcome_observed",
    "observed_at",
    "data_origin",
    "generator_version",
}


MANUFACTURING_REQUIRED_COLUMNS = {
    "timestamp",
    "plant_id",
    "production_line_id",
    "machine_id",
}


# ============================================================
# UPDATED:
# REAL FROZEN WARRANTY SCHEMA
# ============================================================

WARRANTY_REQUIRED_COLUMNS = {
    "warranty_claim_id",
    "production_batch_id",
    "primary_supplier_lot_id",
    "claim_amount_inr",
    "approved_amount_inr",
    "claim_status",
}


# ============================================================
# RUNTIME GROUND-TRUTH LEAKAGE
# ============================================================

FORBIDDEN_RUNTIME_COLUMN_FRAGMENTS = (
    "ground_truth",
    "expected_answer",
    "must_include",
    "must_not_invent",
    "oracle",
    "true_outcome",
    "true_best",
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
    Convert value to finite float.
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
    Convert value to integer.
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


# ============================================================
# JSON HELPERS
# ============================================================


def _json_ready(
    value: Any,
) -> Any:
    """
    Convert pandas/numpy values into deterministic JSON-safe data.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(
                key
            ): _json_ready(
                nested
            )
            for key, nested
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
                nested
            )
            for nested
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
    value: Any,
) -> str:
    """
    Deterministic compact JSON serialization.
    """

    return json.dumps(
        _json_ready(
            value
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
    Parse a JSON object stored as either mapping or string.
    """

    if isinstance(
        value,
        Mapping,
    ):
        return dict(
            value
        )

    try:
        parsed = json.loads(
            str(
                value
            )
        )

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{record_id}: invalid {field_name}"
        ) from exc

    if not isinstance(
        parsed,
        dict,
    ):
        raise ValueError(
            f"{record_id}: {field_name} must contain a JSON object"
        )

    return parsed


# ============================================================
# GENERIC INPUT VALIDATION
# ============================================================


def _require_columns(
    name: str,
    dataframe: pd.DataFrame,
    required: set[str],
    allow_empty: bool = False,
) -> None:
    """
    Require DataFrame presence and exact minimum schema.
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
            f"{name} DataFrame missing required columns: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
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
    Read generation time window.
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


def _get_copilot_config(
    generation: Mapping[str, Any],
) -> tuple[
    int,
    tuple[str, ...],
]:
    """
    Read exact live Copilot configuration.
    """

    copilot = generation.get(
        "copilot"
    )

    if not isinstance(
        copilot,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.copilot configuration"
        )

    evaluation_questions = copilot.get(
        "evaluation_questions"
    )

    if not isinstance(
        evaluation_questions,
        Mapping,
    ):
        raise KeyError(
            "Missing copilot.evaluation_questions"
        )

    if "count" not in evaluation_questions:
        raise KeyError(
            "Missing copilot.evaluation_questions.count"
        )

    count = int(
        evaluation_questions[
            "count"
        ]
    )

    if count <= 0:
        raise ValueError(
            "copilot.evaluation_questions.count must be > 0"
        )

    supported = copilot.get(
        "supported_domains"
    )

    if not isinstance(
        supported,
        list,
    ):
        raise KeyError(
            "Missing or invalid copilot.supported_domains"
        )

    supported_domains = tuple(
        str(
            domain
        )
        .strip()
        .lower()
        for domain
        in supported
    )

    if len(
        set(
            supported_domains
        )
    ) != len(
        supported_domains
    ):
        raise ValueError(
            "Duplicate copilot.supported_domains values"
        )

    missing_domains = (
        set(
            EXPECTED_SUPPORTED_DOMAINS
        )
        -
        set(
            supported_domains
        )
    )

    if missing_domains:
        raise ValueError(
            "Missing expected Copilot domains: "
            +
            ", ".join(
                sorted(
                    missing_domains
                )
            )
        )

    return (
        count,
        supported_domains,
    )


def _get_split_config(
    generation: Mapping[str, Any],
) -> dict[str, float]:
    """
    Read exact entity-data split configuration.
    """

    splits = generation.get(
        "splits"
    )

    if not isinstance(
        splits,
        Mapping,
    ):
        raise KeyError(
            "Missing generation.splits configuration"
        )

    entity_data = splits.get(
        "entity_data"
    )

    if not isinstance(
        entity_data,
        Mapping,
    ):
        raise KeyError(
            "Missing splits.entity_data"
        )

    required = {
        "train",
        "validation",
        "test",
    }

    missing = (
        required
        -
        set(
            entity_data.keys()
        )
    )

    if missing:
        raise KeyError(
            "Missing splits.entity_data keys: "
            +
            ", ".join(
                sorted(
                    missing
                )
            )
        )

    result = {
        "train":
            float(
                entity_data[
                    "train"
                ]
            ),

        "validation":
            float(
                entity_data[
                    "validation"
                ]
            ),

        "test":
            float(
                entity_data[
                    "test"
                ]
            ),
    }

    if any(
        value < 0.0
        for value
        in result.values()
    ):
        raise ValueError(
            "Split fractions cannot be negative"
        )

    if not np.isclose(
        sum(
            result.values()
        ),
        1.0,
    ):
        raise ValueError(
            "Entity split fractions must sum to 1.0"
        )

    return result


# ============================================================
# INPUT VALIDATION
# ============================================================


def _validate_inputs(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    audit_events: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    agent_events: pd.DataFrame,
    action_outcomes: pd.DataFrame,
    manufacturing_timeseries: pd.DataFrame,
    warranty_claims: pd.DataFrame,
) -> None:
    """
    Validate upstream runtime datasets.
    """

    _require_columns(
        "recommendations",
        recommendations,
        RECOMMENDATION_REQUIRED_COLUMNS,
    )

    _require_columns(
        "compliance_checks",
        compliance_checks,
        COMPLIANCE_REQUIRED_COLUMNS,
    )

    _require_columns(
        "trust_decisions",
        trust_decisions,
        TRUST_REQUIRED_COLUMNS,
    )

    _require_columns(
        "audit_events",
        audit_events,
        AUDIT_REQUIRED_COLUMNS,
    )

    _require_columns(
        "workflow_runs",
        workflow_runs,
        WORKFLOW_REQUIRED_COLUMNS,
    )

    _require_columns(
        "agent_events",
        agent_events,
        AGENT_EVENT_REQUIRED_COLUMNS,
    )

    _require_columns(
        "action_outcomes",
        action_outcomes,
        ACTION_OUTCOME_REQUIRED_COLUMNS,
        allow_empty=True,
    )

    _require_columns(
        "manufacturing_timeseries",
        manufacturing_timeseries,
        MANUFACTURING_REQUIRED_COLUMNS,
    )

    _require_columns(
        "warranty_claims",
        warranty_claims,
        WARRANTY_REQUIRED_COLUMNS,
    )

    if (
        recommendations[
            "recommendation_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate recommendation IDs"
        )

    if (
        trust_decisions[
            "decision_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate decision IDs"
        )

    if (
        workflow_runs[
            "workflow_run_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate workflow IDs"
        )


# ============================================================
# CASE BUILDER
# ============================================================


def _build_case(
    domain: str,
    ordinal: int,
    question: str,
    task_type: str,
    difficulty: str,
    response_type: str,
    route_tables: list[str],
    expected_answer: Mapping[str, Any],
    expected_entities: list[str],
    must_include_facts: list[str],
    must_not_invent: list[str],
    source_refs: list[str],
    answerable: bool = True,
    evaluation_notes: str = "",
) -> dict[str, Any]:
    """
    Build one runtime question + hidden evaluator truth bundle.
    """

    return {
        "domain":
            domain,

        "case_ordinal":
            int(
                ordinal
            ),

        "question":
            str(
                question
            ),

        "task_type":
            str(
                task_type
            ),

        "difficulty":
            str(
                difficulty
            ),

        "response_type":
            str(
                response_type
            ),

        "route_tables":
            list(
                route_tables
            ),

        "answerable":
            bool(
                answerable
            ),

        "expected_answer":
            dict(
                expected_answer
            ),

        "expected_entities":
            list(
                expected_entities
            ),

        "must_include_facts":
            list(
                must_include_facts
            ),

        "must_not_invent":
            list(
                must_not_invent
            ),

        "source_refs":
            list(
                source_refs
            ),

        "evaluation_notes":
            str(
                evaluation_notes
            ),
    }


# ============================================================
# RECOMMENDATION-BACKED DOMAIN CASES
# ============================================================


def _recommendation_domain_cases(
    copilot_domain: str,
    governance_domain: str,
    recommendations: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    action_outcomes: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate ten grounded cases for recommendation-backed domains.
    """

    recs = (
        recommendations.loc[
            recommendations[
                "domain"
            ]
            .astype(
                str
            )
            ==
            governance_domain
        ]
        .copy()
    )

    if recs.empty:
        raise ValueError(
            f"No recommendations found for {governance_domain}"
        )

    decisions = (
        trust_decisions.loc[
            trust_decisions[
                "domain"
            ]
            .astype(
                str
            )
            ==
            governance_domain
        ]
        .copy()
    )

    workflows = (
        workflow_runs.loc[
            workflow_runs[
                "domain"
            ]
            .astype(
                str
            )
            ==
            governance_domain
        ]
        .copy()
    )

    outcomes = (
        action_outcomes.loc[
            action_outcomes[
                "domain"
            ]
            .astype(
                str
            )
            ==
            governance_domain
        ]
        .copy()
    )

    recommendation_count = len(
        recs
    )

    type_counts = (
        recs[
            "recommendation_type"
        ]
        .astype(
            str
        )
        .value_counts()
    )

    top_type = str(
        type_counts.index[
            0
        ]
    )

    top_type_count = int(
        type_counts.iloc[
            0
        ]
    )

    high_risk_count = int(
        (
            recs[
                "risk_level"
            ]
            .astype(
                str
            )
            ==
            "HIGH"
        )
        .sum()
    )

    human_review_count = int(
        decisions[
            "human_review_required"
        ]
        .astype(
            bool
        )
        .sum()
    )

    approved_count = int(
        (
            decisions[
                "decision"
            ]
            .astype(
                str
            )
            ==
            "APPROVED"
        )
        .sum()
    )

    non_approved_count = int(
        (
            decisions[
                "decision"
            ]
            .astype(
                str
            )
            !=
            "APPROVED"
        )
        .sum()
    )

    workflow_count = len(
        workflows
    )

    action_count = len(
        outcomes
    )

    ranked = (
        recs
        .assign(
            _confidence=
                pd.to_numeric(
                    recs[
                        "confidence"
                    ],
                    errors="raise",
                )
        )
        .sort_values(
            [
                "_confidence",
                "recommendation_id",
            ],
            ascending=[
                False,
                True,
            ],
        )
    )

    highest_confidence = ranked.iloc[
        0
    ]

    highest_entity = str(
        highest_confidence[
            "target_entity_id"
        ]
    )

    highest_confidence_value = float(
        highest_confidence[
            "_confidence"
        ]
    )

    display_name = (
        copilot_domain.capitalize()
    )

    return [
        _build_case(
            copilot_domain,
            1,
            (
                f"How many {display_name} recommendations exist "
                "in the current governance snapshot?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "recommendations",
            ],
            {
                "recommendation_count":
                    recommendation_count,
            },
            [],
            [
                str(
                    recommendation_count
                ),
                "recommendations",
            ],
            [
                "additional recommendations not present in the database",
            ],
            [
                "recommendations",
            ],
        ),

        _build_case(
            copilot_domain,
            2,
            (
                f"What is the most common {display_name} "
                "recommendation type in this snapshot?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_EASY,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "recommendations",
            ],
            {
                "recommendation_type":
                    top_type,

                "count":
                    top_type_count,
            },
            [
                top_type,
            ],
            [
                top_type,
                str(
                    top_type_count
                ),
            ],
            [
                "recommendation types absent from the data",
            ],
            [
                "recommendations",
            ],
        ),

        _build_case(
            copilot_domain,
            3,
            (
                f"How many {display_name} recommendations "
                "are classified HIGH risk?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "recommendations",
            ],
            {
                "high_risk_count":
                    high_risk_count,
            },
            [],
            [
                str(
                    high_risk_count
                ),
                "HIGH",
            ],
            [
                "risk probabilities not stored in recommendation evidence",
            ],
            [
                "recommendations",
            ],
        ),

        _build_case(
            copilot_domain,
            4,
            (
                f"How many {display_name} recommendations "
                "were routed to human review?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "trust_decisions",
            ],
            {
                "human_review_count":
                    human_review_count,
            },
            [],
            [
                str(
                    human_review_count
                ),
                "human review",
            ],
            [
                "human reviews without a trust decision record",
            ],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            copilot_domain,
            5,
            (
                f"How many {display_name} trust decisions "
                "were APPROVED?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "trust_decisions",
            ],
            {
                "approved_count":
                    approved_count,
            },
            [],
            [
                str(
                    approved_count
                ),
                "APPROVED",
            ],
            [
                "approval records absent from the trust ledger",
            ],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            copilot_domain,
            6,
            (
                f"How many {display_name} trust decisions "
                "were not approved?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "trust_decisions",
            ],
            {
                "non_approved_count":
                    non_approved_count,
            },
            [],
            [
                str(
                    non_approved_count
                ),
            ],
            [
                "decision states absent from the trust ledger",
            ],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            copilot_domain,
            7,
            (
                f"How many {display_name} recommendations are represented "
                "in the selected agent-workflow population?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "agent_workflow_runs",
            ],
            {
                "workflow_count":
                    workflow_count,
            },
            [],
            [
                str(
                    workflow_count
                ),
                "workflow",
            ],
            [
                "workflow runs for recommendations that were not selected",
            ],
            [
                "agent_workflow_runs",
            ],
        ),

        _build_case(
            copilot_domain,
            8,
            (
                f"How many immediate {display_name} action execution "
                "outcomes were recorded?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "action_outcomes",
            ],
            {
                "action_outcome_count":
                    action_count,
            },
            [],
            [
                str(
                    action_count
                ),
                "immediate",
            ],
            [
                "downstream revenue impact",
                "future customer response",
            ],
            [
                "action_outcomes",
            ],
        ),

        _build_case(
            copilot_domain,
            9,
            (
                f"Which {display_name} target entity has the highest "
                "recommendation confidence in this snapshot?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_HARD,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "recommendations",
            ],
            {
                "target_entity_id":
                    highest_entity,

                "confidence":
                    round(
                        highest_confidence_value,
                        6,
                    ),
            },
            [
                highest_entity,
            ],
            [
                highest_entity,
                str(
                    round(
                        highest_confidence_value,
                        4,
                    )
                ),
            ],
            [
                "probability interpretation beyond recommendation confidence",
            ],
            [
                str(
                    highest_confidence[
                        "recommendation_id"
                    ]
                ),
            ],
        ),

        _build_case(
            copilot_domain,
            10,
            (
                f"Do the current {display_name} action-outcome records prove "
                "that downstream business value was achieved?"
            ),
            TASK_ANTI_HALLUCINATION,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "action_outcomes",
            ],
            {
                "business_value_proven":
                    False,

                "reason":
                    (
                        "action_outcomes contain immediate execution "
                        "evidence only"
                    ),
            },
            [],
            [
                "immediate execution",
                "business outcome not observed",
            ],
            [
                "revenue uplift",
                "recovery uplift",
                "SLA improvement",
                "conversion uplift",
            ],
            [
                "action_outcomes",
            ],
        ),
    ]


# ============================================================
# DEALER CASES
# ============================================================


def _dealer_cases(
    recommendations: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    action_outcomes: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate Dealer cases from AUTO recommendation evidence.
    """

    auto_recs = (
        recommendations.loc[
            recommendations[
                "domain"
            ]
            .astype(
                str
            )
            ==
            "AUTO"
        ]
        .copy()
    )

    evidence_rows: list[
        dict[str, Any]
    ] = []

    for row in auto_recs.itertuples(
        index=False
    ):
        payload = _parse_json_object(
            row.evidence_json,
            "evidence_json",
            str(
                row.recommendation_id
            ),
        )

        dealer_id = payload.get(
            "dealer_id"
        )

        dealer_name = payload.get(
            "dealer_name"
        )

        if dealer_id is None:
            continue

        evidence_rows.append(
            {
                "recommendation_id":
                    str(
                        row.recommendation_id
                    ),

                "dealer_id":
                    str(
                        dealer_id
                    ),

                "dealer_name":
                    (
                        None
                        if dealer_name is None
                        else str(
                            dealer_name
                        )
                    ),

                "confidence":
                    _safe_float(
                        row.confidence
                    ),

                "risk_level":
                    str(
                        row.risk_level
                    ),

                "target_entity_id":
                    str(
                        row.target_entity_id
                    ),
            }
        )

    dealer_evidence = pd.DataFrame(
        evidence_rows
    )

    if dealer_evidence.empty:
        raise ValueError(
            "AUTO recommendation evidence contains no dealer_id; "
            "cannot generate grounded Dealer Copilot cases"
        )

    dealer_counts = (
        dealer_evidence[
            "dealer_id"
        ]
        .value_counts()
    )

    top_dealer_id = str(
        dealer_counts.index[
            0
        ]
    )

    top_dealer_count = int(
        dealer_counts.iloc[
            0
        ]
    )

    unique_dealers = int(
        dealer_evidence[
            "dealer_id"
        ]
        .nunique()
    )

    top_rows = (
        dealer_evidence.loc[
            dealer_evidence[
                "dealer_id"
            ]
            ==
            top_dealer_id
        ]
        .copy()
    )

    top_names = (
        top_rows[
            "dealer_name"
        ]
        .dropna()
    )

    top_dealer_name = (
        str(
            top_names.iloc[
                0
            ]
        )
        if not top_names.empty
        else top_dealer_id
    )

    top_high_risk = int(
        (
            top_rows[
                "risk_level"
            ]
            ==
            "HIGH"
        )
        .sum()
    )

    decision_join = (
        top_rows[
            [
                "recommendation_id",
            ]
        ]
        .merge(
            trust_decisions[
                [
                    "recommendation_id",
                    "decision_id",
                    "decision",
                    "human_review_required",
                ]
            ],
            on="recommendation_id",
            how="left",
            validate="one_to_one",
        )
    )

    top_reviewed = int(
        decision_join[
            "human_review_required"
        ]
        .fillna(
            False
        )
        .astype(
            bool
        )
        .sum()
    )

    top_approved = int(
        (
            decision_join[
                "decision"
            ]
            .astype(
                str
            )
            ==
            "APPROVED"
        )
        .sum()
    )

    recommendation_ids = set(
        top_rows[
            "recommendation_id"
        ]
        .astype(
            str
        )
    )

    top_workflows = (
        workflow_runs.loc[
            workflow_runs[
                "recommendation_id"
            ]
            .astype(
                str
            )
            .isin(
                recommendation_ids
            )
        ]
    )

    top_outcomes = (
        action_outcomes.loc[
            action_outcomes[
                "recommendation_id"
            ]
            .astype(
                str
            )
            .isin(
                recommendation_ids
            )
        ]
    )

    max_row = (
        top_rows
        .sort_values(
            [
                "confidence",
                "recommendation_id",
            ],
            ascending=[
                False,
                True,
            ],
        )
        .iloc[
            0
        ]
    )

    return [
        _build_case(
            DOMAIN_DEALER,
            1,
            (
                "How many dealers are represented in the current "
                "AUTO allocation recommendation evidence?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "recommendations",
            ],
            {
                "unique_dealers":
                    unique_dealers,
            },
            [],
            [
                str(
                    unique_dealers
                ),
                "dealers",
            ],
            [
                "dealer IDs absent from recommendation evidence",
            ],
            [
                "recommendations.evidence_json",
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            2,
            (
                "Which dealer appears most frequently in the current "
                "AUTO recommendation evidence?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_MEDIUM,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "recommendations",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "dealer_name":
                    top_dealer_name,

                "recommendation_count":
                    top_dealer_count,
            },
            [
                top_dealer_id,
            ],
            [
                top_dealer_id,
                str(
                    top_dealer_count
                ),
            ],
            [
                "dealer revenue not represented by these recommendation rows",
            ],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            3,
            (
                f"How many recommendations currently reference dealer "
                f"{top_dealer_id}?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "recommendations",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "recommendation_count":
                    top_dealer_count,
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    top_dealer_count
                ),
            ],
            [],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            4,
            (
                f"How many HIGH-risk recommendations reference dealer "
                f"{top_dealer_id}?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "recommendations",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "high_risk_count":
                    top_high_risk,
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    top_high_risk
                ),
                "HIGH",
            ],
            [],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            5,
            (
                f"How many recommendations for dealer {top_dealer_id} "
                "were routed to human review?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "recommendations",
                "trust_decisions",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "human_review_count":
                    top_reviewed,
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    top_reviewed
                ),
            ],
            [],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            6,
            (
                f"How many recommendations for dealer {top_dealer_id} "
                "received an APPROVED trust decision?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "recommendations",
                "trust_decisions",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "approved_count":
                    top_approved,
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    top_approved
                ),
                "APPROVED",
            ],
            [],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            7,
            (
                f"How many selected agent workflows relate to dealer "
                f"{top_dealer_id}?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "recommendations",
                "agent_workflow_runs",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "workflow_count":
                    len(
                        top_workflows
                    ),
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    len(
                        top_workflows
                    )
                ),
            ],
            [],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            8,
            (
                f"How many immediate executed action outcomes relate to "
                f"dealer {top_dealer_id}?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_HARD,
            RESPONSE_NUMBER,
            [
                "recommendations",
                "action_outcomes",
            ],
            {
                "dealer_id":
                    top_dealer_id,

                "action_outcome_count":
                    len(
                        top_outcomes
                    ),
            },
            [
                top_dealer_id,
            ],
            [
                str(
                    len(
                        top_outcomes
                    )
                ),
            ],
            [
                "dealer revenue generated after the action",
            ],
            [
                top_dealer_id,
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            9,
            (
                f"Which target entity for dealer {top_dealer_id} has the "
                "highest recommendation confidence?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_HARD,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "recommendations",
            ],
            {
                "target_entity_id":
                    str(
                        max_row[
                            "target_entity_id"
                        ]
                    ),

                "confidence":
                    round(
                        float(
                            max_row[
                                "confidence"
                            ]
                        ),
                        6,
                    ),
            },
            [
                str(
                    max_row[
                        "target_entity_id"
                    ]
                ),
            ],
            [
                str(
                    max_row[
                        "target_entity_id"
                    ]
                ),
            ],
            [],
            [
                str(
                    max_row[
                        "recommendation_id"
                    ]
                ),
            ],
        ),

        _build_case(
            DOMAIN_DEALER,
            10,
            (
                f"Can the current recommendation evidence prove the exact "
                f"revenue leakage amount for dealer {top_dealer_id}?"
            ),
            TASK_ANTI_HALLUCINATION,
            DIFFICULTY_HARD,
            RESPONSE_ABSTENTION,
            [
                "recommendations",
            ],
            {
                "exact_revenue_leakage_available":
                    False,

                "reason":
                    (
                        "recommendation evidence does not contain "
                        "a verified downstream revenue-leakage outcome"
                    ),
            },
            [
                top_dealer_id,
            ],
            [
                "insufficient evidence",
            ],
            [
                "fabricated revenue leakage amount",
                "fabricated revenue uplift",
            ],
            [
                top_dealer_id,
            ],
            answerable=False,
        ),
    ]


# ============================================================
# MANUFACTURING CASES
# ============================================================


def _manufacturing_cases(
    manufacturing_timeseries: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate grounded manufacturing observational and causal
    restraint cases.
    """

    work = (
        manufacturing_timeseries
        .copy()
    )

    work[
        "_timestamp"
    ] = pd.to_datetime(
        work[
            "timestamp"
        ],
        errors="raise",
        utc=True,
    )

    observation_count = len(
        work
    )

    unique_plants = int(
        work[
            "plant_id"
        ]
        .nunique()
    )

    unique_lines = int(
        work[
            "production_line_id"
        ]
        .nunique()
    )

    unique_machines = int(
        work[
            "machine_id"
        ]
        .nunique()
    )

    first_timestamp = (
        work[
            "_timestamp"
        ]
        .min()
    )

    last_timestamp = (
        work[
            "_timestamp"
        ]
        .max()
    )

    machine_counts = (
        work[
            "machine_id"
        ]
        .astype(
            str
        )
        .value_counts()
    )

    top_machine = str(
        machine_counts.index[
            0
        ]
    )

    top_machine_count = int(
        machine_counts.iloc[
            0
        ]
    )

    ordered = (
        work
        .sort_values(
            [
                "machine_id",
                "_timestamp",
            ]
        )
    )

    deltas = (
        ordered
        .groupby(
            "machine_id"
        )[
            "_timestamp"
        ]
        .diff()
        .dropna()
        .dt.total_seconds()
    )

    median_frequency_seconds = (
        float(
            deltas.median()
        )
        if not deltas.empty
        else None
    )

    return [
        _build_case(
            DOMAIN_MANUFACTURING,
            1,
            (
                "How many manufacturing causal time-series observations "
                "are available?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "observation_count":
                    observation_count,
            },
            [],
            [
                str(
                    observation_count
                ),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            2,
            (
                "How many plants are represented in the manufacturing "
                "causal time series?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "plant_count":
                    unique_plants,
            },
            [],
            [
                str(
                    unique_plants
                ),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            3,
            (
                "How many production lines are represented in the "
                "manufacturing causal time series?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "production_line_count":
                    unique_lines,
            },
            [],
            [
                str(
                    unique_lines
                ),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            4,
            (
                "How many machines are represented in the manufacturing "
                "causal time series?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "machine_count":
                    unique_machines,
            },
            [],
            [
                str(
                    unique_machines
                ),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            5,
            (
                "What is the earliest timestamp in the manufacturing "
                "causal observation history?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_STRUCTURED,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "first_timestamp":
                    first_timestamp.isoformat(),
            },
            [],
            [
                first_timestamp.isoformat(),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            6,
            (
                "What is the latest timestamp in the manufacturing "
                "causal observation history?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_STRUCTURED,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "last_timestamp":
                    last_timestamp.isoformat(),
            },
            [],
            [
                last_timestamp.isoformat(),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            7,
            (
                "Which machine has the most manufacturing time-series "
                "observations?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_MEDIUM,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "machine_id":
                    top_machine,

                "observation_count":
                    top_machine_count,
            },
            [
                top_machine,
            ],
            [
                top_machine,
                str(
                    top_machine_count
                ),
            ],
            [],
            [
                top_machine,
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            8,
            (
                "What is the median sampling interval per machine in the "
                "manufacturing causal time series?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_HARD,
            RESPONSE_STRUCTURED,
            [
                "manufacturing_causal_timeseries",
            ],
            {
                "median_interval_seconds":
                    median_frequency_seconds,
            },
            [],
            [
                str(
                    median_frequency_seconds
                ),
            ],
            [],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            9,
            (
                "Can a correlation visible in the raw manufacturing "
                "observations by itself be reported as a discovered causal edge?"
            ),
            TASK_CAUSAL_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "manufacturing_causal_timeseries",
                "runtime_pcmci_edges",
            ],
            {
                "causal_edge_proven_from_raw_observations":
                    False,

                "reason":
                    (
                        "runtime causal discovery must establish "
                        "the lagged relationship"
                    ),
            },
            [],
            [
                "runtime causal discovery",
                "raw observations alone are insufficient",
            ],
            [
                "invented causal edge",
                "generator causal truth",
            ],
            [
                "manufacturing_causal_timeseries",
            ],
        ),

        _build_case(
            DOMAIN_MANUFACTURING,
            10,
            (
                "Should the runtime Copilot read synthetic causal "
                "ground-truth relationships when explaining manufacturing drivers?"
            ),
            TASK_CAUSAL_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "manufacturing_causal_timeseries",
                "runtime_pcmci_edges",
            ],
            {
                "runtime_may_read_generator_causal_truth":
                    False,
            },
            [],
            [
                "runtime must use discovered evidence",
            ],
            [
                "synthetic causal ground truth",
                "hardcoded generator edge",
            ],
            [
                "manufacturing_causal_timeseries",
            ],
        ),
    ]


# ============================================================
# WARRANTY CASES
# ============================================================


def _warranty_cases(
    warranty_claims: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate grounded warranty evaluation cases from the actual
    frozen warranty-claim schema.

    Runtime evidence used:

        warranty_claim_id
        production_batch_id
        primary_supplier_lot_id
        claim_amount_inr
        approved_amount_inr
        claim_status

    Production/supplier linkage is evidence for investigation.
    It is not treated as causal proof.
    """

    work = (
        warranty_claims
        .copy()
    )

    claim_count = len(
        work
    )

    claim_amount = pd.to_numeric(
        work[
            "claim_amount_inr"
        ],
        errors="raise",
    )

    approved_amount = pd.to_numeric(
        work[
            "approved_amount_inr"
        ],
        errors="raise",
    )

    total_claim_amount = float(
        claim_amount.sum()
    )

    total_approved_amount = float(
        approved_amount.sum()
    )

    status_counts = (
        work[
            "claim_status"
        ]
        .astype(
            str
        )
        .value_counts()
    )

    if status_counts.empty:
        raise ValueError(
            "Warranty claim_status distribution is empty"
        )

    top_status = str(
        status_counts.index[
            0
        ]
    )

    top_status_count = int(
        status_counts.iloc[
            0
        ]
    )

    approved_claim_count = int(
        (
            work[
                "claim_status"
            ]
            .astype(
                str
            )
            ==
            "APPROVED"
        )
        .sum()
    )

    unique_batches = int(
        work[
            "production_batch_id"
        ]
        .dropna()
        .astype(
            str
        )
        .nunique()
    )

    unique_supplier_lots = int(
        work[
            "primary_supplier_lot_id"
        ]
        .dropna()
        .astype(
            str
        )
        .nunique()
    )

    max_index = (
        claim_amount
        .idxmax()
    )

    largest_claim_id = str(
        work.loc[
            max_index,
            "warranty_claim_id",
        ]
    )

    largest_claim_amount = float(
        claim_amount.loc[
            max_index
        ]
    )

    return [
        _build_case(
            DOMAIN_WARRANTY,
            1,
            (
                "How many warranty claims are present in the current "
                "synthetic operational history?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
            ],
            {
                "warranty_claim_count":
                    claim_count,
            },
            [],
            [
                str(
                    claim_count
                ),
            ],
            [],
            [
                "warranty_claims",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            2,
            (
                "What is the most common warranty claim status?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_EASY,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "warranty_claims",
            ],
            {
                "claim_status":
                    top_status,

                "count":
                    top_status_count,
            },
            [
                top_status,
            ],
            [
                top_status,
                str(
                    top_status_count
                ),
            ],
            [],
            [
                "warranty_claims",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            3,
            (
                "What is the total submitted warranty claim amount?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
            ],
            {
                "total_claim_amount_inr":
                    round(
                        total_claim_amount,
                        2,
                    ),
            },
            [],
            [
                str(
                    round(
                        total_claim_amount,
                        2,
                    )
                ),
            ],
            [],
            [
                "warranty_claims.claim_amount_inr",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            4,
            (
                "What is the total approved warranty amount?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
            ],
            {
                "total_approved_amount_inr":
                    round(
                        total_approved_amount,
                        2,
                    ),
            },
            [],
            [
                str(
                    round(
                        total_approved_amount,
                        2,
                    )
                ),
            ],
            [],
            [
                "warranty_claims.approved_amount_inr",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            5,
            (
                "How many warranty claims have APPROVED status?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
            ],
            {
                "approved_claim_count":
                    approved_claim_count,
            },
            [],
            [
                str(
                    approved_claim_count
                ),
                "APPROVED",
            ],
            [],
            [
                "warranty_claims.claim_status",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            6,
            (
                "How many distinct production batches are linked "
                "to warranty claims?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
                "production_batches",
            ],
            {
                "production_batch_count":
                    unique_batches,
            },
            [],
            [
                str(
                    unique_batches
                ),
            ],
            [],
            [
                "warranty_claims.production_batch_id",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            7,
            (
                "How many distinct primary supplier lots are linked "
                "to warranty claims?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "warranty_claims",
                "supplier_lots",
            ],
            {
                "primary_supplier_lot_count":
                    unique_supplier_lots,
            },
            [],
            [
                str(
                    unique_supplier_lots
                ),
            ],
            [],
            [
                "warranty_claims.primary_supplier_lot_id",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            8,
            (
                "Which warranty claim has the largest submitted "
                "claim amount?"
            ),
            TASK_ENTITY_RANKING,
            DIFFICULTY_MEDIUM,
            RESPONSE_ENTITY_AND_METRIC,
            [
                "warranty_claims",
            ],
            {
                "warranty_claim_id":
                    largest_claim_id,

                "claim_amount_inr":
                    round(
                        largest_claim_amount,
                        2,
                    ),
            },
            [
                largest_claim_id,
            ],
            [
                largest_claim_id,
                str(
                    round(
                        largest_claim_amount,
                        2,
                    )
                ),
            ],
            [],
            [
                largest_claim_id,
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            9,
            (
                "Does a primary supplier lot appearing in warranty "
                "claims prove that the supplier lot caused those failures?"
            ),
            TASK_CAUSAL_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "warranty_claims",
                "production_batches",
                "supplier_lots",
                "runtime_pcmci_edges",
            ],
            {
                "causality_proven":
                    False,

                "reason":
                    (
                        "relational linkage is evidence for investigation, "
                        "not causal proof"
                    ),
            },
            [],
            [
                "linkage is not causal proof",
            ],
            [
                "invented supplier causality",
            ],
            [
                "warranty_claims.primary_supplier_lot_id",
            ],
        ),

        _build_case(
            DOMAIN_WARRANTY,
            10,
            (
                "Can the Copilot name a top causal driver of warranty "
                "claims if no discovered runtime causal edge supports it?"
            ),
            TASK_CAUSAL_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_ABSTENTION,
            [
                "warranty_claims",
                "runtime_pcmci_edges",
            ],
            {
                "may_name_unsupported_causal_driver":
                    False,
            },
            [],
            [
                "must use discovered causal evidence",
            ],
            [
                "invented causal driver",
                "generator-only causal relationship",
            ],
            [
                "warranty_claims",
                "runtime_pcmci_edges",
            ],
            answerable=False,
        ),
    ]


# ============================================================
# COMPLIANCE CASES
# ============================================================


def _compliance_cases(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    audit_events: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate compliance/trust evaluation cases.
    """

    decision_count = len(
        trust_decisions
    )

    check_count = len(
        compliance_checks
    )

    checks_per_decision = (
        float(
            check_count
        )
        /
        float(
            decision_count
        )
    )

    pass_count = int(
        (
            compliance_checks[
                "result"
            ]
            .astype(
                str
            )
            ==
            "PASS"
        )
        .sum()
    )

    review_required_count = int(
        (
            compliance_checks[
                "result"
            ]
            .astype(
                str
            )
            ==
            "REVIEW_REQUIRED"
        )
        .sum()
    )

    human_review_count = int(
        trust_decisions[
            "human_review_required"
        ]
        .astype(
            bool
        )
        .sum()
    )

    approved_count = int(
        (
            trust_decisions[
                "decision"
            ]
            .astype(
                str
            )
            ==
            "APPROVED"
        )
        .sum()
    )

    modified_count = int(
        (
            trust_decisions[
                "decision"
            ]
            .astype(
                str
            )
            ==
            "MODIFIED"
        )
        .sum()
    )

    rejected_count = int(
        (
            trust_decisions[
                "decision"
            ]
            .astype(
                str
            )
            ==
            "REJECTED"
        )
        .sum()
    )

    trust_audit_count = int(
        (
            audit_events[
                "event_type"
            ]
            .astype(
                str
            )
            ==
            "TRUST_DECISION_RECORDED"
        )
        .sum()
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

    missing_decisions = len(
        recommendation_ids
        -
        decision_recommendation_ids
    )

    return [
        _build_case(
            DOMAIN_COMPLIANCE,
            1,
            "How many trust decisions exist in the governance snapshot?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "trust_decisions",
            ],
            {
                "trust_decision_count":
                    decision_count,
            },
            [],
            [
                str(
                    decision_count
                ),
            ],
            [],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            2,
            "How many compliance checks were evaluated?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "compliance_checks",
            ],
            {
                "compliance_check_count":
                    check_count,
            },
            [],
            [
                str(
                    check_count
                ),
            ],
            [],
            [
                "compliance_checks",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            3,
            (
                "How many compliance checks are associated with each "
                "trust decision?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "compliance_checks",
                "trust_decisions",
            ],
            {
                "checks_per_decision":
                    checks_per_decision,
            },
            [],
            [
                str(
                    checks_per_decision
                ),
            ],
            [],
            [
                "compliance_checks",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            4,
            "How many compliance checks returned PASS?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "compliance_checks",
            ],
            {
                "pass_count":
                    pass_count,
            },
            [],
            [
                str(
                    pass_count
                ),
            ],
            [],
            [
                "compliance_checks",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            5,
            "How many compliance checks required human review?",
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "compliance_checks",
            ],
            {
                "review_required_count":
                    review_required_count,
            },
            [],
            [
                str(
                    review_required_count
                ),
            ],
            [],
            [
                "compliance_checks",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            6,
            "How many trust decisions were routed to human review?",
            TASK_GOVERNANCE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "trust_decisions",
            ],
            {
                "human_review_count":
                    human_review_count,
            },
            [],
            [
                str(
                    human_review_count
                ),
            ],
            [],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            7,
            (
                "What is the APPROVED / MODIFIED / REJECTED "
                "trust-decision mix?"
            ),
            TASK_GOVERNANCE,
            DIFFICULTY_HARD,
            RESPONSE_STRUCTURED,
            [
                "trust_decisions",
            ],
            {
                "APPROVED":
                    approved_count,

                "MODIFIED":
                    modified_count,

                "REJECTED":
                    rejected_count,
            },
            [],
            [
                str(
                    approved_count
                ),
                str(
                    modified_count
                ),
                str(
                    rejected_count
                ),
            ],
            [],
            [
                "trust_decisions",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            8,
            (
                "How many final trust decisions are represented by "
                "TRUST_DECISION_RECORDED audit events?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_MEDIUM,
            RESPONSE_NUMBER,
            [
                "audit_events",
                "trust_decisions",
            ],
            {
                "trust_audit_event_count":
                    trust_audit_count,
            },
            [],
            [
                str(
                    trust_audit_count
                ),
            ],
            [],
            [
                "audit_events",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            9,
            (
                "How many recommendations are missing a "
                "trust-decision record?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_HARD,
            RESPONSE_NUMBER,
            [
                "recommendations",
                "trust_decisions",
            ],
            {
                "missing_trust_decisions":
                    missing_decisions,
            },
            [],
            [
                str(
                    missing_decisions
                ),
            ],
            [
                "unrecorded approval",
            ],
            [
                "recommendations",
                "trust_decisions",
            ],
        ),

        _build_case(
            DOMAIN_COMPLIANCE,
            10,
            (
                "May the Copilot describe a recommendation as approved "
                "when no trust-decision record exists?"
            ),
            TASK_ANTI_HALLUCINATION,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "trust_decisions",
                "audit_events",
            ],
            {
                "approval_without_decision_allowed":
                    False,
            },
            [],
            [
                "approval requires trust-decision evidence",
            ],
            [
                "fabricated approval",
            ],
            [
                "trust_decisions",
            ],
        ),
    ]


# ============================================================
# SIMULATION CASES
# ============================================================


def _simulation_cases(
    agent_events: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Generate evaluation cases for current simulation availability.

    Simulation results must never be fabricated when the
    Simulation Agent has no linked runtime artifact.
    """

    simulations = (
        agent_events.loc[
            agent_events[
                "agent_name"
            ]
            .astype(
                str
            )
            ==
            "Simulation Agent"
        ]
        .copy()
    )

    total_events = len(
        simulations
    )

    completed_count = int(
        (
            simulations[
                "status"
            ]
            .astype(
                str
            )
            ==
            "COMPLETED"
        )
        .sum()
    )

    skipped_count = int(
        (
            simulations[
                "status"
            ]
            .astype(
                str
            )
            ==
            "SKIPPED"
        )
        .sum()
    )

    workflow_count = int(
        simulations[
            "workflow_run_id"
        ]
        .nunique()
    )

    status_counts = (
        simulations[
            "status"
        ]
        .astype(
            str
        )
        .value_counts()
    )

    dominant_status = (
        str(
            status_counts.index[
                0
            ]
        )
        if not status_counts.empty
        else None
    )

    skip_reasons: list[str] = []

    for row in simulations.itertuples(
        index=False
    ):
        payload = _parse_json_object(
            row.output_refs,
            "output_refs",
            str(
                row.agent_run_id
            ),
        )

        reason = payload.get(
            "skip_reason"
        )

        if reason is not None:
            skip_reasons.append(
                str(
                    reason
                )
            )

    reason_counter = Counter(
        skip_reasons
    )

    dominant_reason = (
        reason_counter.most_common(
            1
        )[
            0
        ][
            0
        ]
        if reason_counter
        else None
    )

    completed_workflow_ids = (
        simulations.loc[
            simulations[
                "status"
            ]
            .astype(
                str
            )
            ==
            "COMPLETED",
            "workflow_run_id",
        ]
        .astype(
            str
        )
        .tolist()
    )

    return [
        _build_case(
            DOMAIN_SIMULATION,
            1,
            (
                "How many Simulation Agent events exist in the selected "
                "workflow population?"
            ),
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "agent_events",
            ],
            {
                "simulation_agent_event_count":
                    total_events,
            },
            [],
            [
                str(
                    total_events
                ),
            ],
            [],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            2,
            "How many Simulation Agent runs completed successfully?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "agent_events",
            ],
            {
                "completed_simulation_count":
                    completed_count,
            },
            completed_workflow_ids,
            [
                str(
                    completed_count
                ),
            ],
            [
                "simulation results for skipped runs",
            ],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            3,
            "How many Simulation Agent runs were skipped?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "agent_events",
            ],
            {
                "skipped_simulation_count":
                    skipped_count,
            },
            [],
            [
                str(
                    skipped_count
                ),
            ],
            [],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            4,
            "How many workflows contain a Simulation Agent stage?",
            TASK_AGGREGATION,
            DIFFICULTY_EASY,
            RESPONSE_NUMBER,
            [
                "agent_events",
            ],
            {
                "workflow_count":
                    workflow_count,
            },
            [],
            [
                str(
                    workflow_count
                ),
            ],
            [],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            5,
            "What is the dominant current status of the Simulation Agent?",
            TASK_ENTITY_RANKING,
            DIFFICULTY_MEDIUM,
            RESPONSE_ENTITY,
            [
                "agent_events",
            ],
            {
                "dominant_status":
                    dominant_status,
            },
            (
                [
                    dominant_status
                ]
                if dominant_status
                else []
            ),
            (
                [
                    dominant_status
                ]
                if dominant_status
                else []
            ),
            [],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            6,
            "Why are current Simulation Agent stages being skipped?",
            TASK_SOURCE_ROUTING,
            DIFFICULTY_MEDIUM,
            RESPONSE_STRUCTURED,
            [
                "agent_events",
            ],
            {
                "dominant_skip_reason":
                    dominant_reason,
            },
            [],
            (
                [
                    dominant_reason
                ]
                if dominant_reason
                else []
            ),
            [
                "fabricated simulation engine failure",
            ],
            [
                "agent_events.output_refs",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            7,
            (
                "Can the Copilot report a simulation-predicted revenue uplift "
                "when the Simulation Agent was skipped?"
            ),
            TASK_SIMULATION_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "agent_events",
            ],
            {
                "may_report_simulation_uplift":
                    False,
            },
            [],
            [
                "no linked runtime simulation artifact",
            ],
            [
                "fabricated revenue uplift",
                "fabricated simulation probability",
            ],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            8,
            (
                "Does an executed Action Agent record prove that a simulation "
                "was run beforehand?"
            ),
            TASK_SIMULATION_RESTRAINT,
            DIFFICULTY_HARD,
            RESPONSE_BOOLEAN,
            [
                "agent_events",
                "action_outcomes",
            ],
            {
                "action_execution_proves_simulation":
                    False,
            },
            [],
            [
                "agent-stage evidence must be checked independently",
            ],
            [
                "implicit simulation result",
            ],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            9,
            (
                "Which workflow IDs currently have a completed Simulation Agent "
                "runtime artifact?"
            ),
            TASK_LINEAGE,
            DIFFICULTY_HARD,
            RESPONSE_STRUCTURED,
            [
                "agent_events",
            ],
            {
                "workflow_ids":
                    completed_workflow_ids,
            },
            completed_workflow_ids,
            [
                str(
                    completed_count
                ),
            ],
            [
                "skipped workflows reported as simulated",
            ],
            [
                "agent_events",
            ],
        ),

        _build_case(
            DOMAIN_SIMULATION,
            10,
            (
                "If there is no completed Simulation Agent artifact, should the "
                "Copilot invent a recommended scenario result?"
            ),
            TASK_ANTI_HALLUCINATION,
            DIFFICULTY_HARD,
            RESPONSE_ABSTENTION,
            [
                "agent_events",
            ],
            {
                "invent_scenario_result":
                    False,

                "required_behavior":
                    "state that simulation evidence is unavailable",
            },
            [],
            [
                "simulation evidence unavailable",
            ],
            [
                "fabricated scenario result",
                "fabricated confidence",
                "fabricated ROI",
            ],
            [
                "agent_events",
            ],
            answerable=False,
        ),
    ]


# ============================================================
# SPLIT ASSIGNMENT
# ============================================================


def _target_split_counts(
    total_count: int,
    split_config: Mapping[str, float],
) -> dict[str, int]:
    """
    Largest-remainder exact split allocation.
    """

    names = (
        "train",
        "validation",
        "test",
    )

    raw = {
        name:
            total_count
            *
            float(
                split_config[
                    name
                ]
            )
        for name
        in names
    }

    counts = {
        name:
            int(
                np.floor(
                    raw[
                        name
                    ]
                )
            )
        for name
        in names
    }

    remaining = (
        total_count
        -
        sum(
            counts.values()
        )
    )

    remainder_order = sorted(
        names,
        key=lambda name: (
            -(
                raw[
                    name
                ]
                -
                counts[
                    name
                ]
            ),
            names.index(
                name
            ),
        ),
    )

    for name in remainder_order[
        :remaining
    ]:
        counts[
            name
        ] += 1

    if sum(
        counts.values()
    ) != total_count:
        raise ValueError(
            "Split allocation failed exact total"
        )

    return counts


def _assign_splits(
    questions: pd.DataFrame,
    supported_domains: tuple[str, ...],
    split_config: Mapping[str, float],
) -> pd.DataFrame:
    """
    Assign deterministic TRAIN / VALIDATION / TEST labels.
    """

    targets = _target_split_counts(
        len(
            questions
        ),
        split_config,
    )

    domain_order = {
        domain:
            index
        for index, domain
        in enumerate(
            supported_domains
        )
    }

    work = (
        questions
        .copy()
    )

    work[
        "_domain_order"
    ] = (
        work[
            "domain"
        ]
        .map(
            domain_order
        )
    )

    ordered_indices = (
        work
        .sort_values(
            [
                "case_ordinal",
                "_domain_order",
                "evaluation_case_id",
            ]
        )
        .index
        .tolist()
    )

    train_end = targets[
        "train"
    ]

    validation_end = (
        train_end
        +
        targets[
            "validation"
        ]
    )

    labels: dict[int, str] = {}

    for position, index in enumerate(
        ordered_indices
    ):
        if position < train_end:
            labels[
                index
            ] = SPLIT_TRAIN

        elif position < validation_end:
            labels[
                index
            ] = SPLIT_VALIDATION

        else:
            labels[
                index
            ] = SPLIT_TEST

    work[
        "dataset_split"
    ] = (
        work.index
        .map(
            labels
        )
    )

    return (
        work
        .drop(
            columns=[
                "_domain_order",
            ]
        )
    )


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_evaluation_cases(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    audit_events: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    agent_events: pd.DataFrame,
    action_outcomes: pd.DataFrame,
    manufacturing_timeseries: pd.DataFrame,
    warranty_claims: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate:

        suggested_prompts
        copilot_eval_questions
        copilot_eval_ground_truth
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

        audit_events=
            audit_events,

        workflow_runs=
            workflow_runs,

        agent_events=
            agent_events,

        action_outcomes=
            action_outcomes,

        manufacturing_timeseries=
            manufacturing_timeseries,

        warranty_claims=
            warranty_claims,
    )

    (
        configured_question_count,
        supported_domains,
    ) = _get_copilot_config(
        generation
    )

    split_config = (
        _get_split_config(
            generation
        )
    )

    (
        _,
        generation_end,
        _,
    ) = _get_generation_window(
        generation
    )

    if (
        configured_question_count
        %
        len(
            supported_domains
        )
        !=
        0
    ):
        raise ValueError(
            "Evaluation question count must divide evenly "
            "across supported domains"
        )

    questions_per_domain = (
        configured_question_count
        //
        len(
            supported_domains
        )
    )

    if questions_per_domain != 10:
        raise ValueError(
            "Current golden evaluation catalogue defines exactly "
            "10 cases per supported domain. "
            f"Configured requirement={questions_per_domain}"
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

    seed = int(
        generation.get(
            "seed",
            4172,
        )
    )

    generated_at = (
        generation_end
        -
        pd.Timedelta(
            milliseconds=1
        )
    )

    # ========================================================
    # DOMAIN CASE CATALOGUE
    # ========================================================

    domain_cases: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for domain, governance_domain in (
        GOVERNANCE_DOMAIN_MAP.items()
    ):
        domain_cases[
            domain
        ] = _recommendation_domain_cases(
            copilot_domain=
                domain,

            governance_domain=
                governance_domain,

            recommendations=
                recommendations,

            trust_decisions=
                trust_decisions,

            workflow_runs=
                workflow_runs,

            action_outcomes=
                action_outcomes,
        )

    domain_cases[
        DOMAIN_DEALER
    ] = _dealer_cases(
        recommendations=
            recommendations,

        trust_decisions=
            trust_decisions,

        workflow_runs=
            workflow_runs,

        action_outcomes=
            action_outcomes,
    )

    domain_cases[
        DOMAIN_MANUFACTURING
    ] = _manufacturing_cases(
        manufacturing_timeseries=
            manufacturing_timeseries,
    )

    domain_cases[
        DOMAIN_WARRANTY
    ] = _warranty_cases(
        warranty_claims=
            warranty_claims,
    )

    domain_cases[
        DOMAIN_COMPLIANCE
    ] = _compliance_cases(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        audit_events=
            audit_events,
    )

    domain_cases[
        DOMAIN_SIMULATION
    ] = _simulation_cases(
        agent_events=
            agent_events,
    )

    # ========================================================
    # BUILD QUESTIONS + GROUND TRUTH
    # ========================================================

    question_rows: list[
        dict[str, Any]
    ] = []

    truth_rows: list[
        dict[str, Any]
    ] = []

    case_sequence = 0

    for domain in supported_domains:
        cases = domain_cases.get(
            domain
        )

        if cases is None:
            raise ValueError(
                f"No evaluation catalogue for domain={domain}"
            )

        if len(
            cases
        ) != questions_per_domain:
            raise ValueError(
                f"{domain}: expected {questions_per_domain} cases, "
                f"generated {len(cases)}"
            )

        for case in cases:
            case_sequence += 1

            evaluation_case_id = (
                generate_id(
                    "COPEVAL_SYN",
                    case_sequence,
                    width=5,
                )
            )

            question_rows.append(
                {
                    "evaluation_case_id":
                        evaluation_case_id,

                    "domain":
                        domain,

                    "case_ordinal":
                        int(
                            case[
                                "case_ordinal"
                            ]
                        ),

                    "question":
                        case[
                            "question"
                        ],

                    "task_type":
                        case[
                            "task_type"
                        ],

                    "difficulty":
                        case[
                            "difficulty"
                        ],

                    "response_type":
                        case[
                            "response_type"
                        ],

                    "route_tables_json":
                        _canonical_json(
                            case[
                                "route_tables"
                            ]
                        ),

                    "generated_at":
                        generated_at,

                    "seed":
                        seed,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

            truth_rows.append(
                {
                    "evaluation_case_id":
                        evaluation_case_id,

                    "domain":
                        domain,

                    "answerable":
                        bool(
                            case[
                                "answerable"
                            ]
                        ),

                    "expected_answer_json":
                        _canonical_json(
                            case[
                                "expected_answer"
                            ]
                        ),

                    "expected_entities_json":
                        _canonical_json(
                            case[
                                "expected_entities"
                            ]
                        ),

                    "must_include_facts_json":
                        _canonical_json(
                            case[
                                "must_include_facts"
                            ]
                        ),

                    "must_not_invent_json":
                        _canonical_json(
                            case[
                                "must_not_invent"
                            ]
                        ),

                    "source_refs_json":
                        _canonical_json(
                            case[
                                "source_refs"
                            ]
                        ),

                    "evaluation_notes":
                        case[
                            "evaluation_notes"
                        ],

                    "generated_at":
                        generated_at,

                    "seed":
                        seed,

                    "data_origin":
                        data_origin,

                    "generator_version":
                        generator_version,
                }
            )

    questions = pd.DataFrame(
        question_rows
    )

    ground_truth = pd.DataFrame(
        truth_rows
    )

    questions = _assign_splits(
        questions=
            questions,

        supported_domains=
            supported_domains,

        split_config=
            split_config,
    )

    ground_truth = (
        ground_truth
        .merge(
            questions[
                [
                    "evaluation_case_id",
                    "dataset_split",
                ]
            ],
            on="evaluation_case_id",
            how="left",
            validate="one_to_one",
        )
    )

    # ========================================================
    # SUGGESTED PROMPTS
    # ========================================================

    prompt_rows: list[
        dict[str, Any]
    ] = []

    for display_order, domain in enumerate(
        supported_domains,
        start=1,
    ):
        first_case = (
            questions.loc[
                questions[
                    "domain"
                ]
                ==
                domain
            ]
            .sort_values(
                "case_ordinal"
            )
            .iloc[
                0
            ]
        )

        prompt_rows.append(
            {
                "prompt_id":
                    generate_id(
                        "COPPROMPT_SYN",
                        display_order,
                        width=3,
                    ),

                "domain":
                    domain,

                "prompt_text":
                    str(
                        first_case[
                            "question"
                        ]
                    ),

                "display_order":
                    display_order,

                "enabled":
                    True,

                "data_origin":
                    data_origin,

                "generator_version":
                    generator_version,
            }
        )

    suggested_prompts = pd.DataFrame(
        prompt_rows
    )

    validate_evaluation_cases(
        suggested_prompts=
            suggested_prompts,

        questions=
            questions,

        ground_truth=
            ground_truth,

        generation=
            generation,
    )

    return (
        suggested_prompts,
        questions,
        ground_truth,
    )


# ============================================================
# PUBLIC ALIAS
# ============================================================


def generate_copilot_evaluation_cases(
    recommendations: pd.DataFrame,
    compliance_checks: pd.DataFrame,
    trust_decisions: pd.DataFrame,
    audit_events: pd.DataFrame,
    workflow_runs: pd.DataFrame,
    agent_events: pd.DataFrame,
    action_outcomes: pd.DataFrame,
    manufacturing_timeseries: pd.DataFrame,
    warranty_claims: pd.DataFrame,
    generation: Mapping[str, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Alias for generate_all.py orchestration.
    """

    return generate_evaluation_cases(
        recommendations=
            recommendations,

        compliance_checks=
            compliance_checks,

        trust_decisions=
            trust_decisions,

        audit_events=
            audit_events,

        workflow_runs=
            workflow_runs,

        agent_events=
            agent_events,

        action_outcomes=
            action_outcomes,

        manufacturing_timeseries=
            manufacturing_timeseries,

        warranty_claims=
            warranty_claims,

        generation=
            generation,
    )


# ============================================================
# OUTPUT VALIDATION
# ============================================================


def validate_evaluation_cases(
    suggested_prompts: pd.DataFrame,
    questions: pd.DataFrame,
    ground_truth: pd.DataFrame,
    generation: Mapping[str, Any],
) -> None:
    """
    Validate full Copilot evaluation layer.
    """

    (
        expected_count,
        supported_domains,
    ) = _get_copilot_config(
        generation
    )

    split_config = (
        _get_split_config(
            generation
        )
    )

    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    question_required = {
        "evaluation_case_id",
        "domain",
        "case_ordinal",
        "question",
        "task_type",
        "difficulty",
        "response_type",
        "route_tables_json",
        "dataset_split",
        "generated_at",
        "seed",
        "data_origin",
        "generator_version",
    }

    truth_required = {
        "evaluation_case_id",
        "domain",
        "answerable",
        "expected_answer_json",
        "expected_entities_json",
        "must_include_facts_json",
        "must_not_invent_json",
        "source_refs_json",
        "evaluation_notes",
        "generated_at",
        "seed",
        "data_origin",
        "generator_version",
        "dataset_split",
    }

    prompt_required = {
        "prompt_id",
        "domain",
        "prompt_text",
        "display_order",
        "enabled",
        "data_origin",
        "generator_version",
    }

    for name, dataframe, required in (
        (
            "questions",
            questions,
            question_required,
        ),
        (
            "ground_truth",
            ground_truth,
            truth_required,
        ),
        (
            "suggested_prompts",
            suggested_prompts,
            prompt_required,
        ),
    ):
        missing = (
            required
            -
            set(
                dataframe.columns
            )
        )

        if missing:
            raise ValueError(
                f"{name} missing columns: "
                +
                ", ".join(
                    sorted(
                        missing
                    )
                )
            )

    # ========================================================
    # COUNTS
    # ========================================================

    if len(
        questions
    ) != expected_count:
        raise ValueError(
            "Question count mismatch. "
            f"Expected={expected_count}, actual={len(questions)}"
        )

    if len(
        ground_truth
    ) != expected_count:
        raise ValueError(
            "Ground-truth count must equal question count"
        )

    if len(
        suggested_prompts
    ) != len(
        supported_domains
    ):
        raise ValueError(
            "Expected one suggested prompt per supported domain"
        )

    # ========================================================
    # IDS
    # ========================================================

    if (
        questions[
            "evaluation_case_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate Copilot evaluation-case IDs"
        )

    if (
        ground_truth[
            "evaluation_case_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate Copilot ground-truth case IDs"
        )

    if (
        suggested_prompts[
            "prompt_id"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate suggested prompt IDs"
        )

    question_ids = set(
        questions[
            "evaluation_case_id"
        ]
        .astype(
            str
        )
    )

    truth_ids = set(
        ground_truth[
            "evaluation_case_id"
        ]
        .astype(
            str
        )
    )

    if question_ids != truth_ids:
        raise ValueError(
            "Question and ground-truth case coverage mismatch"
        )

    # ========================================================
    # DOMAINS
    # ========================================================

    question_domains = set(
        questions[
            "domain"
        ]
        .astype(
            str
        )
    )

    if question_domains != set(
        supported_domains
    ):
        raise ValueError(
            "Question domains do not match configured domains"
        )

    expected_per_domain = (
        expected_count
        //
        len(
            supported_domains
        )
    )

    domain_counts = (
        questions[
            "domain"
        ]
        .value_counts()
    )

    if not (
        domain_counts
        ==
        expected_per_domain
    ).all():
        raise ValueError(
            "Evaluation cases are not evenly distributed by domain"
        )

    # ========================================================
    # SPLITS
    # ========================================================

    split_targets = _target_split_counts(
        expected_count,
        split_config,
    )

    actual_split_counts = (
        questions[
            "dataset_split"
        ]
        .value_counts()
    )

    expected_split_values = {
        SPLIT_TRAIN:
            split_targets[
                "train"
            ],

        SPLIT_VALIDATION:
            split_targets[
                "validation"
            ],

        SPLIT_TEST:
            split_targets[
                "test"
            ],
    }

    for split_name, expected in (
        expected_split_values.items()
    ):
        actual = int(
            actual_split_counts.get(
                split_name,
                0,
            )
        )

        if actual != expected:
            raise ValueError(
                f"{split_name} split mismatch. "
                f"Expected={expected}, actual={actual}"
            )

    invalid_splits = (
        set(
            questions[
                "dataset_split"
            ]
            .astype(
                str
            )
        )
        -
        VALID_SPLITS
    )

    if invalid_splits:
        raise ValueError(
            "Invalid dataset split labels"
        )

    # ========================================================
    # JSON
    # ========================================================

    for row in questions.itertuples(
        index=False
    ):
        route_tables = json.loads(
            row.route_tables_json
        )

        if not isinstance(
            route_tables,
            list,
        ):
            raise ValueError(
                f"{row.evaluation_case_id}: "
                "route_tables_json must be a JSON list"
            )

        if not route_tables:
            raise ValueError(
                f"{row.evaluation_case_id}: "
                "evaluation case has no source route"
            )

    for row in ground_truth.itertuples(
        index=False
    ):
        expected_answer = json.loads(
            row.expected_answer_json
        )

        expected_entities = json.loads(
            row.expected_entities_json
        )

        must_include = json.loads(
            row.must_include_facts_json
        )

        must_not_invent = json.loads(
            row.must_not_invent_json
        )

        source_refs = json.loads(
            row.source_refs_json
        )

        if not isinstance(
            expected_answer,
            dict,
        ):
            raise ValueError(
                f"{row.evaluation_case_id}: "
                "expected_answer_json must be an object"
            )

        for field_name, value in (
            (
                "expected_entities_json",
                expected_entities,
            ),
            (
                "must_include_facts_json",
                must_include,
            ),
            (
                "must_not_invent_json",
                must_not_invent,
            ),
            (
                "source_refs_json",
                source_refs,
            ),
        ):
            if not isinstance(
                value,
                list,
            ):
                raise ValueError(
                    f"{row.evaluation_case_id}: "
                    f"{field_name} must be a JSON list"
                )

    # ========================================================
    # RUNTIME / GROUND-TRUTH SEPARATION
    # ========================================================

    leakage_columns = [
        column
        for column
        in questions.columns
        if any(
            fragment
            in column.lower()
            for fragment
            in FORBIDDEN_RUNTIME_COLUMN_FRAGMENTS
        )
    ]

    if leakage_columns:
        raise ValueError(
            "Hidden Copilot ground truth leaked into runtime dataset: "
            +
            ", ".join(
                leakage_columns
            )
        )

    # ========================================================
    # QUESTION QUALITY
    # ========================================================

    if (
        questions[
            "question"
        ]
        .isna()
        .any()
    ):
        raise ValueError(
            "Copilot question cannot be null"
        )

    if (
        questions[
            "question"
        ]
        .astype(
            str
        )
        .str.strip()
        .eq("")
        .any()
    ):
        raise ValueError(
            "Copilot question cannot be empty"
        )

    if (
        questions[
            "question"
        ]
        .duplicated()
        .any()
    ):
        raise ValueError(
            "Duplicate Copilot evaluation questions found"
        )

    # ========================================================
    # QUESTION / TRUTH MATCH
    # ========================================================

    merged = (
        questions[
            [
                "evaluation_case_id",
                "domain",
                "dataset_split",
            ]
        ]
        .merge(
            ground_truth[
                [
                    "evaluation_case_id",
                    "domain",
                    "dataset_split",
                ]
            ],
            on="evaluation_case_id",
            suffixes=(
                "_question",
                "_truth",
            ),
            validate="one_to_one",
        )
    )

    if not (
        merged[
            "domain_question"
        ]
        ==
        merged[
            "domain_truth"
        ]
    ).all():
        raise ValueError(
            "Question / ground-truth domain mismatch"
        )

    if not (
        merged[
            "dataset_split_question"
        ]
        ==
        merged[
            "dataset_split_truth"
        ]
    ).all():
        raise ValueError(
            "Question / ground-truth split mismatch"
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
            "suggested_prompts",
            suggested_prompts,
        ),
        (
            "questions",
            questions,
        ),
        (
            "ground_truth",
            ground_truth,
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


# ============================================================
# LOCAL MANUFACTURING FIXTURE
# ============================================================


def _build_local_manufacturing_fixture(
    generation: Mapping[str, Any],
) -> pd.DataFrame:
    """
    Minimal local-only manufacturing fixture.

    Public generator never uses this fixture.
    """

    (
        start,
        _,
        _,
    ) = _get_generation_window(
        generation
    )

    rows: list[
        dict[str, Any]
    ] = []

    for machine_index in range(
        1,
        3,
    ):
        for hour in range(
            48
        ):
            rows.append(
                {
                    "timestamp":
                        (
                            start
                            +
                            pd.Timedelta(
                                hours=hour
                            )
                        ),

                    "plant_id":
                        "PLANT_LOCAL_01",

                    "production_line_id":
                        "LINE_LOCAL_01",

                    "machine_id":
                        f"MACHINE_LOCAL_{machine_index:02d}",
                }
            )

    return pd.DataFrame(
        rows
    )


# ============================================================
# UPDATED LOCAL WARRANTY FIXTURE
# ============================================================


def _build_local_warranty_fixture() -> pd.DataFrame:
    """
    Minimal local-only warranty fixture using the SAME column
    names required from the real frozen warranty generator.

    This prevents local validation from hiding schema drift.
    """

    rows: list[
        dict[str, Any]
    ] = []

    statuses = (
        "APPROVED",
        "APPROVED",
        "MANUAL_REVIEW",
        "REJECTED",
    )

    for sequence in range(
        1,
        21,
    ):
        status = statuses[
            (
                sequence
                -
                1
            )
            %
            len(
                statuses
            )
        ]

        claim_amount_inr = float(
            10000
            +
            (
                sequence
                *
                1000
            )
        )

        approved_amount_inr = (
            claim_amount_inr
            *
            0.80
            if status
            ==
            "APPROVED"
            else 0.0
        )

        rows.append(
            {
                "warranty_claim_id":
                    f"WARRANTY_LOCAL_{sequence:04d}",

                "production_batch_id":
                    f"BATCH_LOCAL_{((sequence - 1) % 5) + 1:03d}",

                "primary_supplier_lot_id":
                    f"LOT_LOCAL_{((sequence - 1) % 8) + 1:03d}",

                "claim_amount_inr":
                    claim_amount_inr,

                "approved_amount_inr":
                    approved_amount_inr,

                "claim_status":
                    status,
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# LOCAL MODULE VALIDATION
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

    from data.generators.agents.workflow import (
        generate_workflow,
    )

    generation_config = (
        load_generation_config()
    )

    (
        configured_question_count,
        supported_domains,
    ) = _get_copilot_config(
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

    manufacturing_df = (
        _build_local_manufacturing_fixture(
            generation_config
        )
    )

    warranty_df = (
        _build_local_warranty_fixture()
    )

    # ========================================================
    # CONFIG
    # ========================================================

    print(
        "\n=== COPILOT EVALUATION CONFIG ===\n"
    )

    print(
        "Configured evaluation questions:",
        configured_question_count,
    )

    print(
        "Supported domains:",
        len(
            supported_domains
        ),
    )

    for domain in supported_domains:
        print(
            " -",
            domain,
        )

    # ========================================================
    # GENERATE
    # ========================================================

    (
        suggested_prompts_df,
        evaluation_questions_df,
        evaluation_ground_truth_df,
    ) = generate_evaluation_cases(
        recommendations=
            recommendations_df,

        compliance_checks=
            compliance_checks_df,

        trust_decisions=
            trust_decisions_df,

        audit_events=
            audit_events_df,

        workflow_runs=
            workflow_runs_df,

        agent_events=
            agent_events_df,

        action_outcomes=
            action_outcomes_df,

        manufacturing_timeseries=
            manufacturing_df,

        warranty_claims=
            warranty_df,

        generation=
            generation_config,
    )

    # ========================================================
    # DETERMINISM
    # ========================================================

    (
        suggested_prompts_repeat_df,
        evaluation_questions_repeat_df,
        evaluation_ground_truth_repeat_df,
    ) = generate_evaluation_cases(
        recommendations=
            recommendations_df,

        compliance_checks=
            compliance_checks_df,

        trust_decisions=
            trust_decisions_df,

        audit_events=
            audit_events_df,

        workflow_runs=
            workflow_runs_df,

        agent_events=
            agent_events_df,

        action_outcomes=
            action_outcomes_df,

        manufacturing_timeseries=
            manufacturing_df,

        warranty_claims=
            warranty_df,

        generation=
            generation_config,
    )

    pd.testing.assert_frame_equal(
        suggested_prompts_df,
        suggested_prompts_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        evaluation_questions_df,
        evaluation_questions_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        evaluation_ground_truth_df,
        evaluation_ground_truth_repeat_df,
        check_dtype=True,
        check_exact=True,
    )

    # ========================================================
    # DOMAIN MIX
    # ========================================================

    print(
        "\n=== COPILOT QUESTIONS BY DOMAIN ===\n"
    )

    print(
        evaluation_questions_df
        .groupby(
            "domain",
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size":
                    "questions"
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
    # SPLITS
    # ========================================================

    print(
        "\n=== COPILOT DATASET SPLITS ===\n"
    )

    print(
        evaluation_questions_df[
            "dataset_split"
        ]
        .value_counts()
        .rename_axis(
            "dataset_split"
        )
        .reset_index(
            name="questions"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # TASK MIX
    # ========================================================

    print(
        "\n=== COPILOT TASK TYPE MIX ===\n"
    )

    print(
        evaluation_questions_df[
            "task_type"
        ]
        .value_counts()
        .rename_axis(
            "task_type"
        )
        .reset_index(
            name="questions"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # DIFFICULTY MIX
    # ========================================================

    print(
        "\n=== COPILOT DIFFICULTY MIX ===\n"
    )

    print(
        evaluation_questions_df[
            "difficulty"
        ]
        .value_counts()
        .rename_axis(
            "difficulty"
        )
        .reset_index(
            name="questions"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # ANSWERABILITY
    # ========================================================

    print(
        "\n=== COPILOT ANSWERABILITY ===\n"
    )

    print(
        evaluation_ground_truth_df[
            "answerable"
        ]
        .value_counts()
        .rename_axis(
            "answerable"
        )
        .reset_index(
            name="questions"
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # QUESTION SAMPLE
    # ========================================================

    print(
        "\n=== COPILOT QUESTION SAMPLE ===\n"
    )

    print(
        evaluation_questions_df[
            [
                "evaluation_case_id",
                "domain",
                "dataset_split",
                "task_type",
                "difficulty",
                "question",
            ]
        ]
        .head(
            30
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # GROUND TRUTH SAMPLE
    # ========================================================

    print(
        "\n=== COPILOT GROUND-TRUTH SAMPLE ===\n"
    )

    print(
        evaluation_ground_truth_df[
            [
                "evaluation_case_id",
                "domain",
                "answerable",
                "expected_answer_json",
                "expected_entities_json",
                "must_not_invent_json",
            ]
        ]
        .head(
            20
        )
        .to_string(
            index=False
        )
    )

    # ========================================================
    # SUGGESTED PROMPTS
    # ========================================================

    print(
        "\n=== SUGGESTED PROMPTS ===\n"
    )

    print(
        suggested_prompts_df[
            [
                "prompt_id",
                "domain",
                "prompt_text",
            ]
        ]
        .to_string(
            index=False
        )
    )

    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    print(
        "\n=== COPILOT EVALUATION VALIDATION ===\n"
    )

    print(
        "Suggested prompts:",
        len(
            suggested_prompts_df
        ),
    )

    print(
        "Evaluation questions:",
        len(
            evaluation_questions_df
        ),
    )

    print(
        "Ground-truth rows:",
        len(
            evaluation_ground_truth_df
        ),
    )

    print(
        "Unique evaluation-case IDs:",
        evaluation_questions_df[
            "evaluation_case_id"
        ]
        .nunique(),
    )

    print(
        "Domains represented:",
        evaluation_questions_df[
            "domain"
        ]
        .nunique(),
    )

    print(
        "Duplicate questions:",
        int(
            evaluation_questions_df[
                "question"
            ]
            .duplicated()
            .sum()
        ),
    )

    print(
        "TRAIN questions:",
        int(
            (
                evaluation_questions_df[
                    "dataset_split"
                ]
                ==
                SPLIT_TRAIN
            )
            .sum()
        ),
    )

    print(
        "VALIDATION questions:",
        int(
            (
                evaluation_questions_df[
                    "dataset_split"
                ]
                ==
                SPLIT_VALIDATION
            )
            .sum()
        ),
    )

    print(
        "TEST questions:",
        int(
            (
                evaluation_questions_df[
                    "dataset_split"
                ]
                ==
                SPLIT_TEST
            )
            .sum()
        ),
    )

    runtime_leakage = [
        column
        for column
        in evaluation_questions_df.columns
        if any(
            fragment
            in column.lower()
            for fragment
            in FORBIDDEN_RUNTIME_COLUMN_FRAGMENTS
        )
    ]

    print(
        "Runtime ground-truth leakage:",
        runtime_leakage,
    )

    print(
        "Deterministic rerun:",
        "PASS",
    )

    print(
        "\nGenerated "
        f"{len(evaluation_questions_df)} Copilot evaluation questions "
        "with separate evaluator-only ground truth successfully."
    )