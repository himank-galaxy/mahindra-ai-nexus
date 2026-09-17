"""
Seed utilities for the Mahindra AI Nexus Synthetic Data Factory.

Purpose:
- Make synthetic-data generation reproducible.
- Ensure Python's random module and NumPy use the same base seed.
- Allow individual modules to derive their own deterministic seeds.
"""

from __future__ import annotations

import hashlib
import os
import random

import numpy as np


def set_seed(seed: int) -> int:
    """
    Set the global random seed for Python and NumPy.

    Example:
        set_seed(4172)

    Running the generators again with the same seed should produce
    the same synthetic data, assuming the generation logic is unchanged.
    """

    if not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    if seed < 0:
        raise ValueError("seed must be >= 0")

    # Useful for subprocesses started after this point.
    os.environ["PYTHONHASHSEED"] = str(seed)

    random.seed(seed)
    np.random.seed(seed)

    return seed


def derive_seed(base_seed: int, namespace: str) -> int:
    """
    Create a deterministic child seed for a specific generator/module.

    Example:
        base_seed = 4172

        auto_seed = derive_seed(base_seed, "auto")
        finance_seed = derive_seed(base_seed, "finance")
        logistics_seed = derive_seed(base_seed, "logistics")

    This prevents one module from needing to reuse arbitrary hardcoded seeds.
    """

    if not isinstance(base_seed, int):
        raise TypeError("base_seed must be an integer")

    if not namespace or not isinstance(namespace, str):
        raise ValueError("namespace must be a non-empty string")

    raw = f"{base_seed}:{namespace}".encode("utf-8")

    digest = hashlib.sha256(raw).digest()

    # First 4 bytes gives a 32-bit seed.
    return int.from_bytes(digest[:4], byteorder="big", signed=False)


def make_rng(seed: int) -> np.random.Generator:
    """
    Create an independent NumPy Generator.

    This is useful when a generator should have its own deterministic
    random stream.

    Example:
        rng = make_rng(derive_seed(4172, "manufacturing"))
    """

    if not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    if seed < 0:
        raise ValueError("seed must be >= 0")

    return np.random.default_rng(seed)