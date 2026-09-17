"""Application settings loaded from environment variables / .env file.

Uses pydantic-settings so every knob is overridable per environment
(development, staging, production) without code changes.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Mahindra AI Command Center API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "Mahindra AI Command Center API"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = Field(default=True, description="Enable debug mode (verbose errors, SQL echo).")
    api_v1_prefix: str = "/api/v1"

    # ------------------------------------------------------------------
    # Database (async SQLAlchemy 2.x over asyncpg)
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://mahindra:mahindra@localhost:5432/mahindra_ai",
        description="Async SQLAlchemy database URL.",
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout: int = Field(default=30, ge=1, le=300)
    db_pool_recycle: int = Field(default=1800, ge=60, description="Recycle connections after N seconds.")
    db_echo: bool = Field(default=False, description="Echo SQL statements (debug only).")

    # ------------------------------------------------------------------
    # CORS — comma-separated list of allowed origins
    # ------------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://localhost:8080",
        description="Comma-separated origins allowed by CORS.",
    )

    # ------------------------------------------------------------------
    # AI layer
    # ------------------------------------------------------------------
    ai_provider: Literal["rule", "openai"] = Field(
        default="rule",
        description="Active AI provider: 'rule' (deterministic engines) or 'openai' (LLM, when configured).",
    )
    openai_api_key: str = Field(
        default="",
        description="Optional OpenAI API key (required only for ai_provider=openai).",
    )
    openai_base_url: str = Field(
        default="",
        description="Optional OpenAI-compatible base URL (required only for ai_provider=openai).",
    )
    openai_model: str = Field(
        default="",
        description="Optional OpenAI-compatible model name (required only for ai_provider=openai).",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    log_level: str = Field(default="INFO", description="Root log level (DEBUG, INFO, WARNING, ERROR).")

    # ------------------------------------------------------------------
    # Hardening: rate limiting & caching
    # ------------------------------------------------------------------
    rate_limit_enabled: bool = Field(default=True, description="Enable fixed-window rate limiting.")
    rate_limit_requests: int = Field(
        default=300, ge=1, description="Max requests per client IP per window (general endpoints)."
    )
    rate_limit_ai_requests: int = Field(default=30, ge=1, description="Max AI POST requests per client IP per window.")
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600, description="Rate limit window size.")
    read_cache_ttl_seconds: int = Field(
        default=300, ge=0, description="TTL for in-memory caching of static read endpoints."
    )

    # ------------------------------------------------------------------
    # Synthetic causal replay and dedicated scheduler
    # ------------------------------------------------------------------
    simulation_minutes_per_real_minute: float = Field(
        default=60.0, ge=0.0, description="Synthetic minutes advanced per real minute."
    )
    simulation_tick_interval_seconds: int = Field(
        default=60, ge=1, description="Minimum real-time interval between replay-clock ticks."
    )
    simulation_replay_start: datetime | None = Field(
        default=None, description="Optional UTC replay start; otherwise derived from canonical telemetry."
    )
    simulation_replay_end: datetime | None = Field(
        default=None, description="Optional UTC replay end; otherwise derived from canonical operational data."
    )
    causal_scheduler_enabled: bool = Field(default=True)
    causal_scheduler_poll_seconds: int = Field(default=10, ge=1, le=300)
    causal_ingestion_enabled: bool = Field(default=True)
    causal_ingestion_poll_seconds: int = Field(default=10, ge=1, le=300)
    causal_warning_evaluator_enabled: bool = Field(default=True)
    causal_warning_evaluator_poll_seconds: int = Field(default=60, ge=1, le=300)
    causal_scheduler_domain: str = Field(default="all", pattern="^(all|manufacturing|telematics)$")
    telematics_causal_refresh_minutes: int = Field(default=30, ge=1)
    manufacturing_causal_refresh_minutes: int = Field(default=60, ge=1)
    telematics_causal_max_vehicles: int = Field(
        default=12,
        ge=2,
        le=64,
        description=(
            "Background telematics cohort ceiling. Eligible vehicles carrying visible "
            "field evidence are always admitted; this bounds PCMCI cost for the rest."
        ),
    )
    causal_algorithm: Literal["lpcmci", "pcmci"] = Field(
        default="lpcmci",
        description=(
            "Production causal-discovery engine for manufacturing/telematics. LPCMCI "
            "handles latent confounders and contemporaneous links; PCMCI is retained "
            "only for rollback/comparison. Participates in each run's source signature, "
            "so changing this always triggers a fresh run rather than reusing a stale one."
        ),
    )
    lpcmci_test_contemporaneous: bool = Field(
        default=True,
        description=(
            "Whether the LPCMCI path also tests lag-0 (contemporaneous) links. LPCMCI's "
            "main advantage over PCMCI is resolving contemporaneous/latent-confounding "
            "ambiguity, so this defaults on. Ignored when causal_algorithm='pcmci'."
        ),
    )

    # ------------------------------------------------------------------
    # Auto Mobility Causal Twin — PCMCI over live mobility_timeseries.
    # No replay clock and no scheduler container here (unlike manufacturing/
    # telematics above): mobility_timeseries is written live, every real
    # minute, so every computation just reads it as it currently stands.
    # See docs/Implementation_plan_mobility_causal.md.
    # ------------------------------------------------------------------
    mobility_causal_window_days: int = Field(
        default=90,
        ge=1,
        description=(
            "Trailing lookback, in days, of mobility_timeseries history "
            "eligible for sampling. A ceiling, not a promise: real history "
            "may not span this far yet, in which case whatever's actually "
            "available is used (see mobility_causal_min_observations)."
        ),
    )
    mobility_causal_sample_stride_hours: int = Field(
        default=12,
        ge=1,
        description=(
            "How far apart, in hours, sampled observations are. Every "
            "mobility_timeseries row is itself a trailing 12-HOUR rolling "
            "window rewritten every minute, so sampling every 1-minute row "
            "(the original approach) fed PCMCI near-duplicate observations "
            "(99.86% shared underlying data between consecutive rows) — "
            "manufactured autocorrelation, not genuine timing. 12 hours "
            "matches the rolling window's own length, giving fully "
            "independent samples (zero overlap, zero gap)."
        ),
    )
    mobility_causal_min_observations: int = Field(
        default=50,
        ge=2,
        description=(
            "Minimum sampled observations required before PCMCI will run. "
            "Real accumulated mobility_timeseries history is currently well "
            "short of mobility_causal_window_days, so this floor is set to "
            "what's realistically available now (~50-70 at a 12h stride), "
            "not an ideal target — results this close to the floor are "
            "lower-confidence than a fully-populated window and should be "
            "treated accordingly."
        ),
    )
    mobility_causal_tau_max: int = Field(
        default=2,
        ge=1,
        description=(
            "Max lag PCMCI tests, expressed in sample-steps (each step is "
            "mobility_causal_sample_stride_hours long, so 2 steps at a 12h "
            "stride = 24 hours). Deliberately narrow while real observation "
            "counts are low (~50-70) — testing more lags spreads the same "
            "small sample across more hypotheses. Revisit widening this "
            "(e.g. 4-6 steps, to catch multi-day dynamics like "
            "allocation_delay_days/delivery_delay_days) once real history "
            "passes ~90 days (~180 observations)."
        ),
    )
    mobility_causal_pc_alpha: float = Field(
        default=0.30,
        gt=0.0,
        lt=1.0,
        description=(
            "PCMCI pc_alpha and Benjamini-Hochberg q threshold for the mobility causal graph. "
            "A read-only sweep on the current 28-measure, 70-observation source found 0.30 "
            "to be the connected-node knee (25 measures); higher values added edges without "
            "adding connected measures. Override per environment as the source grows."
        ),
    )
    mobility_causal_refresh_minutes: int = Field(
        default=60,
        ge=1,
        description=(
            "How often the mobility causal graph refresh loop WAKES to "
            "check for new data (starting-phase default: 60 minutes) — not "
            "how often it actually recomputes. A recompute only happens "
            "when a new complete mobility_causal_sample_stride_hours bucket "
            "has become available since the last one, so at the default "
            "12h stride, actual recomputation happens roughly twice a day "
            "even though the check runs hourly."
        ),
    )

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins parsed into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def json_logs(self) -> bool:
        """JSON log rendering outside development; pretty console in dev."""
        return self.environment != "development"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
