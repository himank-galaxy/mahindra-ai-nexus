"""
Configuration for the Warranty Predictive Service.

Mirrors Predictive_Early_Warning_Service/pews_config.py's conventions
exactly: every value overridable via environment variables, prefixed
WPS_ (Warranty Predictive Service) so these can never collide with
PEWS_ or CDS_ variables from the sibling services.

Cluster definitions are NOT redefined here - they're imported directly
from data/generators/auto/service.py's real COMPONENT_ISSUE_MAP, the
same canonical source the actual service_events data was generated
from, so the model's clusters can never drift from what the data
actually contains.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SERVICE_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_ROOT)

# data/generators/* is a plain Python package at the project root (no
# install step) - add the project root to sys.path so
# `from data.generators...` imports work, the same cross-service import
# pattern PEWS already uses to reach Causal_Discovery_Service.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data.generators.auto.service import COMPONENT_ISSUE_MAP  # noqa: E402

CLUSTERS: dict[str, tuple[str, ...]] = {
    component: tuple(issues) for component, issues in COMPONENT_ISSUE_MAP.items()
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


# --- Data sources (read directly - no DB dependency, same as data/scripts) ---

DELIVERIES_PATH = os.path.join(PROJECT_ROOT, "data", "synthetic", "auto", "deliveries.csv")
SERVICE_EVENTS_PATH = os.path.join(PROJECT_ROOT, "data", "synthetic", "auto", "service_events.csv")
WARRANTY_CLAIMS_PATH = os.path.join(PROJECT_ROOT, "data", "synthetic", "auto", "warranty_claims.csv")
INSURANCE_CLAIMS_PATH = os.path.join(PROJECT_ROOT, "data", "synthetic", "auto", "insurance_claims.csv")
TELEMATICS_PATH = os.path.join(PROJECT_ROOT, "data", "synthetic", "causal", "vehicle_telematics_timeseries.csv")

# --- Checkpoint / labeling ---

# Real, timestamped, present for most delivered vehicles - see
# training_data.py for the fallback (60 days post-delivery) used when a
# vehicle never attended First Inspection at all.
CHECKPOINT_FALLBACK_DAYS = _env_int("WPS_CHECKPOINT_FALLBACK_DAYS", 60)

# A cluster with fewer than this many labeled rows is skipped at
# training time (logged, not crashed) rather than fit on noise.
MIN_TRAINING_ROWS = _env_int("WPS_MIN_TRAINING_ROWS", 30)

# Real per-cluster positive-label counts in this fleet's data are thin
# (0-7 per cluster out of ~1,200 rows - checked directly, not assumed).
# A cluster with zero positive examples across every one of its issue
# columns has nothing to learn from at all and is skipped (logged, not
# crashed) rather than producing a model that trivially predicts "never."
MIN_POSITIVE_LABELS = _env_int("WPS_MIN_POSITIVE_LABELS", 1)

# Below this many total positive labels, class_weight="balanced" on a
# RandomForestClassifier reweights the 1-2 positive examples so heavily
# (checked directly against real output: e.g. 2 positives in 1,201 rows
# gets ~300x the weight of a negative) that predict_proba saturates near
# 1.0 for many/most inputs, not just the vehicles resembling the real
# positives. The cluster still trains (there's nothing else useful to do
# with this little data) but predictions from it are marked
# low_confidence=True downstream (predict.py) rather than presented at
# face value alongside a well-supported cluster's output.
RELIABLE_POSITIVE_LABELS_THRESHOLD = _env_int("WPS_RELIABLE_POSITIVE_LABELS_THRESHOLD", 5)

TEST_FRACTION = _env_float("WPS_TEST_FRACTION", 0.2)
RANDOM_STATE = _env_int("WPS_RANDOM_STATE", 42)

# --- Model ---

N_ESTIMATORS = _env_int("WPS_N_ESTIMATORS", 200)
MAX_DEPTH = _env_int("WPS_MAX_DEPTH", 6)
MIN_SAMPLES_LEAF = _env_int("WPS_MIN_SAMPLES_LEAF", 5)

# --- Paths ---
#
# Prefixed warranty_ - PEWS's own models/ and warnings/ directories
# already exist in this same SERVICE_ROOT for the telematics-based
# clusters (see pews_config.py's MODELS_DIR/WARNINGS_DIR) - these must
# never collide with those.

MODELS_DIR = os.path.join(SERVICE_ROOT, "warranty_models")
PREDICTIONS_DIR = os.path.join(SERVICE_ROOT, "warranty_predictions")

# --- Live scoring ---

SCHEDULER_TICK_SECONDS = _env_int("WPS_SCHEDULER_TICK_SECONDS", 3600)

# --- RAG / LLM (see copilot equivalent in PEWS - same gateway convention) ---

OPENAI_API_BASE_URL = os.getenv("OPENAI_API_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_NAME = os.getenv("LLM_NAME")

RAG_TEMPERATURE = _env_float("WPS_RAG_TEMPERATURE", 0.2)
RAG_MAX_RESPONSE_TOKENS = _env_int("WPS_RAG_MAX_RESPONSE_TOKENS", 700)
