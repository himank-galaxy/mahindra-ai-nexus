"""Application settings loaded from environment variables / .env file.

Uses pydantic-settings so every knob is overridable per environment
(development, staging, production) without code changes.
"""

from __future__ import annotations

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
