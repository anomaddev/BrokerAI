from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from brokerai.bots.secretary.candle_preview import (
    clear_candle_preview_cache,
    preview_next_candle_watch,
)
from brokerai.bots.data_manager.forex_strategies import ForexStrategyLoadResult
from brokerai.trading.types import WorkPlan, WorkUnit


@pytest.fixture(autouse=True)
def _clear_preview_cache():
    clear_candle_preview_cache()
    yield
    clear_candle_preview_cache()


def _mock_work_plan() -> WorkPlan:
    return WorkPlan(
        units=(
            WorkUnit(
                pair="EUR/USD",
                asset_class="forex",
                timeframe="M15",
                bar_count=100,
                strategies=({"id": "s1"},),
            ),
            WorkUnit(
                pair="GBP/USD",
                asset_class="forex",
                timeframe="M15",
                bar_count=100,
                strategies=({"id": "s1"},),
            ),
            WorkUnit(
                pair="USD/JPY",
                asset_class="forex",
                timeframe="H1",
                bar_count=100,
                strategies=({"id": "s2"},),
            ),
        ),
        timeframes=("H1", "M15"),
    )


@pytest.mark.asyncio
async def test_preview_next_candle_watch_returns_m15_symbols():
    now = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)
    fetches = {"M15": "2026-07-06T04:15:03+00:00", "H1": "2026-07-06T05:00:03+00:00"}
    strategies = [({"id": "s1"}, ["EUR/USD", "GBP/USD"])]

    with (
        patch(
            "brokerai.bots.secretary.candle_preview.load_runnable_forex_strategies",
            new=AsyncMock(return_value=ForexStrategyLoadResult(strategies)),
        ),
        patch(
            "brokerai.bots.secretary.candle_preview.build_work_plan",
            return_value=_mock_work_plan(),
        ),
    ):
        payload = await preview_next_candle_watch(next_candle_fetches=fetches, now=now)

    assert payload["timeframe"] == "M15"
    assert payload["symbols"] == ["EUR/USD", "GBP/USD"]
    assert payload["asset_sections"] == [
        {
            "asset_class": "forex",
            "label": "Forex",
            "symbols": ["EUR/USD", "GBP/USD"],
        }
    ]
    assert payload["target_at"] == "2026-07-06T04:15:03+00:00"


@pytest.mark.asyncio
async def test_preview_next_candle_watch_uses_cache():
    now = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)
    load_mock = AsyncMock(return_value=ForexStrategyLoadResult([({"id": "s1"}, ["EUR/USD"])]))

    with (
        patch(
            "brokerai.bots.secretary.candle_preview.load_runnable_forex_strategies",
            new=load_mock,
        ),
        patch(
            "brokerai.bots.secretary.candle_preview.build_work_plan",
            return_value=WorkPlan(
                units=(
                    WorkUnit(
                        pair="EUR/USD",
                        asset_class="forex",
                        timeframe="M15",
                        bar_count=100,
                        strategies=({"id": "s1"},),
                    ),
                ),
                timeframes=("M15",),
            ),
        ),
    ):
        await preview_next_candle_watch(now=now)
        await preview_next_candle_watch(now=now)

    assert load_mock.await_count == 1


@pytest.mark.asyncio
async def test_preview_next_candle_watch_empty_when_no_strategies():
    now = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)

    with patch(
        "brokerai.bots.secretary.candle_preview.load_runnable_forex_strategies",
        new=AsyncMock(return_value=ForexStrategyLoadResult([], "no enabled strategies")),
    ):
        payload = await preview_next_candle_watch(now=now)

    assert payload["symbols"] == []
    assert payload["asset_sections"] == []
    assert payload["skip_reason"] == "no enabled strategies"


@pytest.mark.asyncio
async def test_preview_next_candle_watch_groups_symbols_by_asset():
    now = datetime(2026, 7, 6, 4, 0, 0, tzinfo=timezone.utc)
    fetches = {"M15": "2026-07-06T04:15:03+00:00"}

    work_plan = WorkPlan(
        units=(
            WorkUnit(
                pair="EUR/USD",
                asset_class="forex",
                timeframe="M15",
                bar_count=100,
                strategies=({"id": "s1"},),
            ),
            WorkUnit(
                pair="XAU/USD",
                asset_class="metals",
                timeframe="M15",
                bar_count=100,
                strategies=({"id": "s2"},),
            ),
        ),
        timeframes=("M15",),
    )

    with (
        patch(
            "brokerai.bots.secretary.candle_preview.load_runnable_forex_strategies",
            new=AsyncMock(return_value=ForexStrategyLoadResult([({"id": "s1"}, ["EUR/USD"])])),
        ),
        patch(
            "brokerai.bots.secretary.candle_preview.build_work_plan",
            return_value=work_plan,
        ),
    ):
        payload = await preview_next_candle_watch(next_candle_fetches=fetches, now=now)

    assert payload["asset_sections"] == [
        {"asset_class": "forex", "label": "Forex", "symbols": ["EUR/USD"]},
        {"asset_class": "metals", "label": "Precious Metals", "symbols": ["XAU/USD"]},
    ]
    assert payload["symbols"] == ["EUR/USD", "XAU/USD"]
