from __future__ import annotations

from brokerai.bots.data_manager.forex_strategies import (
    filter_forex_strategies,
    strategy_forex_pairs,
)


def _strategy(
    *,
    strategy_id: str = "abc123",
    asset_class: str = "forex",
    instruments: list[str] | None = None,
    instrument_selection: dict[str, list[str]] | None = None,
) -> dict:
    return {
        "id": strategy_id,
        "name": "Test",
        "asset_class": asset_class,
        "instruments": instruments or [],
        "instrument_selection": instrument_selection or {},
    }


def test_strategy_forex_pairs_from_instrument_selection():
    strategy = _strategy(
        instrument_selection={"forex": ["EUR/USD", "GBP/USD"]},
        instruments=["EUR/USD", "GBP/USD"],
    )
    assert strategy_forex_pairs(strategy) == ["EUR/USD", "GBP/USD"]


def test_strategy_forex_pairs_falls_back_to_instruments():
    strategy = _strategy(instruments=["USD/JPY"])
    assert strategy_forex_pairs(strategy) == ["USD/JPY"]


def test_strategy_forex_pairs_ignores_non_forex_strategy():
    strategy = _strategy(
        asset_class="stocks",
        instrument_selection={"stocks": ["AAPL"]},
        instruments=["AAPL"],
    )
    assert strategy_forex_pairs(strategy) == []


def test_filter_forex_strategies_intersects_with_settings_pairs():
    strategies = [
        _strategy(
            strategy_id="one",
            instrument_selection={"forex": ["EUR/USD", "GBP/USD"]},
            instruments=["EUR/USD", "GBP/USD"],
        ),
        _strategy(
            strategy_id="two",
            instrument_selection={"forex": ["USD/JPY"]},
            instruments=["USD/JPY"],
        ),
    ]

    matched = filter_forex_strategies(strategies, ["EUR/USD", "USD/JPY"])

    assert len(matched) == 2
    assert matched[0][0]["id"] == "one"
    assert matched[0][1] == ["EUR/USD"]
    assert matched[1][0]["id"] == "two"
    assert matched[1][1] == ["USD/JPY"]


def test_filter_forex_strategies_excludes_non_overlapping_pairs():
    strategies = [
        _strategy(
            instrument_selection={"forex": ["GBP/USD"]},
            instruments=["GBP/USD"],
        )
    ]

    assert filter_forex_strategies(strategies, ["EUR/USD"]) == []
