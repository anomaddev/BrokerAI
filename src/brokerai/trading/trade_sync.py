from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.trades import TradesRepository
from brokerai.integrations.oanda import (
    _parse_broker_timestamp,
    get_broker_open_trades_snapshot,
    get_broker_trade,
)
from brokerai.trading.trade_close_details import close_details_from_metadata
from brokerai.trading.trade_reconciliation import reconcile_open_trades

logger = logging.getLogger(__name__)

SYNC_STRATEGY_ID = "oanda-import"
SYNC_STRATEGY_NAME = "OANDA Import"
SYNC_METADATA_SOURCE = "oanda_sync"
BROKER_CLOSED_REASON = "broker_closed"


def _parse_broker_open_time(raw: str | None) -> datetime | None:
    """Backward-compatible alias for OANDA timestamp parsing."""
    return _parse_broker_timestamp(raw)


def broker_closed_trade_to_ledger_close(broker_trade: dict[str, Any]) -> dict[str, Any]:
    """Build ledger close kwargs from a normalized OANDA closed trade."""
    metadata: dict[str, Any] = {
        "source": SYNC_METADATA_SOURCE,
        "broker_trade_id": broker_trade.get("id"),
    }
    if broker_trade.get("open_time"):
        metadata["broker_open_time"] = broker_trade["open_time"]
    if broker_trade.get("close_time"):
        metadata["broker_close_time"] = broker_trade["close_time"]

    return {
        "reason": BROKER_CLOSED_REASON,
        "metadata": metadata,
        "exit_price": broker_trade.get("exit_price"),
        "realized_pl": broker_trade.get("realized_pl"),
        "closed_at": broker_trade.get("closed_at"),
    }


async def _backfill_closed_trade_details(
    repo: TradesRepository,
    *,
    access_token: str,
    environment: str,
    account_id: str,
) -> list[str]:
    """Persist missing exit price / realized P/L for already-closed ledger trades."""
    backfilled_ids: list[str] = []
    candidates = await repo.list_closed_trades_missing_close_details()

    for trade in candidates:
        trade_id = str(trade.get("id", ""))
        if not trade_id:
            continue

        metadata_details = close_details_from_metadata(trade.get("close_metadata"))
        exit_price = metadata_details.get("exit_price")
        realized_pl = metadata_details.get("realized_pl")
        closed_at = metadata_details.get("closed_at")

        if exit_price is None or realized_pl is None:
            broker_id = str(trade.get("broker_order_id") or "")
            if broker_id:
                broker_closed = await get_broker_trade(access_token, environment, account_id, broker_id)
                if broker_closed is not None:
                    if exit_price is None:
                        exit_price = broker_closed.get("exit_price")
                    if realized_pl is None:
                        realized_pl = broker_closed.get("realized_pl")
                    if closed_at is None:
                        closed_at = broker_closed.get("closed_at")

        if exit_price is None and realized_pl is None:
            continue

        updated = await repo.backfill_close_details(
            trade_id,
            exit_price=exit_price,
            realized_pl=realized_pl,
            closed_at=closed_at,
        )
        if updated:
            backfilled_ids.append(trade_id)
            logger.info(
                "Backfilled close details on trade %s exit=%s pl=%s",
                trade_id,
                exit_price,
                realized_pl,
            )

    return backfilled_ids


def broker_trade_to_ledger_intent(broker_trade: dict[str, Any]) -> dict[str, Any]:
    """Build a ledger trade payload from a normalized OANDA open trade."""
    direction = str(broker_trade.get("direction", "long")).lower()
    units = float(broker_trade.get("units") or 0)
    if direction == "short":
        units = -abs(units)
    else:
        units = abs(units)

    broker_id = str(broker_trade.get("id", ""))
    open_time = broker_trade.get("open_time")
    metadata: dict[str, Any] = {"source": SYNC_METADATA_SOURCE, "execution_reason": "oanda_import"}
    if open_time:
        metadata["broker_open_time"] = open_time

    return {
        "strategy_id": SYNC_STRATEGY_ID,
        "strategy_name": SYNC_STRATEGY_NAME,
        "pair": broker_trade.get("pair"),
        "asset_class": "forex",
        "direction": direction,
        "entry_price": broker_trade.get("price") or broker_trade.get("current_price") or 0.0,
        "stop_loss": None,
        "take_profit": None,
        "exit_mode": "manual",
        "risk_pct": 0.0,
        "units": units,
        "confidence": 0.0,
        "metadata": metadata,
        "broker_order_id": broker_id,
        "opened_at": _parse_broker_open_time(str(open_time) if open_time else None),
    }


