"""One-shot helpers to repair strategy params written before indicator replace-merge."""

from __future__ import annotations

import copy
from typing import Any


def prune_orphan_legacy_indicators(params: dict[str, Any]) -> dict[str, Any] | None:
    """Drop unused ``fast``/``slow`` indicators when component ``ema_*`` ids are in use.

    Returns a deep-copied cleaned params dict when changes are needed, else ``None``.
    Also rewrites ``trail_ema_ref`` from a removed legacy key to ``signal.slow_ref``.
    """
    indicators = params.get("indicators")
    if not isinstance(indicators, dict) or not indicators:
        return None

    signal = params.get("signal") if isinstance(params.get("signal"), dict) else {}
    signal_refs: set[str] = set()
    for key in ("fast_ref", "slow_ref"):
        ref = signal.get(key)
        if isinstance(ref, str) and ref.strip():
            signal_refs.add(ref.strip())

    uses_component_ids = any(ref.startswith("ema_") for ref in signal_refs) or any(
        key.startswith("ema_") for key in indicators
    )
    if not uses_component_ids:
        return None

    # Keep only indicators still referenced by the signal; trail_ema_ref is rewritten below.
    drop = [key for key in ("fast", "slow") if key in indicators and key not in signal_refs]
    exits = params.get("exits") if isinstance(params.get("exits"), dict) else {}
    take_profit = exits.get("take_profit") if isinstance(exits.get("take_profit"), dict) else {}
    trail_ref = take_profit.get("trail_ema_ref")
    rewrite_trail = (
        isinstance(trail_ref, str)
        and trail_ref.strip() in drop
        and isinstance(signal.get("slow_ref"), str)
        and bool(str(signal.get("slow_ref")).strip())
    )

    if not drop and not rewrite_trail:
        return None

    cleaned = copy.deepcopy(params)
    for key in drop:
        cleaned["indicators"].pop(key, None)

    if rewrite_trail:
        cleaned["exits"]["take_profit"]["trail_ema_ref"] = str(signal["slow_ref"]).strip()

    return cleaned
