"""Simulation engine contract.

Every engine is a pure function ``run(payload) -> result``: no I/O, no
state, deterministic. Future ML-backed engines keep the same surface so
services never change.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

SimIn = TypeVar("SimIn", bound=BaseModel)
SimOut = TypeVar("SimOut", bound=BaseModel)
