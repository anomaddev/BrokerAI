from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from brokerai.db.client import get_db
from brokerai.strategies.params import SCHEMA_VERSION, normalize_stored_params, prepare_params
from brokerai.strategies.registry import get_preset
from brokerai.strategy_constants import WATCHLIST_ALL_SYMBOL

ASSET_CLASS_LABELS: dict[str, str] = {
    "forex": "Forex",
    "metals": "Precious Metals",
    "stocks": "Stocks",
    "crypto": "Crypto",
    "futures": "Futures",
    "options": "Options",
}


def empty_stats() -> dict[str, Any]:
    return {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": None,
        "realized_pnl": 0.0,
        "open_positions": 0,
        "last_trade_at": None,
    }


def normalize_stats(raw: dict[str, Any] | None) -> dict[str, Any]:
    stats = empty_stats()
    if not raw:
        return stats

    total_trades = int(raw.get("total_trades") or 0)
    winning_trades = int(raw.get("winning_trades") or 0)
    losing_trades = int(raw.get("losing_trades") or 0)
    win_rate = raw.get("win_rate")
    if win_rate is None and total_trades > 0:
        win_rate = winning_trades / total_trades

    stats.update(
        {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "realized_pnl": float(raw.get("realized_pnl") or 0.0),
            "open_positions": int(raw.get("open_positions") or 0),
            "last_trade_at": raw.get("last_trade_at"),
        }
    )
    return stats


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def derive_asset_class(instrument_selection: dict[str, list[str]], fallback: str = "forex") -> str:
    active = sorted(cls for cls, symbols in instrument_selection.items() if symbols)
    if len(active) == 1:
        return active[0]
    if active:
        return active[0]
    return fallback


