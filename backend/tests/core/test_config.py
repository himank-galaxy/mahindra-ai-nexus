"""Unit tests for core configuration parsing."""

from __future__ import annotations

from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(cors_origins=" http://a.dev , http://b.dev ,, ")
    assert settings.cors_origin_list == ["http://a.dev", "http://b.dev"]


def test_json_logs_only_outside_development() -> None:
    assert Settings(environment="development").json_logs is False
    assert Settings(environment="production").json_logs is True