async def sync_oanda_trades_to_ledger() -> dict[str, Any]:
    """Import OANDA open trades that are missing from the MongoDB ledger.

    Idempotent: existing open trades keyed by ``broker_order_id`` are skipped.
    Fuzzy-matched ledger rows missing ``broker_order_id`` are backfilled.

    Returns a summary dict with ``configured``, ``imported``, ``updated``, and
    ``skipped`` counts.
    """
    repo = TradesRepository()
    exchange_repo = ExchangeConnectionsRepository()
    oanda = await exchange_repo.get_oanda()
    access_token = str(oanda.get("access_token") or "").strip()
    account_id = str(oanda.get("account_id") or "").strip()
    environment = str(oanda.get("environment") or "practice")

    if not access_token or not account_id:
        return {
            "configured": False,
            "imported": 0,
            "updated": 0,
            "closed": 0,
            "backfilled": 0,
            "skipped": 0,
            "imported_trade_ids": [],
            "updated_trade_ids": [],
            "closed_trade_ids": [],
            "backfilled_trade_ids": [],
        }

    ledger_trades = await repo.list_open_trades()
    try:
        snapshot = await get_broker_open_trades_snapshot(access_token, environment, account_id)
    except httpx.HTTPError as exc:
        logger.warning("OANDA trade sync failed: %s", exc)
        return {
            "configured": True,
            "imported": 0,
            "updated": 0,
            "closed": 0,
            "backfilled": 0,
            "skipped": 0,
            "error": str(exc),
            "imported_trade_ids": [],
            "updated_trade_ids": [],
            "closed_trade_ids": [],
            "backfilled_trade_ids": [],
        }

    broker_trades = snapshot["trades"]
    reconciliation = reconcile_open_trades(ledger_trades, broker_trades)
    ledger_by_id = {str(trade.get("id", "")): trade for trade in ledger_trades}

    imported_ids: list[str] = []
    updated_ids: list[str] = []
    closed_ids: list[str] = []
    skipped = 0

    broker_open_ids = {str(t.get("id", "")) for t in broker_trades if t.get("id")}

    for broker_trade in reconciliation["unmatched_broker"]:
        broker_id = str(broker_trade.get("id", ""))
        if not broker_id:
            skipped += 1
            continue
        if await repo.get_open_by_broker_order_id(broker_id) is not None:
            skipped += 1
            continue

        intent = broker_trade_to_ledger_intent(broker_trade)
        created = await repo.create_open_trade(
            intent,
            broker_order_id=broker_id,
            opened_at=intent.get("opened_at"),
        )
        imported_ids.append(str(created.get("id", "")))
        logger.info(
            "Imported OANDA trade %s %s %s (broker id=%s, ledger id=%s)",
            created.get("pair"),
            created.get("direction"),
            created.get("units"),
            broker_id,
            created.get("id"),
        )

    for match in reconciliation["matched"]:
        if match.get("match_type") != "pair_direction":
            continue
        ledger_id = str(match.get("ledger_trade_id", ""))
        broker_id = str(match.get("broker_trade_id", ""))
        if not ledger_id or not broker_id:
            continue
        ledger = ledger_by_id.get(ledger_id)
        if ledger is None or ledger.get("broker_order_id"):
            continue
        await repo.update_broker_order_id(ledger_id, broker_id)
        updated_ids.append(ledger_id)
        logger.info(
            "Backfilled broker_order_id=%s on ledger trade %s",
            broker_id,
            ledger_id,
        )

    for ledger in ledger_trades:
        ledger_id = str(ledger.get("id", ""))
        broker_id = str(ledger.get("broker_order_id") or "")
        if not ledger_id or not broker_id:
            continue
        if broker_id in broker_open_ids:
            continue

        broker_closed = await get_broker_trade(access_token, environment, account_id, broker_id)
        if broker_closed is None or broker_closed.get("closed_at") is None:
            skipped += 1
            logger.warning(
                "Ledger trade %s broker id=%s is not open on OANDA but close details were unavailable",
                ledger_id,
                broker_id,
            )
            continue

        close_kwargs = broker_closed_trade_to_ledger_close(broker_closed)
        await repo.close_trade(ledger_id, **close_kwargs)
        closed_ids.append(ledger_id)
        logger.info(
            "Closed ledger trade %s from OANDA broker id=%s pl=%s",
            ledger_id,
            broker_id,
            close_kwargs.get("realized_pl"),
        )

    backfilled_ids = await _backfill_closed_trade_details(
        repo,
        access_token=access_token,
        environment=environment,
        account_id=account_id,
    )

    return {
        "configured": True,
        "imported": len(imported_ids),
        "updated": len(updated_ids),
        "closed": len(closed_ids),
        "backfilled": len(backfilled_ids),
        "skipped": skipped,
        "imported_trade_ids": imported_ids,
        "updated_trade_ids": updated_ids,
        "closed_trade_ids": closed_ids,
        "backfilled_trade_ids": backfilled_ids,
    }