def flatten_instruments(instrument_selection: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for symbols in instrument_selection.values():
        for symbol in symbols:
            if symbol == WATCHLIST_ALL_SYMBOL:
                continue
            if symbol not in seen:
                seen.add(symbol)
                ordered.append(symbol)
    return ordered


def clean_instrument_selection(instrument_selection: dict[str, list[str]]) -> dict[str, list[str]]:
    from brokerai.strategy_constants import WATCHLIST_ASSET_CLASSES

    cleaned_selection: dict[str, list[str]] = {}
    for cls, symbols in instrument_selection.items():
        if cls not in ASSET_CLASS_LABELS:
            continue
        cleaned = sorted({s.strip() for s in symbols if s and s.strip()})
        if not cleaned:
            continue
        if cleaned == [WATCHLIST_ALL_SYMBOL] and cls in WATCHLIST_ASSET_CLASSES:
            cleaned_selection[cls] = [WATCHLIST_ALL_SYMBOL]
        else:
            without_watchlist = sorted(s for s in cleaned if s != WATCHLIST_ALL_SYMBOL)
            if without_watchlist:
                cleaned_selection[cls] = without_watchlist
    return cleaned_selection


def _normalize_doc_params(doc: dict[str, Any]) -> dict[str, Any]:
    preset_id = doc.get("preset_id")
    if not preset_id:
        return doc.get("params") or {}
    preset = get_preset(preset_id)
    if not preset:
        return doc.get("params") or {}
    return normalize_stored_params(preset, doc.get("params"))


def serialize_strategy(doc: dict[str, Any]) -> dict[str, Any]:
    asset_class = doc["asset_class"]
    params = _normalize_doc_params(doc)
    payload: dict[str, Any] = {
        "id": doc["id"],
        "name": doc["name"],
        "asset_class": asset_class,
        "asset_class_label": ASSET_CLASS_LABELS.get(asset_class, asset_class.title()),
        "timeframe": params.get("timeframe") or doc.get("timeframe"),
        "description": doc.get("description", ""),
        "enabled": bool(doc.get("enabled", False)),
        "instruments": list(doc.get("instruments") or []),
        "stats": normalize_stats(doc.get("stats")),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "params": params,
        "params_schema_version": doc.get("params_schema_version", SCHEMA_VERSION),
        "strategy_type": doc.get("strategy_type", "custom"),
        "preset_id": doc.get("preset_id"),
        "route": doc.get("route"),
    }
    if doc.get("instrument_selection"):
        payload["instrument_selection"] = doc["instrument_selection"]
    return payload


class StrategiesRepository:
    COLLECTION = "strategies"

    async def list_all(self) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({}, {"_id": 0}).sort(
            [("asset_class", 1), ("name", 1)]
        )
        docs = await cursor.to_list(length=500)
        return [serialize_strategy(doc) for doc in docs]

    async def list_enabled(self) -> list[dict[str, Any]]:
        handle = await get_db()
        cursor = handle.db[self.COLLECTION].find({"enabled": True}, {"_id": 0}).sort(
            [("asset_class", 1), ("name", 1)]
        )
        docs = await cursor.to_list(length=500)
        return [serialize_strategy(doc) for doc in docs]

    async def get_by_id(self, strategy_id: str) -> dict[str, Any] | None:
        handle = await get_db()
        doc = await handle.db[self.COLLECTION].find_one({"id": strategy_id}, {"_id": 0})
        if not doc:
            return None
        return serialize_strategy(doc)

    async def create(
        self,
        *,
        name: str,
        description: str,
        preset_id: str,
        params: dict[str, Any],
        instrument_selection: dict[str, list[str]],
        enabled: bool = False,
    ) -> dict[str, Any]:
        preset = get_preset(preset_id)
        if not preset:
            raise ValueError(f"Unknown preset: {preset_id}")

        cleaned_selection = clean_instrument_selection(instrument_selection)
        normalized_params = prepare_params(preset, params)
        asset_class = derive_asset_class(cleaned_selection)
        instruments = flatten_instruments(cleaned_selection)
        now = _now_iso()

        doc: dict[str, Any] = {
            "id": uuid4().hex,
            "name": name.strip(),
            "description": description.strip(),
            "asset_class": asset_class,
            "timeframe": normalized_params["timeframe"],
            "enabled": enabled,
            "instruments": instruments,
            "instrument_selection": cleaned_selection,
            "strategy_type": "custom" if preset_id == "custom" else "preset",
            "preset_id": preset_id,
            "route": preset.route,
            "params": normalized_params,
            "params_schema_version": SCHEMA_VERSION,
            "stats": empty_stats(),
            "created_at": now,
            "updated_at": now,
        }

        handle = await get_db()
        await handle.db[self.COLLECTION].insert_one(doc)
        return serialize_strategy(doc)

    async def update(
        self,
        strategy_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        params: dict[str, Any] | None = None,
        instrument_selection: dict[str, list[str]] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        handle = await get_db()
        existing = await handle.db[self.COLLECTION].find_one({"id": strategy_id}, {"_id": 0})
        if not existing:
            return None

        updates: dict[str, Any] = {"updated_at": _now_iso()}

        if name is not None:
            updates["name"] = name.strip()
        if description is not None:
            updates["description"] = description.strip()
        if enabled is not None:
            updates["enabled"] = enabled

        if params is not None:
            preset_id = existing.get("preset_id")
            if not preset_id:
                raise ValueError("Cannot update params on a strategy without preset_id")
            preset = get_preset(preset_id)
            if not preset:
                raise ValueError(f"Unknown preset: {preset_id}")
            updates["params"] = prepare_params(preset, params)
            updates["params_schema_version"] = SCHEMA_VERSION
            updates["timeframe"] = updates["params"]["timeframe"]

        if instrument_selection is not None:
            cleaned_selection = clean_instrument_selection(instrument_selection)
            if not cleaned_selection:
                raise ValueError("Select at least one instrument")
            updates["instrument_selection"] = cleaned_selection
            updates["instruments"] = flatten_instruments(cleaned_selection)
            updates["asset_class"] = derive_asset_class(cleaned_selection)

        await handle.db[self.COLLECTION].update_one({"id": strategy_id}, {"$set": updates})
        return await self.get_by_id(strategy_id)

    async def delete(self, strategy_id: str) -> bool:
        handle = await get_db()
        result = await handle.db[self.COLLECTION].delete_one({"id": strategy_id})
        return result.deleted_count > 0
