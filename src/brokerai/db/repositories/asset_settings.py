from __future__ import annotations

from typing import Any

from sqlalchemy import select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import AssetSettingsRow
from brokerai.exchanges import validate_primary_exchange
from brokerai.market_sessions import normalize_enabled_sessions

ASSET_CLASSES = ("forex", "metals", "stocks", "crypto", "futures", "options")

FOREX_PAIR_CATALOG = sorted([
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "AUD/USD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "EUR/CHF",
    "EUR/AUD",
    "EUR/CAD",
    "EUR/NZD",
    "GBP/JPY",
    "GBP/CHF",
    "GBP/AUD",
    "GBP/CAD",
    "GBP/NZD",
    "AUD/JPY",
    "AUD/CAD",
    "AUD/CHF",
    "AUD/NZD",
    "CAD/JPY",
    "CAD/CHF",
    "CHF/JPY",
    "NZD/JPY",
    "NZD/CAD",
    "NZD/CHF",
])

_FOREX_CATALOG_SET = frozenset(FOREX_PAIR_CATALOG)


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def default_pair_order(enabled_pairs: list[str] | None = None) -> list[str]:
    """Default catalog order: enabled pairs first (A–Z), then disabled (A–Z)."""
    enabled = sorted(p for p in (enabled_pairs or []) if p in _FOREX_CATALOG_SET)
    enabled_set = set(enabled)
    disabled = sorted(p for p in FOREX_PAIR_CATALOG if p not in enabled_set)
    return enabled + disabled


def normalize_pair_order(
    enabled_pairs: list[str],
    pair_order: list[str] | None,
) -> list[str]:
    """Build a full catalog order with enabled pairs before deactivated pairs."""
    valid_enabled = _dedupe_preserve_order(p for p in enabled_pairs if p in _FOREX_CATALOG_SET)
    enabled_set = set(valid_enabled)

    raw_order = pair_order if pair_order else default_pair_order(valid_enabled)
    filtered = _dedupe_preserve_order(p for p in raw_order if p in _FOREX_CATALOG_SET)

    enabled_block = [p for p in filtered if p in enabled_set]
    disabled_block = [p for p in filtered if p not in enabled_set]

    for pair in valid_enabled:
        if pair not in enabled_block:
            enabled_block.append(pair)

    for pair in FOREX_PAIR_CATALOG:
        if pair not in enabled_set and pair not in disabled_block:
            disabled_block.append(pair)

    return enabled_block + disabled_block


def ordered_enabled_pairs(enabled_pairs: list[str], pair_order: list[str] | None) -> list[str]:
    """Return enabled pairs in user priority order (candle/analysis processing)."""
    order = normalize_pair_order(enabled_pairs, pair_order)
    enabled_set = set(enabled_pairs)
    return [p for p in order if p in enabled_set]


def enabled_forex_pairs(enabled_pairs: list[str]) -> list[str]:
    """Return enabled pairs in catalog order for research (ignores user priority)."""
    enabled_set = set(_dedupe_preserve_order(p for p in enabled_pairs if p in _FOREX_CATALOG_SET))
    return [pair for pair in FOREX_PAIR_CATALOG if pair in enabled_set]


def _normalize_forex_doc(doc: dict[str, Any]) -> dict[str, Any]:
    enabled = list(doc.get("enabled_pairs") or [])
    doc["enabled_pairs"] = _dedupe_preserve_order(p for p in enabled if p in _FOREX_CATALOG_SET)
    doc["pair_order"] = normalize_pair_order(doc["enabled_pairs"], doc.get("pair_order"))
    doc["enabled_sessions"] = normalize_enabled_sessions(doc.get("enabled_sessions"))
    if "only_one_position_per_pair" not in doc:
        doc["only_one_position_per_pair"] = True
    try:
        warmup_days = int(doc.get("default_warmup_trading_days", 5))
    except (TypeError, ValueError):
        warmup_days = 5
    doc["default_warmup_trading_days"] = max(1, min(60, warmup_days))
    return doc


class AssetSettingsRepository:
    COLLECTION = "asset_settings"

    async def get(self, asset_class: str) -> dict[str, Any]:
        if asset_class not in ASSET_CLASSES:
            raise ValueError(f"Unknown asset class: {asset_class}")

        async with session_scope() as session:
            row = await session.get(AssetSettingsRow, asset_class)
            if row:
                doc = dict(row.doc)
                if "primary_exchange" not in doc:
                    doc["primary_exchange"] = None
                if asset_class == "forex":
                    return _normalize_forex_doc(doc)
                return doc

        default: dict[str, Any] = {
            "asset_class": asset_class,
            "enabled": False,
            "primary_exchange": None,
        }
        if asset_class == "forex":
            default["enabled_pairs"] = []
            default["pair_order"] = default_pair_order([])
            default["enabled_sessions"] = normalize_enabled_sessions(None)
            default["only_one_position_per_pair"] = True
            default["default_warmup_trading_days"] = 5
        else:
            default["enabled_symbols"] = []
        return default

    async def save(
        self,
        asset_class: str,
        *,
        enabled: bool,
        enabled_pairs: list[str] | None = None,
        pair_order: list[str] | None = None,
        enabled_sessions: dict[str, bool] | None = None,
            only_one_position_per_pair: bool | None = None,
        primary_exchange: str | None = None,
        default_warmup_trading_days: int | None = None,
    ) -> dict[str, Any]:
        """Persist asset settings.

        Pair/symbol selections are kept when omitted so toggling the asset class
        off and on does not clear the user's enabled-pair list. Pass an explicit
        empty list to clear selections.
        """
        if asset_class not in ASSET_CLASSES:
            raise ValueError(f"Unknown asset class: {asset_class}")

        existing = await self.get(asset_class)
        doc: dict[str, Any] = {
            **existing,
            "asset_class": asset_class,
            "enabled": enabled,
            "primary_exchange": validate_primary_exchange(asset_class, primary_exchange),
        }
        if asset_class == "forex":
            if enabled_pairs is not None:
                pairs = _dedupe_preserve_order(
                    p for p in enabled_pairs if p in _FOREX_CATALOG_SET
                )
            else:
                pairs = list(existing.get("enabled_pairs") or [])
            doc["enabled_pairs"] = pairs
            order_source = pair_order if pair_order is not None else existing.get("pair_order")
            doc["pair_order"] = normalize_pair_order(pairs, order_source)
            if enabled_sessions is not None:
                doc["enabled_sessions"] = normalize_enabled_sessions(enabled_sessions)
            else:
                doc["enabled_sessions"] = normalize_enabled_sessions(
                    existing.get("enabled_sessions")
                )
            if only_one_position_per_pair is not None:
                doc["only_one_position_per_pair"] = bool(only_one_position_per_pair)
            else:
                doc["only_one_position_per_pair"] = bool(
                    existing.get("only_one_position_per_pair", True)
                )
            if default_warmup_trading_days is not None:
                doc["default_warmup_trading_days"] = int(default_warmup_trading_days)
        elif enabled_pairs is not None:
            doc["enabled_symbols"] = sorted(set(enabled_pairs))

        if asset_class == "forex":
            doc = _normalize_forex_doc(doc)

        async with session_scope() as session:
            row = await session.get(AssetSettingsRow, asset_class)
            if row is None:
                session.add(AssetSettingsRow(asset_class=asset_class, doc=doc))
            else:
                row.doc = doc
        return doc

    def forex_catalog(self) -> list[str]:
        return list(FOREX_PAIR_CATALOG)
