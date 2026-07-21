from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.backtesting.ai_feedback import (
    AI_FEEDBACK_STATUS_COMPLETED,
    AI_FEEDBACK_STATUS_RUNNING,
    MAX_CONTEXT_JSON_CHARS,
    begin_ai_feedback_job,
    build_backtest_feedback_messages,
    downsample_equity_for_feedback,
    maybe_auto_analyze_backtest,
    normalize_ai_feedback,
    reconstruct_trades_from_actions,
    slice_candle_windows,
    summarize_period_candles,
)


def test_reconstruct_trades_pairs_entry_and_exit():
    actions = [
        {
            "sequence": 1,
            "kind": "entry",
            "bar_time": "2026-01-01T10:00:00+00:00",
            "message": "Entered long",
            "meta": {"direction": "long", "price": 1.1, "units": 1000},
        },
        {
            "sequence": 2,
            "kind": "sl",
            "bar_time": "2026-01-01T11:00:00+00:00",
            "message": "Stop Loss",
            "meta": {"reason": "stop_loss", "price": 1.09, "realized_pnl": -10.0},
        },
        {
            "sequence": 3,
            "kind": "entry",
            "bar_time": "2026-01-01T12:00:00+00:00",
            "message": "Entered short",
            "meta": {"direction": "short", "price": 1.1, "units": 1000},
        },
        {
            "sequence": 4,
            "kind": "tp",
            "bar_time": "2026-01-01T13:00:00+00:00",
            "message": "Take Profit",
            "meta": {"reason": "take_profit", "price": 1.08, "realized_pnl": 20.0},
        },
    ]
    trades = reconstruct_trades_from_actions(actions)
    assert len(trades) == 2
    assert trades[0]["direction"] == "long"
    assert trades[0]["exit_kind"] == "sl"
    assert trades[0]["realized_pnl"] == -10.0
    assert trades[1]["exit_kind"] == "tp"
    assert trades[1]["realized_pnl"] == 20.0


def test_reconstruct_trades_skips_orphan_exit_and_open_entry():
    actions = [
        {
            "sequence": 1,
            "kind": "exit",
            "bar_time": "2026-01-01T09:00:00+00:00",
            "meta": {"reason": "manual", "price": 1.0, "realized_pnl": 0},
        },
        {
            "sequence": 2,
            "kind": "entry",
            "bar_time": "2026-01-01T10:00:00+00:00",
            "meta": {"direction": "long", "price": 1.1, "units": 1},
        },
    ]
    assert reconstruct_trades_from_actions(actions) == []


def test_downsample_equity_for_feedback_keeps_budget():
    curve = [{"time": str(i), "equity": float(i % 17)} for i in range(500)]
    out = downsample_equity_for_feedback(curve, max_points=50)
    assert len(out) <= 50
    assert out[0]["time"] == "0"
    assert out[-1]["time"] == "499"


def test_summarize_and_slice_candle_windows():
    candles = [
        {
            "time": f"2026-01-01T{h:02d}:00:00+00:00",
            "open": 1.0 + h * 0.01,
            "high": 1.02 + h * 0.01,
            "low": 0.99 + h * 0.01,
            "close": 1.01 + h * 0.01,
            "volume": 10,
        }
        for h in range(24)
    ]
    summary = summarize_period_candles(candles)
    assert summary is not None
    assert summary["bar_count"] == 24
    assert summary["open"] == candles[0]["open"]
    assert summary["close"] == candles[-1]["close"]

    trades = [
        {
            "entry_sequence": 1,
            "entry_time": "2026-01-01T10:00:00+00:00",
            "exit_time": "2026-01-01T12:00:00+00:00",
            "realized_pnl": -5.0,
        }
    ]
    windows = slice_candle_windows(candles, trades, timeframe="H1", window_bars=2)
    assert len(windows) == 2
    assert all(w["bars"] for w in windows)
    assert all("o" in bar for bar in windows[0]["bars"])


def test_build_messages_stays_under_size_budget():
    huge_windows = [
        {
            "trade_entry_sequence": i,
            "around": "entry",
            "anchor_time": f"t{i}",
            "bars": [{"t": f"t{i}-{j}", "o": 1, "h": 2, "l": 0.5, "c": 1.5} for j in range(30)],
        }
        for i in range(80)
    ]
    context = {
        "run": {"id": "run-1"},
        "stats": {"total_trades": 80},
        "trades": [],
        "candle_windows": huge_windows,
        "signals_sample": [{"message": "x" * 200} for _ in range(40)],
        "filter_fails_sample": [{"message": "y" * 200} for _ in range(40)],
    }
    messages = build_backtest_feedback_messages(context)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert len(messages[1]["content"]) < MAX_CONTEXT_JSON_CHARS + 500


def test_normalize_ai_feedback_none_when_empty():
    assert normalize_ai_feedback(None) is None
    assert normalize_ai_feedback({}) is None
    normalized = normalize_ai_feedback(
        {"status": "completed", "markdown": "## Summary", "model_name": "gpt"}
    )
    assert normalized is not None
    assert normalized["status"] == AI_FEEDBACK_STATUS_COMPLETED
    assert normalized["markdown"] == "## Summary"
    assert normalized["suggestions"] == []


