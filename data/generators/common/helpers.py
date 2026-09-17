"""
General helper utilities for the Mahindra AI Nexus
Synthetic Data Factory.

Responsibilities:
- Locate project/data/config directories.
- Load generation.yaml, scenarios.yaml and distributions.yaml.
- Access nested configuration values.
- Validate probabilities/weights.
- Build deterministic configuration hashes.
- Create required directories.

This module does NOT generate business data.
"""

from __future__ import annotations

import hashlib
import json

from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


# ------------------------------------------------------------------
# PROJECT PATHS
#
# helpers.py
# data/generators/common/helpers.py
#
# parents[0] -> common
# parents[1] -> generators
# parents[2] -> data
# ------------------------------------------------------------------

DATA_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

PROJECT_ROOT = DATA_ROOT.parent

CONFIG_DIR = (
    DATA_ROOT
    / "config"
)

SYNTHETIC_DIR = (
    DATA_ROOT
    / "synthetic"
)

GROUND_TRUTH_DIR = (
    DATA_ROOT
    / "ground_truth"
)


def load_yaml(
    path: str | Path,
) -> dict[str, Any]:
    """
    Load a YAML file safely.

    Returns an empty dictionary if the YAML file itself is empty.
    """

    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"YAML configuration file not found: "
            f"{file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Expected a file but received: "
            f"{file_path}"
        )

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        content = yaml.safe_load(
            file
        )

    if content is None:
        return {}

    if not isinstance(
        content,
        dict,
    ):
        raise ValueError(
            f"Expected YAML root to be a mapping: "
            f"{file_path}"
        )

    return content


def load_generation_config() -> dict[str, Any]:
    """
    Load data/config/generation.yaml
    """

    return load_yaml(
        CONFIG_DIR
        / "generation.yaml"
    )


def load_scenario_config() -> dict[str, Any]:
    """
    Load data/config/scenarios.yaml
    """

    return load_yaml(
        CONFIG_DIR
        / "scenarios.yaml"
    )


def load_distribution_config() -> dict[str, Any]:
    """
    Load data/config/distributions.yaml
    """

    return load_yaml(
        CONFIG_DIR
        / "distributions.yaml"
    )


def load_all_configs() -> dict[str, dict[str, Any]]:
    """
    Load all three synthetic-data configuration files.

    Returns:

        {
            "generation": {...},
            "scenarios": {...},
            "distributions": {...}
        }
    """

    return {
        "generation":
            load_generation_config(),

        "scenarios":
            load_scenario_config(),

        "distributions":
            load_distribution_config(),
    }


_MISSING = object()


def deep_get(
    mapping: Mapping[str, Any],
    path: str | Sequence[str],
    default: Any = _MISSING,
) -> Any:
    """
    Read a nested value from a configuration dictionary.

    Example:

        deep_get(
            generation,
            "manufacturing.pcmci.tau_max"
        )

    or:

        deep_get(
            generation,
            ["manufacturing", "pcmci", "tau_max"]
        )
    """

    if isinstance(path, str):
        keys = path.split(".")
    else:
        keys = list(path)

    current: Any = mapping

    for key in keys:

        if (
            not isinstance(
                current,
                Mapping,
            )
            or key not in current
        ):

            if default is not _MISSING:
                return default

            raise KeyError(
                "Missing configuration key: "
                + ".".join(keys)
            )

        current = current[key]

    return current


def validate_probability(
    value: float,
    name: str = "probability",
) -> float:
    """
    Validate a probability in [0, 1].
    """

    value = float(value)

    if not 0 <= value <= 1:
        raise ValueError(
            f"{name} must be between 0 and 1. "
            f"Received {value}."
        )

    return value


def normalize_weights(
    weights: Sequence[float],
) -> list[float]:
    """
    Normalize weights so they sum to 1.
    """

    if not weights:
        raise ValueError(
            "weights cannot be empty"
        )

    numeric_weights = [
        float(value)
        for value in weights
    ]

    if any(
        value < 0
        for value in numeric_weights
    ):
        raise ValueError(
            "weights cannot contain negative values"
        )

    total = sum(
        numeric_weights
    )

    if total <= 0:
        raise ValueError(
            "weights must have a positive sum"
        )

    return [
        value / total
        for value in numeric_weights
    ]


def ensure_directory(
    path: str | Path,
) -> Path:
    """
    Create a directory if it does not already exist.
    """

    directory = Path(path)

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


def ensure_parent_directory(
    file_path: str | Path,
) -> Path:
    """
    Ensure the parent directory for a file exists.
    """

    path = Path(
        file_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def resolve_project_path(
    path: str | Path,
) -> Path:
    """
    Resolve a path relative to the project root.

    Example configuration:

        data/synthetic/causal/file.csv

    becomes:

        <project_root>/data/synthetic/causal/file.csv
    """

    value = Path(path)

    if value.is_absolute():
        return value

    return (
        PROJECT_ROOT
        / value
    ).resolve()


def config_hash(
    *configs: Mapping[str, Any],
) -> str:
    """
    Create a deterministic SHA-256 hash from one or more
    configuration dictionaries.

    Useful for dataset manifests:

        dataset_run_id
        seed
        generator_version
        config_hash
    """

    serialized = json.dumps(
        configs,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def validate_required_keys(
    mapping: Mapping[str, Any],
    required_keys: Sequence[str],
    context: str = "configuration",
) -> None:
    """
    Validate that required keys exist in a dictionary.
    """

    missing = [
        key
        for key in required_keys
        if key not in mapping
    ]

    if missing:
        raise KeyError(
            f"Missing required keys in {context}: "
            f"{', '.join(missing)}"
        )