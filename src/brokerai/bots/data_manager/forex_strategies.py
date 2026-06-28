from __future__ import annotations

from dataclasses import dataclass

from brokerai.db.repositories.asset_settings import AssetSettingsRepository, enabled_forex_pairs
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.strategy_constants import WATCHLIST_ALL_SYMBOL


def strategy_forex_pairs(strategy: dict) -> list[str]:
    """Return explicit forex pairs assigned to a strategy."""
    selection = strategy.get("instrument_selection") or {}
    forex = [pair for pair in selection.get("forex") or [] if pair != WATCHLIST_ALL_SYMBOL]
    if forex:
        return forex

    if strategy.get("asset_class") == "forex":
        return [pair for pair in strategy.get("instruments") or [] if pair != WATCHLIST_ALL_SYMBOL]

    return []


def filter_forex_strategies(
    strategies: list[dict],
    settings_enabled_pairs: list[str],
) -> list[tuple[dict, list[str]]]:
    """Return strategies whose forex pairs overlap settings-enabled pairs."""
    enabled_set = set(settings_enabled_pairs)
    runnable: list[tuple[dict, list[str]]] = []

    for strategy in strategies:
        pairs = strategy_forex_pairs(strategy)
        if not pairs:
            continue
        matched = [pair for pair in pairs if pair in enabled_set]
        if matched:
            runnable.append((strategy, matched))

    return runnable


@dataclass(frozen=True)
class ForexStrategyLoadResult:
    strategies: list[tuple[dict, list[str]]]
    skip_reason: str | None = None


async def load_runnable_forex_strategies() -> ForexStrategyLoadResult:
    """Load enabled strategies limited to forex pairs enabled in asset settings."""
    strategies_repo = StrategiesRepository()
    enabled = await strategies_repo.list_enabled()
    if not enabled:
        return ForexStrategyLoadResult([], "no enabled strategies")

    asset_repo = AssetSettingsRepository()
    forex_settings = await asset_repo.get("forex")
    if not forex_settings.get("enabled"):
        return ForexStrategyLoadResult([], "forex is disabled in Settings → Broker")

    settings_pairs = enabled_forex_pairs(list(forex_settings.get("enabled_pairs") or []))
    if not settings_pairs:
        return ForexStrategyLoadResult([], "no forex pairs enabled in Settings → Broker")

    runnable = filter_forex_strategies(enabled, settings_pairs)
    if not runnable:
        return ForexStrategyLoadResult([], "no enabled strategies match enabled forex pairs")

    return ForexStrategyLoadResult(runnable)
