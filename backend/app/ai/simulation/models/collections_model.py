"""Collections trained models: recovery/channel/offer response, roll-forward risk.

Recovery probability, channel response, and offer response are one
question, not three: given a customer's real delinquency state, how does
the choice of channel and offer change the probability of payment after
contact. Channel and offer are categorical features of ONE classifier
(reusing the mixed numeric+categorical fitting in
app/ai/simulation/models/logit.py, the same code Auto Sales uses), fit on
the real ``collection_interactions`` history with a genuine recorded
outcome (``payment_after_contact``) — unlike Auto Sales/Dealer
Allocation, this domain has no missing-history gap.

Roll-forward risk is a second, separate classifier: whether a case
resolves (inverse: keeps rolling forward), from loan-origination features
known before any delinquency occurred.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from app.ai.simulation.models.logit import FittedLogit, fit_logit
from app.core.errors import DomainValidationError
from app.repositories.collections_simulation import RISK_TO_DPD_RANGE, CollectionsSimulationRepository

MIN_TRAINING_ROWS = 50
MIN_COHORT_SIZE = 20

RECOVERY_NUMERIC_FEATURES: list[str] = [
    "dpd_at_interaction",
    "arrears_at_interaction_inr",
    "outstanding_principal_at_interaction_inr",
]
RECOVERY_CATEGORICAL_FEATURES: list[str] = ["channel", "offer_type"]

ROLL_FORWARD_FEATURES: list[str] = [
    "principal_inr",
    "interest_rate_pct",
    "debt_service_ratio_at_origination",
    "secured",
]

FRIENDLY_NAMES: dict[str, str] = {
    "dpd_at_interaction": "Days past due at contact",
    "arrears_at_interaction_inr": "Arrears amount",
    "outstanding_principal_at_interaction_inr": "Outstanding principal",
    "principal_inr": "Loan principal",
    "interest_rate_pct": "Interest rate",
    "debt_service_ratio_at_origination": "Debt-service ratio at origination",
    "secured": "Secured loan",
}


@dataclass(frozen=True)
class CollectionsModels:
    recovery: FittedLogit
    roll_forward: FittedLogit
    interaction_frame: pd.DataFrame
    case_frame: pd.DataFrame

    def cohort_recovery_features(self, risk: str) -> tuple[dict[str, float], int]:
        low, high = RISK_TO_DPD_RANGE[risk]
        cohort = self.interaction_frame[
            (self.interaction_frame["dpd_at_interaction"] >= low)
            & (self.interaction_frame["dpd_at_interaction"] <= high)
        ]
        source = cohort if len(cohort) >= MIN_COHORT_SIZE else self.interaction_frame
        return {feature: float(source[feature].mean()) for feature in RECOVERY_NUMERIC_FEATURES}, len(cohort)

    def cohort_roll_forward_features(self, risk: str) -> tuple[dict[str, float], int]:
        low, high = RISK_TO_DPD_RANGE[risk]
        cohort = self.case_frame[(self.case_frame["current_dpd"] >= low) & (self.case_frame["current_dpd"] <= high)]
        source = cohort if len(cohort) >= MIN_COHORT_SIZE else self.case_frame
        return {feature: float(source[feature].mean()) for feature in ROLL_FORWARD_FEATURES}, len(cohort)


_cache: CollectionsModels | None = None
_lock = asyncio.Lock()


def reset_cache_for_tests() -> None:
    """Clear the in-process model cache — test isolation only, never called at runtime."""
    global _cache
    _cache = None


async def get_or_train_models(repo: CollectionsSimulationRepository) -> CollectionsModels:
    global _cache
    if _cache is not None:
        return _cache
    async with _lock:
        if _cache is not None:
            return _cache
        interaction_frame = await repo.load_interaction_frame()
        case_frame = await repo.load_case_resolution_frame()
        if (
            len(interaction_frame) < MIN_TRAINING_ROWS
            or "payment_after_contact" not in interaction_frame.columns
            or interaction_frame["payment_after_contact"].nunique() < 2
        ):
            raise DomainValidationError(
                "Insufficient historical interaction data to train the Collections recovery model.",
                code="insufficient_training_data",
            )
        if len(case_frame) < MIN_TRAINING_ROWS or case_frame["resolved"].nunique() < 2:
            raise DomainValidationError(
                "Insufficient historical case data to train the Collections roll-forward risk model.",
                code="insufficient_training_data",
            )
        recovery = fit_logit(
            interaction_frame,
            RECOVERY_NUMERIC_FEATURES,
            "payment_after_contact",
            categorical_features=RECOVERY_CATEGORICAL_FEATURES,
        )
        roll_forward = fit_logit(case_frame, ROLL_FORWARD_FEATURES, "resolved")
        _cache = CollectionsModels(
            recovery=recovery,
            roll_forward=roll_forward,
            interaction_frame=interaction_frame,
            case_frame=case_frame,
        )
        return _cache
