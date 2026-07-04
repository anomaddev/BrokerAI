from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brokerai.db.repositories.oanda_account_snapshots import SUMMARY_FIELDS
from brokerai.integrations.oanda import (
    _normalize_oanda_child_order,
    _normalize_oanda_open_trade,
    _normalize_oanda_trade_raw,
    _optional_float,
    normalize_account_summary_fields,
    normalize_oanda_transaction,
)
from brokerai.trading.broker.models import BrokerEvent, ChildOrder, PositionLot

logger = logging.getLogger(__name__)

OANDA_EXCHANGE_ID = "oanda"
DEFAULT_ASSET_CLASS = "forex"


def _lot_from_trade(raw: dict[str, Any], *, exchange_id: str, account_id: str, asset_class: str) -> PositionLot:
    from brokerai.trading.broker.adapters.oanda import lot_from_oanda_trade

    return lot_from_oanda_trade(
        raw,
        exchange_id=exchange_id,
        account_id=account_id,
        asset_class=asset_class,
    )


def _event_from_txn(raw: dict[str, Any], *, exchange_id: str, account_id: str) -> BrokerEvent:
    from brokerai.trading.broker.adapters.oanda import event_from_oanda_transaction

    return event_from_oanda_transaction(raw, exchange_id=exchange_id, account_id=account_id)


@dataclass
class ChildOrderPatch:
    broker_lot_id: str
    child: ChildOrder


@dataclass
class AccountChangesApplied:
    lots: list[PositionLot] = field(default_factory=list)
    events: list[BrokerEvent] = field(default_factory=list)
    child_order_patches: list[ChildOrderPatch] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


@dataclass
class AccountStateApplied:
    summary: dict[str, Any] = field(default_factory=dict)
    lot_pl_updates: dict[str, float] = field(default_factory=dict)
    changed_summary_fields: list[str] = field(default_factory=list)


