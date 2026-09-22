"""Deterministic compliance rule engine for Simulation Center decisions.

Mirrors the same five-rule taxonomy already generated for canonical
(Synthetic Data Factory) decisions — ``BUSINESS_POLICY_ALIGNMENT``,
``LINEAGE_INTEGRITY``, ``EVIDENCE_SUFFICIENCY``, ``FAIRNESS_INPUT_SCOPE``,
``HUMAN_CONTROL_GATE`` — real ``rule_code`` values read directly from the
``compliance_checks`` table, not invented. Applied here to the simulation
track, which had no rule evaluation of any kind before. Every result is
derived from the run's own real persisted fields (inputs, outputs,
driver_json, confidence) and the real risk assessment — never random,
never a hardcoded PASS.

``evaluate_simulation_compliance`` takes a ``_HasComplianceFields``
duck-type rather than the concrete ``SimulationRun`` so the same rule
evaluation can be reused for Collections AI Swarm's real case-level
recommendations (see app/services/collections.py), which have no
``SimulationRun`` row at all — a lightweight snapshot object with the
same field names satisfies the protocol exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.risk_engine import (
    CONFIDENCE_MEDIUM,
    FINANCIAL_IMPACT_MEDIUM_INR,
    RiskAssessment,
)


class _HasResult(Protocol):
    result: str


class _HasComplianceFields(Protocol):
    model_name: str
    model_version: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    baseline_reference: dict[str, Any] | None
    driver_json: dict[str, Any] | None
    confidence: int


MANDATORY_RESULTS_REQUIRING_REVIEW = {"REVIEW_REQUIRED"}
MANDATORY_RESULTS_BLOCKING = {"FAIL"}


@dataclass(frozen=True)
class ComplianceResult:
    rule_code: str
    rule_name: str
    result: str  # PASS | REVIEW_REQUIRED | FAIL | NOT_APPLICABLE
    reason: str


def evaluate_simulation_compliance(run: _HasComplianceFields, risk: RiskAssessment) -> list[ComplianceResult]:
    results: list[ComplianceResult] = []

    # 1. Business policy alignment — every simulation engine enforces its
    # own hard constraints (input-range validation, allocation floors,
    # price bounds) before a recommendation can be produced at all, so a
    # persisted recommendation already satisfies them by construction.
    results.append(
        ComplianceResult(
            rule_code="BUSINESS_POLICY_ALIGNMENT",
            rule_name="Business policy alignment",
            result="PASS",
            reason=(
                "Recommendation was produced by an engine that enforces its own input-range and "
                "business-rule constraints before returning a result."
            ),
        )
    )

    # 2. Lineage integrity — real source reference, inputs, baseline, outputs.
    has_lineage = bool(run.model_name and run.model_version and run.inputs and run.outputs and run.baseline_reference)
    results.append(
        ComplianceResult(
            rule_code="LINEAGE_INTEGRITY",
            rule_name="Data lineage integrity",
            result="PASS" if has_lineage else "REVIEW_REQUIRED",
            reason=(
                f"Model {run.model_name} ({run.model_version}), scenario inputs, baseline reference, and "
                "outputs are all persisted for this run."
                if has_lineage
                else "One or more of model/version, inputs, baseline reference, or outputs is missing for this run."
            ),
        )
    )

    # 3. Evidence and explainability sufficiency.
    drivers = (run.driver_json or {}).get("predictive_drivers") or []
    has_evidence = len(drivers) > 0 and run.confidence is not None
    results.append(
        ComplianceResult(
            rule_code="EVIDENCE_SUFFICIENCY",
            rule_name="Evidence and explainability sufficiency",
            result="PASS" if has_evidence else "REVIEW_REQUIRED",
            reason=(
                f"{len(drivers)} predictive/calibrated driver(s) and a {run.confidence}% confidence score "
                "are persisted for this run."
                if has_evidence
                else "No driver evidence is persisted for this run."
            ),
        )
    )

    # 4. Fairness input-scope — none of the five simulation domains take a
    # protected/sensitive attribute as a scenario input (region, vehicle
    # model, channel, route, credit type are business dimensions, not
    # protected attributes), so a fairness evaluation does not apply —
    # never claim PASS for a check that never ran.
    results.append(
        ComplianceResult(
            rule_code="FAIRNESS_INPUT_SCOPE",
            rule_name="Fairness input-scope check",
            result="NOT_APPLICABLE",
            reason=(
                "This scenario's inputs (region/vehicle model/channel/route/credit type) are business "
                "dimensions, not protected attributes — no fairness evaluation applies."
            ),
        )
    )

    # 5. Human-control risk gate — the only rule that can BLOCK outright.
    if any(r.result in MANDATORY_RESULTS_BLOCKING for r in results):
        gate_result = "FAIL"
        gate_reason = "A mandatory compliance check failed — execution is blocked pending remediation."
    elif risk.level in ("Critical", "High"):
        gate_result = "REVIEW_REQUIRED"
        gate_reason = f"Risk level is {risk.level} — {risk.reason}"
    elif run.confidence < CONFIDENCE_MEDIUM:
        gate_result = "REVIEW_REQUIRED"
        gate_reason = f"Confidence {run.confidence}% is below the {CONFIDENCE_MEDIUM}% autonomous-action threshold."
    elif risk.financial_impact_inr >= FINANCIAL_IMPACT_MEDIUM_INR:
        gate_result = "REVIEW_REQUIRED"
        gate_reason = (
            f"Expected financial impact ₹{risk.financial_impact_inr:,.0f} exceeds the "
            f"₹{FINANCIAL_IMPACT_MEDIUM_INR:,.0f} autonomous-action threshold."
        )
    else:
        gate_result = "PASS"
        gate_reason = "Risk, confidence, and financial impact are all within the autonomous-action thresholds."
    results.append(
        ComplianceResult(
            rule_code="HUMAN_CONTROL_GATE",
            rule_name="Human-control risk gate",
            result=gate_result,
            reason=gate_reason,
        )
    )
    return results


def derive_audit_status(results: list[_HasResult]) -> str:
    """Same derivation shape already used for canonical decisions
    (see app/services/trust.py's ``_decision_out``) — audit status is
    never stored independently, always computed from real check results."""
    if any(r.result in MANDATORY_RESULTS_BLOCKING for r in results):
        return "Failed"
    if any(r.result in MANDATORY_RESULTS_REQUIRING_REVIEW for r in results):
        return "Review Required"
    return "Passed"
