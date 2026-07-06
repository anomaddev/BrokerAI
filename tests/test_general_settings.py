"""Tests for user general settings normalization."""

from brokerai.auth.general_settings import (
    DEFAULT_TIME_FORMAT,
    normalize_general_settings,
    normalize_time_format,
    resolved_general_settings,
)


def test_normalize_time_format_defaults_to_24h() -> None:
    assert normalize_time_format(None) == "24h"
    assert normalize_time_format("") == "24h"
    assert normalize_time_format("invalid") == "24h"


def test_normalize_time_format_accepts_valid_values() -> None:
    assert normalize_time_format("12h") == "12h"
    assert normalize_time_format("24h") == "24h"
    assert normalize_time_format("12H") == "12h"


def test_normalize_general_settings_includes_time_format_default() -> None:
    settings = normalize_general_settings()
    assert settings["time_format"] == DEFAULT_TIME_FORMAT


def test_normalize_general_settings_persists_12h() -> None:
    settings = normalize_general_settings(time_format="12h")
    assert settings["time_format"] == "12h"


def test_resolved_general_settings_normalizes_invalid_time_format() -> None:
    settings = resolved_general_settings({"time_format": "bogus"})
    assert settings["time_format"] == "24h"