def _normalize_trade_summary(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize OANDA TradeSummary from AccountChanges payloads."""
    if not isinstance(raw, dict):
        return None
    trade_id = raw.get("id") or raw.get("tradeID")
    if not trade_id:
        return None
    merged = dict(raw)
    merged.setdefault("id", trade_id)
    if "currentUnits" not in merged and "units" in merged:
        merged["currentUnits"] = merged["units"]
    if "initialUnits" not in merged and "currentUnits" in merged:
        merged["initialUnits"] = merged["currentUnits"]
    state = str(merged.get("state", "OPEN")).upper()
    if state == "CLOSED":
        return _normalize_oanda_trade_raw(merged)
    open_norm = _normalize_oanda_open_trade(merged)
    if open_norm is not None:
        return open_norm
    return _normalize_oanda_trade_raw(merged)


def lots_from_account_details(
    account: dict[str, Any],
    *,
    exchange_id: str = OANDA_EXCHANGE_ID,
    account_id: str,
    asset_class: str = DEFAULT_ASSET_CLASS,
) -> list[PositionLot]:
    """Build open position lots from an OANDA Account Details document."""
    lots: list[PositionLot] = []
    for raw in account.get("trades") or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_oanda_open_trade(raw) or _normalize_oanda_trade_raw(raw)
        if normalized is None:
            continue
        normalized["state"] = "OPEN"
        lots.append(
            _lot_from_trade(
                normalized,
                exchange_id=exchange_id,
                account_id=account_id,
                asset_class=asset_class,
            )
        )
    return lots


def summary_from_account(account: dict[str, Any]) -> dict[str, Any]:
    """Extract BrokerAI summary fields from a full OANDA account object."""
    return normalize_account_summary_fields(account)


def _child_order_from_normalized(raw: dict[str, Any] | None) -> ChildOrder | None:
    from brokerai.trading.broker.adapters.oanda import _child_order_from_normalized as _from_adapter

    return _from_adapter(raw)


def _child_order_patch_from_order(raw: dict[str, Any]) -> ChildOrderPatch | None:
    normalized = _normalize_oanda_child_order(raw)
    if normalized is None:
        return None
    trade_id = raw.get("tradeID") or normalized.get("trade_id")
    if not trade_id:
        return None
    child = _child_order_from_normalized(normalized)
    if child is None:
        return None
    return ChildOrderPatch(broker_lot_id=str(trade_id), child=child)


def _apply_child_order_patches(lots: list[PositionLot], patches: list[ChildOrderPatch]) -> None:
    from brokerai.trading.broker.child_orders import merge_child_order_patch

    if not patches:
        return
    by_lot_id = {lot.broker_lot_id: lot for lot in lots}
    for patch in patches:
        lot = by_lot_id.get(patch.broker_lot_id)
        if lot is None:
            continue
        merge_child_order_patch(lot, patch.child)


def apply_account_changes(
    changes: dict[str, Any],
    *,
    exchange_id: str,
    account_id: str,
    asset_class: str = DEFAULT_ASSET_CLASS,
) -> AccountChangesApplied:
    """Map OANDA AccountChanges to lots and broker events (idempotent inputs)."""
    result = AccountChangesApplied()

    def _add_lot(raw: dict[str, Any], *, state_hint: str | None = None) -> None:
        normalized = _normalize_trade_summary(raw)
        if normalized is None:
            return
        if state_hint:
            normalized["state"] = state_hint
        lot = _lot_from_trade(
            normalized,
            exchange_id=exchange_id,
            account_id=account_id,
            asset_class=asset_class,
        )
        result.lots.append(lot)

    for raw in changes.get("tradesOpened") or []:
        if isinstance(raw, dict):
            _add_lot(raw, state_hint="OPEN")
    result.counts["trades_opened"] = len(changes.get("tradesOpened") or [])

    for raw in changes.get("tradesReduced") or []:
        if isinstance(raw, dict):
            _add_lot(raw, state_hint="OPEN")
    result.counts["trades_reduced"] = len(changes.get("tradesReduced") or [])

    for raw in changes.get("tradesClosed") or []:
        if isinstance(raw, dict):
            _add_lot(raw, state_hint="CLOSED")
    result.counts["trades_closed"] = len(changes.get("tradesClosed") or [])

    for raw in changes.get("transactions") or []:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_oanda_transaction(raw)
        if normalized is None:
            continue
        result.events.append(
            _event_from_txn(
                normalized,
                exchange_id=exchange_id,
                account_id=account_id,
            )
        )
    result.counts["transactions"] = len(changes.get("transactions") or [])

    for section, count_key in (
        ("ordersCreated", "orders_created"),
        ("ordersFilled", "orders_filled"),
        ("ordersCancelled", "orders_cancelled"),
    ):
        for raw in changes.get(section) or []:
            if not isinstance(raw, dict):
                continue
            patch = _child_order_patch_from_order(raw)
            if patch is None:
                continue
            if section == "ordersCancelled" and patch.child.state.upper() != "CANCELLED":
                patch.child.state = "CANCELLED"
            elif section == "ordersFilled" and patch.child.state.upper() != "FILLED":
                patch.child.state = "FILLED"
            result.child_order_patches.append(patch)
        result.counts[count_key] = len(changes.get(section) or [])

    _apply_child_order_patches(result.lots, result.child_order_patches)

    return result


def apply_account_state(
    state: dict[str, Any],
    *,
    previous_summary: dict[str, Any] | None = None,
) -> AccountStateApplied:
    """Merge OANDA AccountChangesState into summary and per-trade PL (sparse-safe)."""
    result = AccountStateApplied()
    if not state:
        return result

    account_slice = state.get("account") if isinstance(state.get("account"), dict) else state
    summary = summary_from_account(account_slice) if account_slice else {}

    for key, value in summary.items():
        if value is not None:
            result.summary[key] = value

    for field_name in SUMMARY_FIELDS:
        if field_name not in result.summary:
            continue
        prev = (previous_summary or {}).get(field_name)
        cur = result.summary.get(field_name)
        if prev != cur:
            result.changed_summary_fields.append(field_name)

    for raw in state.get("trades") or []:
        if not isinstance(raw, dict):
            continue
        trade_id = raw.get("id") or raw.get("tradeID")
        pl = _optional_float(raw.get("unrealizedPL"))
        if trade_id and pl is not None:
            result.lot_pl_updates[str(trade_id)] = pl

    return result


def open_lots_from_account_state(
    state: dict[str, Any],
    *,
    exchange_id: str,
    account_id: str,
    asset_class: str = DEFAULT_ASSET_CLASS,
) -> list[PositionLot]:
    """Build open lots from AccountChangesState.trades when present."""
    lots: list[PositionLot] = []
    for raw in state.get("trades") or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_trade_summary(raw)
        if normalized is None:
            continue
        normalized["state"] = "OPEN"
        lot = _lot_from_trade(
            normalized,
            exchange_id=exchange_id,
            account_id=account_id,
            asset_class=asset_class,
        )
        pl = _optional_float(raw.get("unrealizedPL"))
        if pl is not None:
            lot.unrealized_pl = pl
        lots.append(lot)
    return lots


def detect_transaction_gap(
    transactions: list[dict[str, Any]],
    *,
    since_id: str,
    last_transaction_id: str | None,
) -> bool:
    """Return True when transaction IDs suggest a gap requiring sinceid repair."""
    if not transactions:
        return False
    try:
        since_num = int(since_id)
        last_num = int(last_transaction_id) if last_transaction_id else None
    except ValueError:
        return False

    ids: list[int] = []
    for raw in transactions:
        txn_id = raw.get("id")
        if txn_id is None:
            continue
        try:
            ids.append(int(str(txn_id)))
        except ValueError:
            continue
    if not ids:
        return False

    ids.sort()
    if ids[0] > since_num + 1:
        logger.warning(
            "OANDA transaction gap detected: since=%s first_in_batch=%s",
            since_id,
            ids[0],
        )
        return True

    if last_num is not None and last_num - since_num > len(ids) + 5:
        return True

    return False


def summary_changed(
    new_summary: dict[str, Any],
    previous: dict[str, Any] | None,
) -> bool:
    """True when any summary chart field differs from *previous*."""
    if not previous:
        return bool(new_summary)
    for field_name in SUMMARY_FIELDS:
        if new_summary.get(field_name) != previous.get(field_name):
            return True
    return False
