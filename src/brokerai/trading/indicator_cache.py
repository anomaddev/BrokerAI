from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brokerai.trading.indicators import compute_adx, compute_atr, compute_ema, compute_rsi, compute_sma
from brokerai.trading.indicators._candles import candle_source_value


def indicator_cache_key(indicator_type: str, period: int, source: str = "close") -> str:
    return f"{indicator_type}:{period}:{source}"


def _compute_indicator(
    indicator_type: str,
    candles: list[dict[str, Any]],
    period: int,
    source: str,
) -> Any:
    if indicator_type == "ema":
        series = [
            {**candle, "close": candle_source_value(candle, source)}
            for candle in candles
        ]
        return compute_ema(series, period)
    if indicator_type == "sma":
        series = [
            {**candle, "close": candle_source_value(candle, source)}
            for candle in candles
        ]
        return compute_sma(series, period)
    if indicator_type == "rsi":
        series = [
            {**candle, "close": candle_source_value(candle, source)}
            for candle in candles
        ]
        return compute_rsi(series, period)
    if indicator_type == "adx":
        return compute_adx(candles, period)
    if indicator_type == "atr":
        return compute_atr(candles, period)
    return None


@dataclass
class IndicatorCacheView:
    pair: str
    timeframe: str
    _values: dict[str, Any] = field(default_factory=dict)

    def get_series(self, key: str) -> list[dict[str, Any]] | None:
        value = self._values.get(key)
        return value if isinstance(value, list) else None

    def get_scalar(self, key: str) -> float | None:
        value = self._values.get(key)
        return float(value) if isinstance(value, (int, float)) else None


@dataclass
class IndicatorCache:
    _store: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)

    def _bucket(self, pair: str, timeframe: str) -> dict[str, Any]:
        return self._store.setdefault((pair, timeframe), {})

    def warm(
        self,
        pair: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        params_list: list[dict[str, Any]],
    ) -> IndicatorCacheView:
        needed: set[tuple[str, int, str]] = set()

        for params in params_list:
            indicators = params.get("indicators") or {}
            if isinstance(indicators, dict):
                for spec in indicators.values():
                    if not isinstance(spec, dict):
                        continue
                    indicator_type = str(spec.get("type", "ema"))
                    period = int(spec.get("period", 14))
                    source = str(spec.get("source", "close"))
                    needed.add((indicator_type, period, source))

            for filter_spec in params.get("filters") or []:
                if not isinstance(filter_spec, dict) or not filter_spec.get("enabled", True):
                    continue
                filter_type = str(filter_spec.get("type", ""))
                period = int(filter_spec.get("period", 14))
                if filter_type in {"adx", "atr", "rsi"}:
                    needed.add((filter_type, period, "close"))

        bucket = self._bucket(pair, timeframe)
        for indicator_type, period, source in needed:
            key = indicator_cache_key(indicator_type, period, source)
            bucket[key] = _compute_indicator(indicator_type, candles, period, source)

        return IndicatorCacheView(pair=pair, timeframe=timeframe, _values=dict(bucket))

    def clear(self, pair: str | None = None, timeframe: str | None = None) -> None:
        if pair is None and timeframe is None:
            self._store.clear()
            return
        keys_to_remove = [
            key
            for key in self._store
            if (pair is None or key[0] == pair) and (timeframe is None or key[1] == timeframe)
        ]
        for key in keys_to_remove:
            del self._store[key]
