"""Compile a strategy memory digest into a backtest params_snapshot.

Produces ``signal.type == compiled_playbook`` with risk/execution copied from
the live AI Strategy. Deterministic — never calls an LLM.

Digest shape matches Slice 3: ``standing_rules`` / ``anti_rules`` are string lists.
The evaluator is a bias + momentum gate; this compiler must turn digest *changes*
into gate changes (bias, caution knobs) or improve-loops produce identical fills.
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

_ALLOWED_BIAS = frozenset({"long", "short", "flat", "both"})


def _infer_bias(standing_rules: list[str], *, explicit_bias: str | None = None) -> str:
    """Recency-weighted bias from standing rule text; honor explicit digest bias.

    Rules are assumed newest-first (feedback merge prepends). Newer rules get
    higher weight so a handful of fresh short/flat lessons can overturn a large
    long-biased seed block — otherwise improve-loops never change fills.
    """
    if explicit_bias in _ALLOWED_BIAS:
        return explicit_bias

    scores = {"long": 0.0, "short": 0.0, "flat": 0.0, "both": 0.0}
    n = len(standing_rules)
    for index, rule in enumerate(standing_rules):
        # Newest (index 0) weighs ~n; oldest weighs ~1.
        weight = float(max(1, n - index))
        blob = str(rule or "").lower()
        if any(token in blob for token in ("short", "bear", "sell", "risk-off", "fade")):
            scores["short"] += weight
        elif any(token in blob for token in ("long", "bull", "buy", "risk-on", "continuation")):
            scores["long"] += weight
        elif any(token in blob for token in ("flat", "stand aside", "no trade", "avoid")):
            scores["flat"] += weight
    best = max(scores.items(), key=lambda item: item[1])
    if best[1] <= 0:
        return "flat"
    if scores["long"] == scores["short"] and scores["long"] > scores["flat"]:
        return "both"
    return best[0]


def _anti_active(anti_rules: list[str]) -> bool:
    """True only for *global* kill-switch anti rules.

    Conditional phrasing like \"Stand aside through MOF alerts\" or \"stand aside
    momentum-only chases at extremes\" must NOT disable the whole playbook —
    those are location/regime lessons, not a halt. Matching bare \"stand aside\"
    previously zeroed every startup/trade loop.
    """
    hard_block_phrases = (
        "do not trade",
        "no entries",
        "no trading",
        "halt trading",
        "kill switch",
        "stop all trading",
        "stand aside entirely",
        "stand aside always",
        "stand aside completely",
    )
    for rule in anti_rules:
        blob = str(rule or "").lower().strip()
        if not blob:
            continue
        if any(phrase in blob for phrase in hard_block_phrases):
            return True
    return False


def _caution_from_anti_rules(anti_rules: list[str]) -> tuple[int, float, int, int]:
    """Map cautionary anti rules into stricter entry / sizing gates.

    Soft (non-kill-switch) antis previously had *zero* effect on fills — only
    ``anti_active`` and keyword-inferred bias mattered — so trade loops with
    growing digests still cloned P/L. Effects scale past the seed-size floor
    so later lessons still move momentum / confidence / trade caps.
    """
    caution_tokens = (
        "stand aside",
        "avoid",
        "do not",
        "don't",
        "no chase",
        "fade",
        "thin",
        "extreme",
        "intervention",
        "late-ny",
        "late ny",
    )
    caution = 0
    for rule in anti_rules:
        blob = str(rule or "").lower()
        if not blob:
            continue
        if any(token in blob for token in caution_tokens):
            caution += 1
    # Wide ranges so digests that keep adding caution still change the gate
    # after the research-seed anti list (often ~10–12) is already present.
    extra_momentum_bars = min(7, caution // 3)
    confidence_bump = min(0.25, caution * 0.012)
    max_trades_penalty = min(3, caution // 5)
    cooldown_bars = min(15, caution)
    return extra_momentum_bars, confidence_bump, max_trades_penalty, cooldown_bars


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
    explicit_bias = normalized.get("bias")
    bias = _infer_bias(standing, explicit_bias=explicit_bias if isinstance(explicit_bias, str) else None)
    anti_active = _anti_active(anti)
    extra_bars, conf_bump, trades_penalty, cooldown = _caution_from_anti_rules(anti)
    momentum_bars = DEFAULT_MOMENTUM_BARS + extra_bars
    min_confidence = min(0.85, float(DEFAULT_MIN_CONFIDENCE) + conf_bump)

    params["signal"] = {
        "type": SIGNAL_TYPE,
        "bias": bias,
        "default_bias": bias,
        "require_momentum": True,
        "momentum_bars": momentum_bars,
        "min_confidence": min_confidence,
        "anti_active": anti_active,
        "standing_rules": standing,
        "anti_rules": anti,
        "digest_version": digest_version_key(normalized),
        "digest_summary": normalized.get("summary") or "",
        "digest_bias": explicit_bias,
        "caution_anti_count": sum(
            1
            for rule in anti
            if any(
                token in str(rule or "").lower()
                for token in (
                    "stand aside",
                    "avoid",
                    "do not",
                    "don't",
                    "no chase",
                    "fade",
                    "thin",
                    "extreme",
                    "intervention",
                    "late-ny",
                    "late ny",
                )
            )
        ),
    }
    ai = params.get("ai") if isinstance(params.get("ai"), dict) else {}
    params["ai"] = {**ai, "llm_mode": "off"}
    if "risk" not in params or not isinstance(params.get("risk"), dict):
        params["risk"] = {"risk_per_trade_pct": 1.0, "max_trades_per_day": 3}
    else:
        params["risk"] = dict(params["risk"])
    try:
        base_max_trades = int(params["risk"].get("max_trades_per_day") or 3)
    except (TypeError, ValueError):
        base_max_trades = 3
    params["risk"]["max_trades_per_day"] = max(1, base_max_trades - trades_penalty)
    # Align the execution confidence gate with the playbook signal scale so a
    # long anti-rule list cannot soft-fail every entry below strategy defaults
    # (often min_confidence=60 while playbook signals sit near 55%).
    signal_min_pct = int(round(min_confidence * 100))
    existing_exec = params.get("execution") if isinstance(params.get("execution"), dict) else {}
    params["execution"] = {
        **{
            "sessions": ["London", "NY"],
            "min_confidence": signal_min_pct,
            "post_stop_cooldown_bars": 0,
        },
        **existing_exec,
        "min_confidence": signal_min_pct,
        "post_stop_cooldown_bars": max(
            int(existing_exec.get("post_stop_cooldown_bars") or 0),
            cooldown,
        ),
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
