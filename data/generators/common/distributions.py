"""
Reusable distribution-sampling utilities.

The purpose of this module is to interpret distribution definitions
from data/config/distributions.yaml.

Individual business generators should call these utilities instead of
implementing their own NumPy/random logic.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np


def _get_rng(
    rng: np.random.Generator | None = None,
):
    """
    Use a supplied NumPy Generator when available.

    If none is supplied, use numpy.random's global generator,
    which is controlled by np.random.seed() from seed.py.
    """

    return rng if rng is not None else np.random


def _scalarize(value: Any) -> Any:
    """
    Convert a NumPy scalar into a normal Python scalar.
    Arrays are returned unchanged.
    """

    if isinstance(value, np.generic):
        return value.item()

    return value


def clip_value(
    value: Any,
    minimum: float | None = None,
    maximum: float | None = None,
):
    """
    Clip a scalar or NumPy array to optional min/max limits.
    """

    if minimum is None and maximum is None:
        return value

    lower = (
        minimum
        if minimum is not None
        else -np.inf
    )

    upper = (
        maximum
        if maximum is not None
        else np.inf
    )

    result = np.clip(
        value,
        lower,
        upper,
    )

    return _scalarize(result)


def weighted_choice(
    values: Sequence[Any],
    weights: Sequence[float] | None = None,
    size: int | None = None,
    rng: np.random.Generator | None = None,
):
    """
    Pick values using optional probability weights.

    Example:

        weighted_choice(
            ["West", "North", "South", "East"],
            [0.30, 0.25, 0.25, 0.20],
        )
    """

    if not values:
        raise ValueError(
            "values cannot be empty"
        )

    generator = _get_rng(rng)

    probabilities = None

    if weights is not None:

        if len(values) != len(weights):
            raise ValueError(
                "values and weights must have equal length"
            )

        weights_array = np.asarray(
            weights,
            dtype=float,
        )

        if np.any(weights_array < 0):
            raise ValueError(
                "weights cannot contain negative values"
            )

        total = weights_array.sum()

        if total <= 0:
            raise ValueError(
                "weights must sum to a positive value"
            )

        probabilities = (
            weights_array / total
        )

    result = generator.choice(
        values,
        size=size,
        p=probabilities,
    )

    return _scalarize(result)


def weighted_choice_from_mapping(
    value_weights: Mapping[Any, float],
    size: int | None = None,
    rng: np.random.Generator | None = None,
):
    """
    Choose directly from a YAML-style mapping.

    Example:

        {
            "West": 0.30,
            "North": 0.25,
            "South": 0.25,
            "East": 0.20
        }
    """

    if not value_weights:
        raise ValueError(
            "value_weights cannot be empty"
        )

    values = list(
        value_weights.keys()
    )

    weights = list(
        value_weights.values()
    )

    return weighted_choice(
        values=values,
        weights=weights,
        size=size,
        rng=rng,
    )


def bernoulli(
    probability: float,
    size: int | None = None,
    rng: np.random.Generator | None = None,
):
    """
    Generate True/False using a probability.

    Example:
        bernoulli(0.65)

    means approximately 65% True across many samples.
    """

    if not 0 <= probability <= 1:
        raise ValueError(
            "probability must be between 0 and 1"
        )

    generator = _get_rng(rng)

    values = (
        generator.random(size)
        < probability
    )

    if size is None:
        return bool(values)

    return values


def sample_distribution(
    spec: Mapping[str, Any],
    size: int | None = None,
    rng: np.random.Generator | None = None,
):
    """
    Sample from a distribution defined in distributions.yaml.

    Supported distributions:

        normal
        lognormal
        beta
        beta_scaled
        discrete_uniform
        uniform
        choice
        categorical

    Example YAML:

        engagement_score:
          distribution: "beta"
          alpha: 3.0
          beta: 2.0
    """

    if not isinstance(spec, Mapping):
        raise TypeError(
            "spec must be a mapping/dictionary"
        )

    distribution = spec.get(
        "distribution"
    )

    if not distribution:
        raise ValueError(
            "distribution specification must contain "
            "'distribution'"
        )

    distribution = (
        str(distribution)
        .strip()
        .lower()
    )

    generator = _get_rng(rng)

    minimum = spec.get("min")
    maximum = spec.get("max")

    # ----------------------------------------------------------
    # NORMAL
    # ----------------------------------------------------------

    if distribution == "normal":

        mean = float(
            spec["mean"]
        )

        std = float(
            spec["std"]
        )

        if std < 0:
            raise ValueError(
                "normal std cannot be negative"
            )

        result = generator.normal(
            loc=mean,
            scale=std,
            size=size,
        )

    # ----------------------------------------------------------
    # LOGNORMAL
    # ----------------------------------------------------------

    elif distribution == "lognormal":

        mean = float(
            spec["mean"]
        )

        sigma = float(
            spec["sigma"]
        )

        if sigma < 0:
            raise ValueError(
                "lognormal sigma cannot be negative"
            )

        result = generator.lognormal(
            mean=mean,
            sigma=sigma,
            size=size,
        )

    # ----------------------------------------------------------
    # BETA
    # ----------------------------------------------------------

    elif distribution == "beta":

        alpha = float(
            spec["alpha"]
        )

        beta = float(
            spec["beta"]
        )

        if alpha <= 0 or beta <= 0:
            raise ValueError(
                "beta alpha and beta must be > 0"
            )

        result = generator.beta(
            alpha,
            beta,
            size=size,
        )

    # ----------------------------------------------------------
    # BETA SCALED
    # ----------------------------------------------------------

    elif distribution == "beta_scaled":

        alpha = float(
            spec["alpha"]
        )

        beta = float(
            spec["beta"]
        )

        scale_min = float(
            spec["min"]
        )

        scale_max = float(
            spec["max"]
        )

        if alpha <= 0 or beta <= 0:
            raise ValueError(
                "beta_scaled alpha and beta must be > 0"
            )

        if scale_max <= scale_min:
            raise ValueError(
                "beta_scaled max must be greater than min"
            )

        raw = generator.beta(
            alpha,
            beta,
            size=size,
        )

        result = (
            scale_min
            + raw
            * (scale_max - scale_min)
        )

        # Already scaled.
        minimum = None
        maximum = None

    # ----------------------------------------------------------
    # DISCRETE UNIFORM
    # ----------------------------------------------------------

    elif distribution == "discrete_uniform":

        low = int(
            spec["min"]
        )

        high = int(
            spec["max"]
        )

        if high < low:
            raise ValueError(
                "discrete_uniform max must be >= min"
            )

        # np.random.randint excludes upper bound,
        # so high + 1 makes max inclusive.
        if isinstance(
            generator,
            np.random.Generator,
        ):
            result = generator.integers(
                low=low,
                high=high + 1,
                size=size,
            )
        else:
            result = generator.randint(
                low=low,
                high=high + 1,
                size=size,
            )

        minimum = None
        maximum = None

    # ----------------------------------------------------------
    # CONTINUOUS UNIFORM
    # ----------------------------------------------------------

    elif distribution == "uniform":

        low = float(
            spec["min"]
        )

        high = float(
            spec["max"]
        )

        if high < low:
            raise ValueError(
                "uniform max must be >= min"
            )

        result = generator.uniform(
            low=low,
            high=high,
            size=size,
        )

        minimum = None
        maximum = None

    # ----------------------------------------------------------
    # CHOICE / CATEGORICAL
    # ----------------------------------------------------------

    elif distribution in {
        "choice",
        "categorical",
    }:

        values = spec.get(
            "values"
        )

        weights = spec.get(
            "weights"
        )

        return weighted_choice(
            values=values,
            weights=weights,
            size=size,
            rng=rng,
        )

    else:
        raise ValueError(
            f"Unsupported distribution: "
            f"{distribution}"
        )

    result = clip_value(
        result,
        minimum=minimum,
        maximum=maximum,
    )

    return _scalarize(result)