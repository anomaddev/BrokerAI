from __future__ import annotations

from brokerai.config_backup.categories import category_for_trigger
from brokerai.config_backup.change_labels import (
    describe_backup_schedule_change,
    describe_general_settings_change,
    describe_market_indicators_change,
    describe_research_settings_change,
    describe_strategy_update,
)


def test_category_for_general_settings():
    assert category_for_trigger("account.general") == "General"


def test_category_for_forex_broker():
    assert category_for_trigger("asset_settings.forex") == "Forex"


def test_category_for_strategies():
    assert category_for_trigger("strategies.patch:abc") == "Strategies"


def test_describe_general_settings_show_utc_toggle():
    label = describe_general_settings_change(
        {"show_utc_times": False, "timezone_auto": True, "time_format": "24h"},
        timezone_auto=True,
        timezone="America/New_York",
        show_utc_times=True,
        time_format="24h",
    )
    assert label == "Always Show UTC Time enabled"


def test_describe_market_indicators_sydney_toggle():
    label = describe_market_indicators_change(
        {"sydney": False, "asia": True, "london": True, "ny": True},
        {"sydney": True, "asia": True, "london": True, "ny": True},
    )
    assert label == "Sydney market enabled"


def test_describe_market_indicators_multiple_changes():
    label = describe_market_indicators_change(
        {"sydney": True, "asia": True, "london": True, "ny": True},
        {"sydney": False, "asia": False, "london": True, "ny": True},
    )
    assert label == "Sydney market disabled; Asia market disabled"


def test_describe_backup_schedule_retention_change():
    label = describe_backup_schedule_change(
        {"full_retention": 30, "change_retention": 100},
        {"full_retention": 25},
    )
    assert label == "Full backup retention set to 25"


def test_describe_research_daily_report_toggle():
    label = describe_research_settings_change(
        {"daily_report_enabled": False},
        daily_report_enabled=True,
    )
    assert label == "Daily report enabled"


def test_describe_strategy_enabled_toggle():
    label = describe_strategy_update(
        {"name": "EMA Cross", "enabled": False},
        name=None,
        description=None,
        params=None,
        instrument_selection=None,
        enabled=True,
    )
    assert label == "EMA Cross enabled"
