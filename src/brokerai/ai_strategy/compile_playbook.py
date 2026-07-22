"""Compile a strategy memory digest into a backtest params_snapshot.

Produces ``signal.type == compiled_playbook`` with risk/execution copied from
the live AI Strategy. Deterministic — never calls an LLM.

Digest shape matches Slice 3: ``standing_rules`` / ``anti_rules`` are string lists.
"""

from __future__ import annotations

import copy
from typing import Any

from brokerai.ai_strategy.memory_digest import (
    digest_is_queueable,
    digest_version_key,
    normalize_memory_digest,
)
from brokerai.trading.presets.compiled_playbook.signal import (
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MOMENTUM_BARS,
    SIGNAL_TYPE,
)


def _infer_bias(standing_rules: list[str]) -> str:
    """Majority bias from standing rule text; default flat when mixed/empty."""
    scores = {"long": 0, "short": 0, "flat": 0, "both": 0}
    for rule in standing_rules:
        blob = str(rule or "").lower()
        if any(token in blob for token in ("short", "bear", "sell", "risk-off", "fade")):
            scores["short"] += 1
        elif any(token in blob for token in ("long", "bull", "buy", "risk-on", "continuation")):
            scores["long"] += 1
        elif any(token in blob for token in ("flat", "stand aside", "no trade", "avoid")):
            scores["flat"] += 1
    best = max(scores.items(), key=lambda item: item[1])
    if best[1] <= 0:
        return "flat"
    if scores["long"] == scores["short"] and scores["long"] > scores["flat"]:
        return "both"
    return best[0]


def _anti_active(anti_rules: list[str]) -> bool:
    """v1: anti rules that mention hard-block keywords mark the book inactive."""
    block_tokens = ("do not trade", "stand aside", "no entries", "halt", "kill switch")
    for rule in anti_rules:
        blob = str(rule or "").lower()
        if any(token in blob for token in block_tokens):
            return True
    return False


def compile_playbook_params(
    strategy: dict[str, Any],
    digest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build a params_snapshot for a compiled-playbook backtest.

    Returns ``None`` when the digest is missing/empty (caller should skip queue).
    """
    if not digest_is_queueable(digest):
        return None

    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    params = copy.deepcopy(params) if params else {}
    normalized = normalize_memory_digest(
        digest,
        strategy_id=str(strategy.get("id") or (digest or {}).get("strategy_id") or ""),
    )
    standing = list(normalized["standing_rules"])
    anti = list(normalized["anti_rules"])
    bias = _infer_bias(standing)

    params["signal"] = {
        "type": SIGNAL_TYPE,
        "bias": bias,
        "default_bias": bias,
        "require_momentum": True,
        "momentum_bars": DEFAULT_MOMENTUM_BARS,
        "min_confidence": DEFAULT_MIN_CONFIDENCE,
        "anti_active": _anti_active(anti),
        "standing_rules": standing,
        "anti_rules": anti,
        "digest_version": digest_version_key(normalized),
        "digest_summary": normalized.get("summary") or "",
    }
    ai = params.get("ai") if isinstance(params.get("ai"), dict) else {}
    params["ai"] = {**ai, "llm_mode": "off"}
    if "risk" not in params or not isinstance(params.get("risk"), dict):
        params["risk"] = {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3}
    if "execution" not in params or not isinstance(params.get("execution"), dict):
        params["execution"] = {
            "sessions": ["London", "NY"],
            "min_confidence": 60,
            "post_stop_cooldown_bars": 0,
        }
    if "timeframe" not in params:
        params["timeframe"] = strategy.get("timeframe") or "M15"
    params.setdefault("schema_version", 1)
    params.setdefault("indicators", {})
    params.setdefault("filters", list(params.get("filters") or []))
    return params


def compile_playbook_strategy_doc(
    strategy: dict[str, Any],
    digest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a strategy-shaped dict with compiled params, or ``None`` to skip."""
    compiled = compile_playbook_params(strategy, digest)
    if compiled is None:
        return None
    out = dict(strategy)
    out["params"] = compiled
    return out
