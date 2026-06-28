from __future__ import annotations

from typing import Any


def compute_required_candles(params: dict[str, Any], *, maximum: int = 2000) -> int:
    """Estimate how many historical bars a strategy needs for indicator warm-up."""
    periods: list[int] = []

    indicators = params.get("indicators") or {}
    if isinstance(indicators, dict):
        for indicator in indicators.values():
            if isinstance(indicator, dict) and indicator.get("period") is not None:
                periods.append(int(indicator["period"]))

    filters = params.get("filters") or []
    if isinstance(filters, list):
        for filt in filters:
            if not isinstance(filt, dict):
                continue
            if filt.get("enabled") is False:
                continue
            if filt.get("period") is not None:
                periods.append(int(filt["period"]))

    signal = params.get("signal") or {}
    if isinstance(signal, dict) and signal.get("type") in {"monthly_high", "monthly_low"}:
        periods.append(31)

    exits = params.get("exits") or {}
    if isinstance(exits, dict):
        stop_loss = exits.get("stop_loss") or {}
        if isinstance(stop_loss, dict) and stop_loss.get("structure_lookback") is not None:
            periods.append(int(stop_loss["structure_lookback"]))

    warmup = max(periods) if periods else 50
    return min(maximum, warmup * 3)


def effective_min_candles(params: dict[str, Any], *, maximum: int = 2000) -> int:
    """Return max(user-configured min_candles, computed warmup)."""
    computed = compute_required_candles(params, maximum=maximum)
    stored = params.get("min_candles")
    if stored is None:
        return computed
    return max(int(stored), computed)
