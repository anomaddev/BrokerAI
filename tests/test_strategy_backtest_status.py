from __future__ import annotations

from brokerai.db.repositories.strategies import (
    BACKTEST_STATUS_NOT_RUN,
    BACKTEST_STATUS_QUEUED,
    normalize_backtest_status,
    serialize_strategy,
)


def test_normalize_backtest_status_defaults_to_not_run():
    assert normalize_backtest_status(None) == BACKTEST_STATUS_NOT_RUN
    assert normalize_backtest_status("") == BACKTEST_STATUS_NOT_RUN
    assert normalize_backtest_status("unknown") == BACKTEST_STATUS_NOT_RUN


def test_normalize_backtest_status_accepts_known_values():
    assert normalize_backtest_status("queued") == BACKTEST_STATUS_QUEUED
    assert normalize_backtest_status("running") == "running"
    assert normalize_backtest_status("completed") == "completed"
    assert normalize_backtest_status("failed") == "failed"


def test_serialize_strategy_includes_backtest_status():
    payload = serialize_strategy(
        {
            "id": "abc",
            "name": "Test",
            "asset_class": "forex",
            "enabled": False,
            "instruments": [],
            "params": {"timeframe": "M15"},
        }
    )
    assert payload["backtest_status"] == BACKTEST_STATUS_NOT_RUN

    queued = serialize_strategy(
        {
            "id": "abc",
            "name": "Test",
            "asset_class": "forex",
            "enabled": False,
            "instruments": [],
            "params": {"timeframe": "M15"},
            "backtest_status": "queued",
        }
    )
    assert queued["backtest_status"] == BACKTEST_STATUS_QUEUED