def test_normalize_ai_feedback_keeps_allowlisted_suggestions():
    normalized = normalize_ai_feedback(
        {
            "status": "completed",
            "markdown": "## Summary",
            "suggestions": [
                {
                    "id": "atr_floor",
                    "path": "filters.atr.min_value",
                    "to": 0.05,
                    "rationale": "JPY",
                    "priority": 1,
                },
                {"id": "bad", "path": "indicators.fast.period", "to": 12},
            ],
        }
    )
    assert normalized is not None
    assert len(normalized["suggestions"]) == 1
    assert normalized["suggestions"][0]["path"] == "filters.atr.min_value"


@pytest.mark.asyncio
async def test_begin_ai_feedback_rejects_non_completed():
    with patch(
        "brokerai.backtesting.ai_feedback.BacktestRunsRepository"
    ) as mock_runs_cls:
        mock_runs = AsyncMock()
        mock_runs_cls.return_value = mock_runs
        mock_runs.get_by_id.return_value = {"id": "r1", "status": "running"}
        with pytest.raises(ValueError, match="completed"):
            await begin_ai_feedback_job("r1")


@pytest.mark.asyncio
async def test_begin_ai_feedback_rejects_when_disabled():
    with (
        patch("brokerai.backtesting.ai_feedback.BacktestRunsRepository") as mock_runs_cls,
        patch(
            "brokerai.backtesting.ai_feedback.BacktestSettingsRepository"
        ) as mock_settings_cls,
    ):
        mock_runs = AsyncMock()
        mock_runs_cls.return_value = mock_runs
        mock_runs.get_by_id.return_value = {"id": "r1", "status": "completed"}
        mock_settings = AsyncMock()
        mock_settings_cls.return_value = mock_settings
        mock_settings.get.return_value = {
            "ai_feedback_enabled": False,
            "ai_feedback_model_id": None,
            "ai_feedback_model_name": None,
        }
        with pytest.raises(ValueError, match="Enable AI feedback"):
            await begin_ai_feedback_job("r1")


@pytest.mark.asyncio
async def test_begin_ai_feedback_returns_existing_when_running():
    with (
        patch("brokerai.backtesting.ai_feedback.BacktestRunsRepository") as mock_runs_cls,
        patch(
            "brokerai.backtesting.ai_feedback.BacktestSettingsRepository"
        ) as mock_settings_cls,
    ):
        run = {
            "id": "r1",
            "status": "completed",
            "ai_feedback": {"status": AI_FEEDBACK_STATUS_RUNNING, "markdown": None},
        }
        mock_runs = AsyncMock()
        mock_runs_cls.return_value = mock_runs
        mock_runs.get_by_id.return_value = run
        mock_settings = AsyncMock()
        mock_settings_cls.return_value = mock_settings
        mock_settings.get.return_value = {
            "ai_feedback_enabled": True,
            "ai_feedback_model_id": "m1",
            "ai_feedback_model_name": "gpt-4o",
            "ai_feedback_reasoning_effort": "medium",
        }
        result = await begin_ai_feedback_job("r1")
        assert result is run
        mock_runs.update_ai_feedback.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_auto_analyze_respects_toggles():
    with (
        patch(
            "brokerai.backtesting.ai_feedback.BacktestSettingsRepository"
        ) as mock_settings_cls,
        patch(
            "brokerai.backtesting.ai_feedback.begin_ai_feedback_job",
            new_callable=AsyncMock,
        ) as mock_begin,
    ):
        mock_settings = AsyncMock()
        mock_settings_cls.return_value = mock_settings
        mock_settings.get.return_value = {
            "ai_feedback_enabled": True,
            "ai_feedback_auto_on_complete": False,
            "ai_feedback_model_id": "m1",
            "ai_feedback_model_name": "gpt",
        }
        await maybe_auto_analyze_backtest("r1")
        mock_begin.assert_not_awaited()

        mock_settings.get.return_value = {
            "ai_feedback_enabled": True,
            "ai_feedback_auto_on_complete": True,
            "ai_feedback_model_id": "m1",
            "ai_feedback_model_name": "gpt",
        }
        with patch(
            "brokerai.backtesting.ai_feedback.BacktestRunsRepository"
        ) as mock_runs_cls:
            mock_runs = AsyncMock()
            mock_runs_cls.return_value = mock_runs
            mock_runs.get_by_id.return_value = {
                "id": "r1",
                "status": "completed",
                "ai_feedback": None,
            }
            await maybe_auto_analyze_backtest("r1")
            mock_begin.assert_awaited_once_with("r1")


def test_context_json_roundtrip_for_messages():
    context = {
        "run": {"id": "run-1", "instrument": "EUR/USD"},
        "stats": {"total_trades": 2, "win_rate": 0.5},
        "trades": [{"entry_sequence": 1, "realized_pnl": 1.0}],
        "candle_windows": [],
    }
    messages = build_backtest_feedback_messages(context)
    # Extract JSON block
    body = messages[1]["content"]
    start = body.index("```json\n") + len("```json\n")
    end = body.rindex("\n```")
    parsed = json.loads(body[start:end])
    assert parsed["run"]["id"] == "run-1"
    assert parsed["stats"]["total_trades"] == 2
