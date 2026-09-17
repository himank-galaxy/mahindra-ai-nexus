"""Catalogue response schemas (mirrors SOLUTION_BUCKETS / SOLUTION_TAGS)."""

from __future__ import annotations

from pydantic import BaseModel


class SolutionOut(BaseModel):
    """One AI solution card inside a bucket."""

    name: str
    problem: str
    solution: str
    diff: str
    impact: str


class BucketOut(BaseModel):
    """Catalogue bucket with its solutions nested under ``items``."""

    name: str
    tag: str
    items: list[SolutionOut]
