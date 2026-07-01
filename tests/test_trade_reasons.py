from __future__ import annotations

from brokerai.trading.trade_reasons import REASON_REGISTRY, resolve_trade_reason


def test_known_reason_has_short_label_under_twenty_chars():
    for code, info in REASON_REGISTRY.items():
        assert len(info.short) < 20, code
        resolved = resolve_trade_reason(code)
        assert resolved["short"] == info.short
        assert resolved["category"] == info.category
        assert resolved["label"] == info.label


def test_resolve_trade_reason_unknown_code_falls_back():
    resolved = resolve_trade_reason("custom_exit_rule")
    assert resolved["code"] == "custom_exit_rule"
    assert resolved["category"] == "other"
    assert resolved["label"] == "Custom Exit Rule"
    assert len(resolved["short"]) < 20


def test_resolve_trade_reason_empty():
    assert resolve_trade_reason(None) == {
        "code": None,
        "label": None,
        "short": None,
        "category": None,
    }
