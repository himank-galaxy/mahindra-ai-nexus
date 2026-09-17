"""Shared mixed numeric+categorical OLS regression fitting.

Mirrors app/ai/simulation/models/logit.py's design (standardized numeric
features plus one-hot categorical contrasts, chronologically split 80/20)
but for a genuine continuous historical target via statsmodels OLS,
rather than a binary outcome. Used by domains that predict a real
continuous quantity — Credit Pricing's ask-price and buyer-interest
regressions — the same factoring rationale as ``logit.py``: fit once,
reuse the prediction/driver-attribution logic everywhere it's needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm


@dataclass(frozen=True)
class FittedOLS:
    features: list[str]
    result: Any  # statsmodels RegressionResultsWrapper
    means: pd.Series
    stds: pd.Series
    holdout_rmse: float
    holdout_r2: float
    train_rows: int
    test_rows: int
    categorical_features: list[str] = ()  # type: ignore[assignment]
    category_levels: dict[str, list[str]] = None  # type: ignore[assignment]

    def predict(
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
        """``(feature, standardized_coefficient, direction)`` sorted by |coefficient| — see ``FittedLogit.numeric_drivers``."""
        params = np.asarray(self.result.params)
        items = [
            (feature, float(coefficient), "positive" if coefficient >= 0 else "negative")
            for feature, coefficient in zip(self.features, params[1 : 1 + len(self.features)], strict=True)
        ]
        return sorted(items, key=lambda item: abs(item[1]), reverse=True)

    def categorical_coefficient(self, feature: str, value: str) -> float | None:
        """Coefficient contrasting ``value`` against the reference level, or
        ``None`` if ``value`` *is* the reference or the feature/value is unrecognized."""
        if feature not in self.category_levels or value not in self.category_levels[feature]:
            return None
        offset = 1 + len(self.features)
        for other_feature in self.categorical_features:
            for level in self.category_levels[other_feature]:
                if other_feature == feature and level == value:
                    return float(np.asarray(self.result.params)[offset])
                offset += 1
        return None


def fit_ols(
    frame: pd.DataFrame,
    features: list[str],
    label: str,
    categorical_features: list[str] | None = None,
) -> FittedOLS:
    categorical_features = categorical_features or []
    frame = frame.copy()
    for feature in features:
        frame[feature] = frame[feature].astype(float)
    frame[label] = frame[label].astype(float)

    split_index = int(len(frame) * 0.8)
    train, test = frame.iloc[:split_index], frame.iloc[split_index:]
    means = train[features].mean()
    stds = train[features].std().replace(0, 1.0)

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

    result = sm.OLS(train[label], design_matrix(train)).fit()

    holdout_rmse, holdout_r2 = 0.0, 0.0
    if len(test) >= 5:
        predicted = result.predict(design_matrix(test))
        residuals = test[label].to_numpy() - predicted
        holdout_rmse = float(np.sqrt(np.mean(residuals**2)))
        total_variance = float(np.var(test[label].to_numpy()))
        holdout_r2 = float(1 - np.var(residuals) / total_variance) if total_variance > 0 else 0.0

    return FittedOLS(
        features=features,
        result=result,
        means=means,
        stds=stds,
        holdout_rmse=holdout_rmse,
        holdout_r2=holdout_r2,
        train_rows=len(train),
        test_rows=len(test),
        categorical_features=categorical_features,
        category_levels=category_levels,
    )
