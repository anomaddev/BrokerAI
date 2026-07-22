"""Deterministic compiled-playbook signal evaluator (no LLM).

Compiles memory-digest standing/anti rules into a simple bias + momentum gate
suitable for daily AI Strategy self-backtests. Keyword rules are evaluated
against the compiled rule texts themselves (static) plus optional candle
momentum confirmation — never against an LLM.
"""

from __future__ import annotations

from typing import Any

from brokerai.strategies.candles import effective_min_candles
from brokerai.strategies.evaluator import StrategyResult
from brokerai.trading.indicator_cache import IndicatorCacheView
from brokerai.trading.registries.signals import register_signal

SIGNAL_TYPE = "compiled_playbook"
DEFAULT_MOMENTUM_BARS = 3
DEFAULT_MIN_CONFIDENCE = 0.55


def _signal_spec(params: dict[str, Any]) -> dict[str, Any]:
    signal = params.get("signal") if isinstance(params.get("signal"), dict) else {}
    return dict(signal)


def _momentum_direction(candles: list[dict[str, Any]], bars: int) -> str | None:
    """Return long/short when the last ``bars`` closes move consistently."""
    if bars < 1 or len(candles) < bars + 1:
        return None
    closes: list[float] = []
    for candle in candles[-(bars + 1) :]:
        try:
            closes.append(float(candle["close"]))
        except (KeyError, TypeError, ValueError):
            return None
    if len(closes) < bars + 1:
        return None
    ups = all(closes[i] > closes[i - 1] for i in range(1, len(closes)))
    downs = all(closes[i] < closes[i - 1] for i in range(1, len(closes)))
    if ups:
        return "long"
    if downs:
        return "short"
    return None


def _anti_blocks(signal: dict[str, Any]) -> bool:
    """Anti rules block entries when marked active (digest compile sets this)."""
    if bool(signal.get("anti_active")):
        return True
    anti_rules = signal.get("anti_rules") or []
    if isinstance(anti_rules, list) and anti_rules:
        # v1: presence of anti rules without an explicit override blocks trades
        # only when ``anti_active`` is true; otherwise they reduce confidence.
        return False
    return False


class CompiledPlaybookSignalEvaluator:
    """Rule-based playbook evaluator for ``signal.type == compiled_playbook``."""

    signal_type = SIGNAL_TYPE

    def evaluate(
        self,
        candles: list[dict[str, Any]],
        params: dict[str, Any],
        indicators: IndicatorCacheView,
        *,
        catchup: bool = False,
    ) -> StrategyResult:
        """Evaluate without any LLM / network calls.

        Edge cases:
        - Empty candles → no direction.
        - ``bias`` flat → no direction.
        - ``anti_active`` → no direction (fail closed).
        - Momentum mismatch with bias → no direction when ``require_momentum``.
        """
        _ = indicators, catchup
        signal = _signal_spec(params)
        min_required = effective_min_candles(params)
        bias = str(signal.get("bias") or signal.get("default_bias") or "flat").strip().lower()
        require_momentum = bool(signal.get("require_momentum", True))
        try:
            momentum_bars = max(1, int(signal.get("momentum_bars") or DEFAULT_MOMENTUM_BARS))
        except (TypeError, ValueError):
            momentum_bars = DEFAULT_MOMENTUM_BARS
        try:
            min_confidence = float(signal.get("min_confidence") or DEFAULT_MIN_CONFIDENCE)
        except (TypeError, ValueError):
            min_confidence = DEFAULT_MIN_CONFIDENCE
        min_confidence = max(0.0, min(1.0, min_confidence))

        base_meta: dict[str, Any] = {
            "signal": "none",
            "signal_type": SIGNAL_TYPE,
            "bias": bias,
            "llm_called": False,
            "require_momentum": require_momentum,
            "momentum_bars": momentum_bars,
            "standing_rule_count": len(signal.get("standing_rules") or []),
            "anti_rule_count": len(signal.get("anti_rules") or []),
        }

        if bias not in {"long", "short", "both"}:
            return StrategyResult(
                confidence=0.0,
                min_candles=min_required,
                direction=None,
                metadata={**base_meta, "reason": "bias_flat_or_unknown"},
            )

        if _anti_blocks(signal):
            return StrategyResult(
                confidence=0.0,
                min_candles=min_required,
                direction=None,
                metadata={**base_meta, "reason": "anti_rule_active"},
            )

        if len(candles) < min_required:
            return StrategyResult(
                confidence=0.0,
                min_candles=min_required,
                direction=None,
                metadata={
                    **base_meta,
                    "reason": "insufficient_candles",
                    "have": len(candles),
                    "need": min_required,
                },
            )

        momentum = _momentum_direction(candles, momentum_bars)
        base_meta["momentum"] = momentum

        direction: str | None = None
        if bias in {"long", "short"}:
            if require_momentum:
                direction = bias if momentum == bias else None
            else:
                direction = bias
        elif bias == "both":
            direction = momentum if require_momentum else None

        if direction is None:
            return StrategyResult(
                confidence=0.0,
                min_candles=min_required,
                direction=None,
                metadata={**base_meta, "reason": "momentum_mismatch" if require_momentum else "no_signal"},
            )

        anti_count = len(signal.get("anti_rules") or [])
        confidence = min_confidence
        if anti_count:
            confidence = max(0.35, min_confidence - 0.05 * min(anti_count, 4))

        return StrategyResult(
            confidence=confidence,
            min_candles=min_required,
            direction=direction,
            metadata={
                **base_meta,
                "signal": f"playbook_{direction}",
                "signal_time": str(candles[-1].get("time") or "") if candles else None,
            },
        )


def register_compiled_playbook_signal() -> None:
    register_signal(SIGNAL_TYPE, CompiledPlaybookSignalEvaluator())
