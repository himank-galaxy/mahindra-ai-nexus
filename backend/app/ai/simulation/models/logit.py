"""Shared mixed numeric+categorical logistic regression fitting.

Plain logistic regression (statsmodels — already a dependency; no new one
added) on standardized numeric features plus one-hot categorical
contrasts, chronologically split 80/20 so the holdout never precedes
training data. Used by every domain that trains a real classifier on a
genuine historical outcome (Auto Sales' conversion/cancellation models,
Collections' recovery model, ...) — factored out once both needed the
same fitting/prediction/driver-attribution logic, rather than duplicating
it per domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm


def roc_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    """Mann-Whitney U form of ROC-AUC — avoids adding scikit-learn for one metric."""
    positive = scores[labels == 1]
    negative = scores[labels == 0]
    if len(positive) == 0 or len(negative) == 0:
        return 0.5
    ranks = pd.Series(np.concatenate([positive, negative])).rank().to_numpy()
    positive_rank_sum = ranks[: len(positive)].sum()
    return float((positive_rank_sum - len(positive) * (len(positive) + 1) / 2) / (len(positive) * len(negative)))


@dataclass(frozen=True)
class FittedLogit:
    features: list[str]
    result: Any  # statsmodels BinaryResultsWrapper
    means: pd.Series
    stds: pd.Series
    holdout_auc: float
    train_rows: int
    test_rows: int
    categorical_features: list[str] = ()  # type: ignore[assignment]
    category_levels: dict[str, list[str]] = None  # type: ignore[assignment]

    def predict_proba(
        self,
        feature_values: dict[str, float],
        categorical_values: dict[str, str] | None = None,
    ) -> float:
        standardized = [(feature_values[f] - self.means[f]) / (self.stds[f] or 1.0) for f in self.features]
        dummies = self._dummy_row(categorical_values or {})
        design = sm.add_constant(np.array([standardized + dummies]), has_constant="add")
        return float(self.result.predict(design)[0])

    def _dummy_row(self, categorical_values: dict[str, str]) -> list[float]:
        row: list[float] = []
        for feature in self.categorical_features:
            value = categorical_values.get(feature)
            row.extend(1.0 if value == level else 0.0 for level in self.category_levels[feature])
        return row

    def numeric_drivers(self) -> list[tuple[str, float, str]]:
        """``(feature, standardized_coefficient, direction)`` sorted by |coefficient|.

        Numeric features apply to every prediction, so ranking them globally
        is meaningful. Categorical coefficients are NOT included here — see
        ``categorical_coefficient`` — because showing an unrelated
        category's contrast as a "top driver" for a run that didn't select
        it would misattribute the effect to the wrong scenario.
        """
        params = np.asarray(self.result.params)
        items = [
            (feature, float(coefficient), "positive" if coefficient >= 0 else "negative")
            for feature, coefficient in zip(self.features, params[1 : 1 + len(self.features)], strict=True)
        ]
        return sorted(items, key=lambda item: abs(item[1]), reverse=True)

    def categorical_coefficient(self, feature: str, value: str) -> float | None:
        """Coefficient contrasting ``value`` against the reference level, or
        ``None`` if ``value`` *is* the reference (no separate effect fitted)
        or the feature/value is unrecognized."""
        if feature not in self.category_levels or value not in self.category_levels[feature]:
            return None
        offset = 1 + len(self.features)
        for other_feature in self.categorical_features:
            for level in self.category_levels[other_feature]:
                if other_feature == feature and level == value:
                    return float(np.asarray(self.result.params)[offset])
                offset += 1
        return None


def fit_logit(
    frame: pd.DataFrame,
    features: list[str],
    label: str,
    categorical_features: list[str] | None = None,
) -> FittedLogit:
    categorical_features = categorical_features or []
    frame = frame.copy()
    for feature in features:
        frame[feature] = frame[feature].astype(float)
    frame[label] = frame[label].astype(float)

    split_index = int(len(frame) * 0.8)
    train, test = frame.iloc[:split_index], frame.iloc[split_index:]
    means = train[features].mean()
    stds = train[features].std().replace(0, 1.0)

    # Reference level = the train split's most frequent category, so the
    # intercept represents the modal cohort and every dummy coefficient is a
    # contrast against it (dropped to avoid the dummy-variable trap).
    category_levels: dict[str, list[str]] = {
        feature: train[feature].value_counts().index.tolist()[1:] for feature in categorical_features
    }

    def design_matrix(part: pd.DataFrame) -> np.ndarray:
        standardized = (part[features] - means) / stds
        blocks = [standardized.to_numpy()]
        for feature in categorical_features:
            for level in category_levels[feature]:
                blocks.append((part[feature] == level).astype(float).to_numpy().reshape(-1, 1))
        combined = np.concatenate(blocks, axis=1) if blocks else standardized.to_numpy()
        return sm.add_constant(combined, has_constant="add")

    result = sm.Logit(train[label], design_matrix(train)).fit(disp=0)

    holdout_auc = 0.5
    if len(test) >= 10 and test[label].nunique() > 1:
        predicted = result.predict(design_matrix(test))
        holdout_auc = roc_auc(test[label].to_numpy(), predicted)

    return FittedLogit(
        features=features,
        result=result,
        means=means,
        stds=stds,
        holdout_auc=holdout_auc,
        train_rows=len(train),
        test_rows=len(test),
        categorical_features=categorical_features,
        category_levels=category_levels,
    )
