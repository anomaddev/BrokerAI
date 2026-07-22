from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select

from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import StrategyRow
from brokerai.db.repositories.strategy_versions import (
    StrategyVersionsRepository,
    append_strategy_version,
    strategy_version_snapshot,
)
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

BACKTEST_STATUS_NOT_RUN = "not_run"
BACKTEST_STATUS_QUEUED = "queued"
BACKTEST_STATUS_RUNNING = "running"
BACKTEST_STATUS_COMPLETED = "completed"
BACKTEST_STATUS_FAILED = "failed"
BACKTEST_STATUS_CANCELLED = "cancelled"

BACKTEST_STATUSES = frozenset(
    {
        BACKTEST_STATUS_NOT_RUN,
        BACKTEST_STATUS_QUEUED,
        BACKTEST_STATUS_RUNNING,
        BACKTEST_STATUS_COMPLETED,
        BACKTEST_STATUS_FAILED,
        BACKTEST_STATUS_CANCELLED,
    }
)


def normalize_backtest_status(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip() in BACKTEST_STATUSES:
        return raw.strip()
    return BACKTEST_STATUS_NOT_RUN


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
    from brokerai.ai_strategy.lifecycle import (
        is_ai_strategy_doc,
        normalize_lifecycle,
    )

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
        "backtest_status": normalize_backtest_status(doc.get("backtest_status")),
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
    if is_ai_strategy_doc(doc):
        lifecycle = normalize_lifecycle(doc)
        payload["execution_phase"] = lifecycle["execution_phase"]
        payload["warmup"] = lifecycle["warmup"]
        if doc.get("ai_improve"):
            payload["ai_improve"] = doc["ai_improve"]
    return payload


def _sync_row_columns(row: StrategyRow, doc: dict[str, Any]) -> None:
    row.asset_class = doc["asset_class"]
    row.name = doc["name"]
    row.enabled = bool(doc.get("enabled", False))
    row.preset_id = doc.get("preset_id")
    row.backtest_status = normalize_backtest_status(doc.get("backtest_status"))
    row.doc = doc


class StrategiesRepository:
    """Postgres-backed strategies (`brokerai.strategies`)."""

    COLLECTION = "strategies"  # legacy name; storage is Postgres JSONB docs

    async def list_all(self) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = select(StrategyRow).order_by(StrategyRow.asset_class, StrategyRow.name)
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_strategy(dict(row.doc)) for row in rows]

    async def list_enabled(self) -> list[dict[str, Any]]:
        async with session_scope() as session:
            stmt = (
                select(StrategyRow)
                .where(StrategyRow.enabled.is_(True))
                .order_by(StrategyRow.asset_class, StrategyRow.name)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [serialize_strategy(dict(row.doc)) for row in rows]

    async def get_by_id(self, strategy_id: str) -> dict[str, Any] | None:
        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if not row:
                return None
            return serialize_strategy(dict(row.doc))

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
            "backtest_status": BACKTEST_STATUS_NOT_RUN,
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
        if preset_id == "ai_strategy":
            if asset_class != "forex" or set(cleaned_selection.keys()) - {"forex"}:
                raise ValueError("AI Strategy is forex-only in v1")
            from brokerai.ai_strategy.lifecycle import ensure_lifecycle_on_create
            from brokerai.db.repositories.asset_settings import AssetSettingsRepository

            forex_settings = await AssetSettingsRepository().get("forex")
            default_days = int(forex_settings.get("default_warmup_trading_days") or 5)
            doc = ensure_lifecycle_on_create(doc, default_warmup_trading_days=default_days)

        async with session_scope() as session:
            row = StrategyRow(
                id=doc["id"],
                asset_class=doc["asset_class"],
                name=doc["name"],
                enabled=doc["enabled"],
                preset_id=doc.get("preset_id"),
                backtest_status=doc["backtest_status"],
                doc=doc,
            )
            session.add(row)
            await append_strategy_version(
                session,
                strategy_id=doc["id"],
                snapshot=strategy_version_snapshot(doc),
                change_label="Created strategy",
            )
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
        definition_changed = any(
            value is not None for value in (name, description, params, instrument_selection)
        )
        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if not row:
                return None

            existing = dict(row.doc)
            before = dict(existing)
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

            cleaned_selection = None
            if instrument_selection is not None:
                cleaned_selection = clean_instrument_selection(instrument_selection)
                if not cleaned_selection:
                    raise ValueError("Select at least one instrument")
                updates["instrument_selection"] = cleaned_selection
                updates["instruments"] = flatten_instruments(cleaned_selection)
                updates["asset_class"] = derive_asset_class(cleaned_selection)

            existing.update(updates)
            _sync_row_columns(row, existing)

            if definition_changed:
                # Lazy import: config_backup.service imports this module.
                from brokerai.config_backup.change_labels import describe_strategy_update

                change_label = describe_strategy_update(
                    before,
                    name=name.strip() if name is not None else None,
                    description=description.strip() if description is not None else None,
                    params=params,
                    instrument_selection=cleaned_selection,
                    enabled=enabled,
                )
                await append_strategy_version(
                    session,
                    strategy_id=strategy_id,
                    snapshot=strategy_version_snapshot(existing),
                    change_label=change_label or "Strategy updated",
                )

        return await self.get_by_id(strategy_id)

    async def promote_to_live(self, strategy_id: str) -> dict[str, Any] | None:
        from brokerai.ai_strategy.lifecycle import is_ai_strategy_doc, promote_to_live

        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if not row:
                return None
            existing = dict(row.doc)
            if not is_ai_strategy_doc(existing):
                raise ValueError("Only AI Strategies can be promoted")
            updated = promote_to_live(existing)
            updated["updated_at"] = _now_iso()
            _sync_row_columns(row, updated)
        return await self.get_by_id(strategy_id)

    async def save_lifecycle(self, strategy_id: str, doc_updates: dict[str, Any]) -> dict[str, Any] | None:
        """Persist lifecycle fields (phase/warmup) without creating a params version."""
        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if not row:
                return None
            existing = dict(row.doc)
            existing.update(doc_updates)
            existing["updated_at"] = _now_iso()
            _sync_row_columns(row, existing)
        return await self.get_by_id(strategy_id)

    async def delete(self, strategy_id: str) -> bool:
        async with session_scope() as session:
            await StrategyVersionsRepository().delete_for_strategy(session, strategy_id)
            result = await session.execute(
                delete(StrategyRow).where(StrategyRow.id == strategy_id)
            )
            return bool(result.rowcount)

    async def queue_backtests(self, strategy_ids: list[str]) -> list[dict[str, Any]]:
        """Mark strategies as queued for backtest processing."""
        unique_ids = list(dict.fromkeys(strategy_id for strategy_id in strategy_ids if strategy_id))
        if not unique_ids:
            return []

        updated: list[dict[str, Any]] = []
        async with session_scope() as session:
            for strategy_id in unique_ids:
                row = await session.get(StrategyRow, strategy_id)
                if not row:
                    continue
                existing = dict(row.doc)
                existing["backtest_status"] = BACKTEST_STATUS_QUEUED
                existing["updated_at"] = _now_iso()
                _sync_row_columns(row, existing)
                updated.append(serialize_strategy(existing))
        return updated

    async def set_backtest_status(
        self, strategy_id: str, status: str
    ) -> dict[str, Any] | None:
        """Update only the strategy-level backtest status badge."""
        normalized = normalize_backtest_status(status)
        async with session_scope() as session:
            row = await session.get(StrategyRow, strategy_id)
            if not row:
                return None
            existing = dict(row.doc)
            existing["backtest_status"] = normalized
            existing["updated_at"] = _now_iso()
            _sync_row_columns(row, existing)
            return serialize_strategy(existing)
