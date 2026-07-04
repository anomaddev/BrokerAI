from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from brokerai.integrations.oanda_client import (
    OANDA_ENVIRONMENTS,
    auth_headers,
    base_url,
    get_oanda_client,
)


logger = logging.getLogger(__name__)


def _auth_headers(access_token: str) -> dict[str, str]:
    return auth_headers(access_token)


async def _http_client(access_token: str, environment: str):
    return await get_oanda_client(access_token, environment)


async def list_accounts(access_token: str, environment: str) -> list[dict[str, Any]]:
    """Return the sub-accounts accessible with the given token.

    Raises httpx.HTTPError on transport failures and httpx.HTTPStatusError on
    non-2xx responses so callers can translate them into user-facing messages.
    """
    client = await _http_client(access_token, environment)
    data = await client.get_json("/v3/accounts", timeout=15.0)
    accounts = data.get("accounts") or []
    return [
        {"id": acc.get("id"), "tags": acc.get("tags") or []}
        for acc in accounts
        if acc.get("id")
    ]


def normalize_account_summary_fields(account: dict[str, Any]) -> dict[str, Any]:
    """Map OANDA account object fields to BrokerAI summary shape."""
    return {
        "id": account.get("id"),
        "alias": account.get("alias"),
        "currency": account.get("currency"),
        "balance": account.get("balance"),
        "nav": account.get("NAV"),
        "unrealized_pl": account.get("unrealizedPL"),
        "realized_pl": account.get("pl"),
        "margin_available": account.get("marginAvailable"),
        "margin_used": account.get("marginUsed"),
        "open_trade_count": account.get("openTradeCount"),
        "open_position_count": account.get("openPositionCount"),
        "pending_order_count": account.get("pendingOrderCount"),
    }


async def get_account_summary(
    access_token: str,
    environment: str,
    account_id: str,
) -> dict[str, Any]:
    """Fetch account summary for a single OANDA account."""
    client = await _http_client(access_token, environment)
    data = await client.get_json(f"/v3/accounts/{account_id}/summary", timeout=15.0)
    account = data.get("account") or {}
    return normalize_account_summary_fields(account)


async def get_account_details(
    access_token: str,
    environment: str,
    account_id: str,
) -> tuple[dict[str, Any], str | None]:
    """Fetch full OANDA account details (open trades, orders, positions).

    Returns ``(account_dict, lastTransactionID)``.
    """
    client = await _http_client(access_token, environment)
    data = await client.get_json(f"/v3/accounts/{account_id}", timeout=15.0)
    account = data.get("account") or {}
    last_txn = data.get("lastTransactionID")
    return account, str(last_txn) if last_txn else None


async def poll_account_changes(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    since_transaction_id: str,
) -> dict[str, Any]:
    """Poll OANDA account updates since *since_transaction_id*.

    Returns ``{changes, state, lastTransactionID}`` (keys may be absent).
    """
    client = await _http_client(access_token, environment)
    data = await client.get_json(
        f"/v3/accounts/{account_id}/changes",
        params={"sinceTransactionID": since_transaction_id},
        timeout=15.0,
    )
    last_txn = data.get("lastTransactionID")
    return {
        "changes": data.get("changes") or {},
        "state": data.get("state") or {},
        "lastTransactionID": str(last_txn) if last_txn else None,
    }


def instrument_to_pair(instrument: str) -> str:
    """Convert OANDA instrument id ``EUR_USD`` to ``EUR/USD``."""
    parts = instrument.strip().upper().split("_")
    if len(parts) == 2:
        return f"{parts[0]}/{parts[1]}"
    return instrument.replace("_", "/")


def _parse_broker_timestamp(raw: str | None) -> datetime | None:
    """Parse OANDA ISO-8601 timestamps (nanosecond precision) into UTC."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip().replace("Z", "+00:00")
    if "." in text:
        base, _, rest = text.partition(".")
        tz = ""
        if "+" in rest:
            frac, _, tz = rest.partition("+")
            tz = f"+{tz}"
        elif rest.count("-") > 0:
            frac, _, tz = rest.rpartition("-")
            tz = f"-{tz}"
        else:
            frac = rest
        text = f"{base}.{frac[:6]}{tz}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _normalize_oanda_open_trade(raw: dict[str, Any]) -> dict[str, Any] | None:
    trade_id = raw.get("id")
    instrument = raw.get("instrument")
    if not trade_id or not instrument:
        return None

    state = str(raw.get("state", "OPEN")).upper()
    if state != "OPEN":
        return None

    try:
        units = float(raw.get("currentUnits") or raw.get("initialUnits") or 0)
    except (TypeError, ValueError):
        units = 0.0
    if units == 0:
        return None

    direction = "long" if units > 0 else "short"
    price_raw = raw.get("price")
    try:
        price = float(price_raw) if price_raw is not None else 0.0
    except (TypeError, ValueError):
        price = 0.0
    pl_raw = raw.get("unrealizedPL")
    try:
        unrealized_pl = float(pl_raw) if pl_raw is not None else None
    except (TypeError, ValueError):
        unrealized_pl = None
    return {
        "id": str(trade_id),
        "instrument": str(instrument),
        "pair": instrument_to_pair(str(instrument)),
        "units": abs(units),
        "direction": direction,
        "price": price,
        "entry_price": price,
        "unrealized_pl": unrealized_pl,
        "current_price": None,
        "open_time": raw.get("openTime"),
        "initial_units": abs(float(raw.get("initialUnits") or units)),
        "current_units": abs(units),
        "financing": _optional_float(raw.get("financing")),
        "margin_used": _optional_float(raw.get("marginUsed")),
        "realized_pl": _optional_float(raw.get("realizedPL")),
        "stop_loss": _normalize_oanda_child_order(raw.get("stopLossOrder")),
        "take_profit": _normalize_oanda_child_order(raw.get("takeProfitOrder")),
        "state": "OPEN",
        "raw": raw,
    }


def _normalize_oanda_child_order(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    return {
        "broker_order_id": str(raw.get("id")),
        "order_type": str(raw.get("type", "")),
        "state": str(raw.get("state", "")),
        "price": _optional_float(raw.get("price")),
        "trade_id": str(raw.get("tradeID")) if raw.get("tradeID") else None,
        "create_time": raw.get("createTime"),
        "filled_time": raw.get("filledTime"),
        "filling_event_id": str(raw.get("fillingTransactionID"))
        if raw.get("fillingTransactionID")
        else None,
        "cancelling_event_id": str(raw.get("cancellingTransactionID"))
        if raw.get("cancellingTransactionID")
        else None,
    }


def _normalize_oanda_trade_raw(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize any OANDA trade payload (open or closed)."""
    trade_id = raw.get("id")
    instrument = raw.get("instrument")
    if not trade_id or not instrument:
        return None

    state = str(raw.get("state", "")).upper()
    try:
        initial_units = float(raw.get("initialUnits") or 0)
    except (TypeError, ValueError):
        initial_units = 0.0
    if initial_units == 0:
        return None

    try:
        current_units = float(raw.get("currentUnits") or initial_units)
    except (TypeError, ValueError):
        current_units = initial_units

    direction = "long" if initial_units > 0 else "short"
    entry_price = _optional_float(raw.get("price")) or 0.0

    return {
        "id": str(trade_id),
        "instrument": str(instrument),
        "pair": instrument_to_pair(str(instrument)),
        "direction": direction,
        "initial_units": abs(initial_units),
        "current_units": abs(current_units),
        "entry_price": entry_price,
        "exit_price": _optional_float(raw.get("averageClosePrice")),
        "realized_pl": _optional_float(raw.get("realizedPL")),
        "unrealized_pl": _optional_float(raw.get("unrealizedPL")),
        "financing": _optional_float(raw.get("financing")),
        "margin_used": _optional_float(raw.get("marginUsed")),
        "open_time": raw.get("openTime"),
        "close_time": raw.get("closeTime"),
        "closed_at": _parse_broker_timestamp(raw.get("closeTime")),
        "closing_event_ids": [str(x) for x in (raw.get("closingTransactionIDs") or [])],
        "stop_loss": _normalize_oanda_child_order(raw.get("stopLossOrder")),
        "take_profit": _normalize_oanda_child_order(raw.get("takeProfitOrder")),
        "state": state,
        "raw": raw,
    }


def normalize_oanda_transaction(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a single OANDA transaction payload."""
    payload = raw.get("transaction") if isinstance(raw.get("transaction"), dict) else raw
    if not isinstance(payload, dict):
        return None
    txn_id = payload.get("id")
    if not txn_id:
        return None

    trade_id = payload.get("tradeID")
    if not trade_id:
        trade_closed = payload.get("tradeClosed") or {}
        if isinstance(trade_closed, dict):
            trade_id = trade_closed.get("tradeID")
        trades_closed = payload.get("tradesClosed") or []
        if not trade_id and trades_closed:
            first = trades_closed[0]
            if isinstance(first, dict):
                trade_id = first.get("tradeID")

    order_id = payload.get("orderID")
    if not order_id and isinstance(payload.get("orderFillTransaction"), dict):
        order_id = payload["orderFillTransaction"].get("id")

    units_raw = payload.get("units")
    if units_raw is None:
        trade_opened = payload.get("tradeOpened") or {}
        if isinstance(trade_opened, dict):
            units_raw = trade_opened.get("units")

    return {
        "id": str(txn_id),
        "type": str(payload.get("type", "")),
        "time": payload.get("time"),
        "batch_id": str(payload.get("batchID")) if payload.get("batchID") else None,
        "request_id": payload.get("requestID"),
        "trade_id": str(trade_id) if trade_id else None,
        "order_id": str(order_id) if order_id else None,
        "instrument": payload.get("instrument"),
        "units": _optional_float(units_raw),
        "price": _optional_float(payload.get("price")),
        "pl": _optional_float(payload.get("pl")),
        "reason": payload.get("reason"),
        "raw": payload,
    }


def _pricing_mid_price(raw: dict[str, Any]) -> float | None:
    """Return mid price from an OANDA pricing payload row."""
    bids = raw.get("bids") or []
    asks = raw.get("asks") or []
    try:
        bid = float(bids[0]["price"]) if bids else None
        ask = float(asks[0]["price"]) if asks else None
    except (IndexError, KeyError, TypeError, ValueError):
        bid = None
        ask = None
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    closeout = raw.get("closeoutBid") or raw.get("closeoutAsk")
    if closeout is not None:
        try:
            return float(closeout)
        except (TypeError, ValueError):
            return None
    return None


async def fetch_account_pricing(
    access_token: str,
    environment: str,
    account_id: str,
    instruments: list[str],
) -> dict[str, float]:
    """Fetch latest mid prices for OANDA instruments.

    Returns a map of instrument id (e.g. ``EUR_USD``) to mid price. Unknown or
    invalid instruments are omitted.
    """
    unique = sorted({inst.strip().upper() for inst in instruments if inst and inst.strip()})
    if not unique:
        return {}

    params = {"instruments": ",".join(unique)}
    http = await _http_client(access_token, environment)
    data = await http.get_json(
        f"/v3/accounts/{account_id}/pricing",
        params=params,
        timeout=15.0,
    )

    prices: dict[str, float] = {}
    for raw in data.get("prices") or []:
        if not isinstance(raw, dict):
            continue
        instrument = raw.get("instrument")
        mid = _pricing_mid_price(raw)
        if instrument and mid is not None:
            prices[str(instrument).upper()] = mid
    return prices


def attach_current_prices_to_broker_trades(
    trades: list[dict[str, Any]],
    prices_by_instrument: dict[str, float],
) -> list[dict[str, Any]]:
    """Attach ``current_price`` to normalized broker open trades."""
    for trade in trades:
        instrument = str(trade.get("instrument", "")).upper()
        trade["current_price"] = prices_by_instrument.get(instrument)
    return trades


def parse_oanda_close_response(response: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized close fields from an OANDA trade-close response.

    OANDA may populate ``orderFillTransaction`` (market close) with
    ``tradeClosed`` or ``tradesClosed`` entries.
    """
    fill = response.get("orderFillTransaction") or {}
    trade_closed = fill.get("tradeClosed") or {}
    trades_closed = fill.get("tradesClosed") or []

    exit_price = _optional_float(fill.get("price"))
    realized_pl = _optional_float(fill.get("pl"))

    if realized_pl is None and trades_closed:
        total = 0.0
        found = False
        for entry in trades_closed:
            if not isinstance(entry, dict):
                continue
            pl = _optional_float(entry.get("realizedPL"))
            if pl is not None:
                total += pl
                found = True
        if found:
            realized_pl = total

    if realized_pl is None:
        realized_pl = _optional_float(trade_closed.get("realizedPL"))

    closed_at = _parse_broker_timestamp(fill.get("time"))
    broker_trade_id = trade_closed.get("tradeID")
    if not broker_trade_id and trades_closed:
        first = trades_closed[0]
        if isinstance(first, dict):
            broker_trade_id = first.get("tradeID")

    return {
        "exit_price": exit_price,
        "realized_pl": realized_pl,
        "closed_at": closed_at,
        "broker_trade_id": str(broker_trade_id) if broker_trade_id else None,
    }


def _normalize_oanda_closed_trade(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a CLOSED OANDA trade payload."""
    trade_id = raw.get("id")
    instrument = raw.get("instrument")
    if not trade_id or not instrument:
        return None

    state = str(raw.get("state", "")).upper()
    if state != "CLOSED":
        return None

    try:
        initial_units = float(raw.get("initialUnits") or 0)
    except (TypeError, ValueError):
        initial_units = 0.0
    if initial_units == 0:
        return None

    direction = "long" if initial_units > 0 else "short"
    entry_price = _optional_float(raw.get("price")) or 0.0
    exit_price = _optional_float(raw.get("averageClosePrice"))
    realized_pl = _optional_float(raw.get("realizedPL"))

    return {
        "id": str(trade_id),
        "instrument": str(instrument),
        "pair": instrument_to_pair(str(instrument)),
        "units": abs(initial_units),
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "realized_pl": realized_pl,
        "open_time": raw.get("openTime"),
        "close_time": raw.get("closeTime"),
        "closed_at": _parse_broker_timestamp(raw.get("closeTime")),
        "closing_event_ids": [str(x) for x in (raw.get("closingTransactionIDs") or [])],
        "stop_loss": _normalize_oanda_child_order(raw.get("stopLossOrder")),
        "take_profit": _normalize_oanda_child_order(raw.get("takeProfitOrder")),
        "financing": _optional_float(raw.get("financing")),
        "state": "CLOSED",
        "raw": raw,
    }


async def list_trades(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    state: str | None = None,
    count: int = 500,
    before_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch OANDA trades with optional state filter and pagination.

    Returns ``(normalized_trades, last_transaction_id)``.
    """
    if not access_token.strip() or not account_id.strip():
        return [], None

    params: dict[str, Any] = {"count": max(1, min(count, 1000))}
    if state:
        params["state"] = state.upper()
    if before_id:
        params["beforeID"] = before_id

    http = await _http_client(access_token, environment)
    data = await http.get_json(
        f"/v3/accounts/{account_id}/trades",
        params=params,
        timeout=30.0,
    )

    trades: list[dict[str, Any]] = []
    for raw in data.get("trades") or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_oanda_trade_raw(raw)
        if normalized is not None:
            trades.append(normalized)

    last_txn = data.get("lastTransactionID")
    return trades, str(last_txn) if last_txn else None


async def list_all_trades(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    state: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginate through all OANDA trades."""
    all_trades: list[dict[str, Any]] = []
    before_id: str | None = None
    last_txn: str | None = None

    while True:
        batch, last_txn = await list_trades(
            access_token,
            environment,
            account_id,
            state=state,
            before_id=before_id,
        )
        if not batch:
            break
        all_trades.extend(batch)
        if len(batch) < 500:
            break
        before_id = batch[-1]["id"]

    return all_trades, last_txn


def _transactions_from_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize transaction objects from an OANDA list/idrange/sinceid payload."""
    events: list[dict[str, Any]] = []
    for raw in data.get("transactions") or []:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_oanda_transaction(raw)
        if normalized is not None:
            events.append(normalized)
    return events


async def _iter_transaction_pages(
    http: Any,
    *,
    initial_path: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield normalized transaction batches one OANDA response page at a time."""
    data = await http.get_json(initial_path, params=params, timeout=timeout)
    page_events = _transactions_from_payload(data)
    if page_events:
        yield page_events

    for page_url in data.get("pages") or []:
        if not isinstance(page_url, str) or not page_url.strip():
            continue
        page_data = await http.get_json(page_url, timeout=timeout)
        page_events = _transactions_from_payload(page_data)
        if page_events:
            yield page_events


async def _fetch_paginated_transactions(
    http: Any,
    *,
    initial_path: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch all transaction pages from an OANDA idrange or sinceid response."""
    all_events: list[dict[str, Any]] = []
    last_txn: str | None = None

    data = await http.get_json(initial_path, params=params, timeout=timeout)
    all_events.extend(_transactions_from_payload(data))
    raw_last = data.get("lastTransactionID")
    if raw_last is not None:
        last_txn = str(raw_last)

    for page_url in data.get("pages") or []:
        if not isinstance(page_url, str) or not page_url.strip():
            continue
        page_data = await http.get_json(page_url, timeout=timeout)
        all_events.extend(_transactions_from_payload(page_data))
        page_last = page_data.get("lastTransactionID")
        if page_last is not None:
            last_txn = str(page_last)

    return all_events, last_txn


async def iter_transactions_idrange(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    from_id: str,
    to_id: str,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield normalized transactions per OANDA page for an inclusive ID range."""
    params = {"from": from_id, "to": to_id}
    http = await _http_client(access_token, environment)
    async for page in _iter_transaction_pages(
        http,
        initial_path=f"/v3/accounts/{account_id}/transactions/idrange",
        params=params,
        timeout=30.0,
    ):
        yield page


async def iter_transactions_since(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    since_id: str,
) -> AsyncIterator[list[dict[str, Any]]]:
    """Yield normalized transactions per OANDA page since *since_id* (exclusive)."""
    params = {"id": since_id}
    http = await _http_client(access_token, environment)
    async for page in _iter_transaction_pages(
        http,
        initial_path=f"/v3/accounts/{account_id}/transactions/sinceid",
        params=params,
        timeout=30.0,
    ):
        yield page


async def list_transactions_idrange(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    from_id: str,
    to_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch OANDA transactions in an inclusive ID range (all pages)."""
    params = {"from": from_id, "to": to_id}
    http = await _http_client(access_token, environment)
    return await _fetch_paginated_transactions(
        http,
        initial_path=f"/v3/accounts/{account_id}/transactions/idrange",
        params=params,
        timeout=30.0,
    )


async def list_transactions_since(
    access_token: str,
    environment: str,
    account_id: str,
    *,
    since_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch OANDA transactions since *since_id* (exclusive, all pages)."""
    params = {"id": since_id}
    http = await _http_client(access_token, environment)
    return await _fetch_paginated_transactions(
        http,
        initial_path=f"/v3/accounts/{account_id}/transactions/sinceid",
        params=params,
        timeout=30.0,
    )


async def get_transaction(
    access_token: str,
    environment: str,
    account_id: str,
    transaction_id: str,
) -> dict[str, Any] | None:
    """Fetch a single OANDA transaction by id."""
    http = await _http_client(access_token, environment)
    response = await http.get(
        f"/v3/accounts/{account_id}/transactions/{transaction_id}",
        timeout=15.0,
        allow_404=True,
    )
    if response.status_code == 404:
        return None
    data = response.json()

    raw = data.get("transaction")
    if not isinstance(raw, dict):
        return None
    return normalize_oanda_transaction(raw)


async def list_pending_orders(
    access_token: str,
    environment: str,
    account_id: str,
) -> list[dict[str, Any]]:
    """Fetch pending OANDA orders for an account."""
    http = await _http_client(access_token, environment)
    data = await http.get_json(f"/v3/accounts/{account_id}/pendingOrders", timeout=15.0)
    return [o for o in (data.get("orders") or []) if isinstance(o, dict)]


async def list_positions(
    access_token: str,
    environment: str,
    account_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch OANDA open positions for validation."""
    http = await _http_client(access_token, environment)
    data = await http.get_json(f"/v3/accounts/{account_id}/positions", timeout=15.0)
    positions = [p for p in (data.get("positions") or []) if isinstance(p, dict)]
    last_txn = data.get("lastTransactionID")
    return positions, str(last_txn) if last_txn else None


async def get_broker_trade(
    access_token: str,
    environment: str,
    account_id: str,
    trade_id: str,
) -> dict[str, Any] | None:
    """Fetch a single OANDA trade by id (open or closed)."""
    if not access_token.strip() or not account_id.strip() or not trade_id.strip():
        return None

    http = await _http_client(access_token, environment)
    response = await http.get(
        f"/v3/accounts/{account_id}/trades/{trade_id}",
        timeout=15.0,
        allow_404=True,
    )
    if response.status_code == 404:
        return None
    data = response.json()

    raw = data.get("trade")
    if not isinstance(raw, dict):
        return None

    state = str(raw.get("state", "")).upper()
    if state == "CLOSED":
        return _normalize_oanda_closed_trade(raw)
    return _normalize_oanda_open_trade(raw)


def extract_broker_trade_id(order_response: dict[str, Any]) -> str | None:
    """Return the OANDA trade ID from an order response, not the transaction ID."""
    order_fill = order_response.get("orderFillTransaction") or {}
    trade_opened = order_fill.get("tradeOpened") or {}
    trade_id = trade_opened.get("tradeID")
    if trade_id:
        return str(trade_id)
    return None


async def get_broker_open_trades_snapshot(
    access_token: str,
    environment: str,
    account_id: str,
) -> dict[str, Any]:
    """Fetch OANDA open-trade count and details.

    Uses account summary ``openTradeCount`` as the authoritative count. When that
    count is zero, returns an empty trade list even if ``/openTrades`` returns
    stale or zero-unit legs.
    """
    summary = await get_account_summary(access_token, environment, account_id)
    raw_count = summary.get("open_trade_count")
    try:
        open_trade_count = int(raw_count) if raw_count is not None else 0
    except (TypeError, ValueError):
        open_trade_count = 0

    if open_trade_count <= 0:
        return {
            "open_trade_count": 0,
            "trades": [],
            "summary": summary,
        }

    trades = await list_open_trades(access_token, environment, account_id)
    instruments = [str(t.get("instrument", "")) for t in trades if t.get("instrument")]
    prices = await fetch_account_pricing(access_token, environment, account_id, instruments)
    attach_current_prices_to_broker_trades(trades, prices)
    return {
        "open_trade_count": open_trade_count,
        "trades": trades,
        "summary": summary,
    }


async def list_open_trades(
    access_token: str,
    environment: str,
    account_id: str,
) -> list[dict[str, Any]]:
    """Fetch open trades for a single OANDA account."""
    http = await _http_client(access_token, environment)
    data = await http.get_json(f"/v3/accounts/{account_id}/openTrades", timeout=15.0)
    trades: list[dict[str, Any]] = []
    for raw in data.get("trades") or []:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_oanda_open_trade(raw)
        if normalized is not None:
            trades.append(normalized)
    return trades


async def test_connection(
    access_token: str,
    environment: str,
    account_id: str | None = None,
) -> tuple[bool, str, list[dict[str, Any]]]:
    """Verify OANDA credentials and optionally confirm a specific account.

    Returns (ok, message, accounts).
    """
    if not access_token.strip():
        return False, "OANDA access token is not configured", []
    if environment not in OANDA_ENVIRONMENTS:
        return False, f"Unknown OANDA environment '{environment}'", []

    try:
        accounts = await list_accounts(access_token, environment)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            return False, "Invalid OANDA access token", []
        if status == 403:
            return False, "Token is not authorized for this environment", []
        return False, f"OANDA returned HTTP {status}", []
    except httpx.HTTPError as exc:
        return False, f"OANDA request failed: {exc}", []

    if not accounts:
        return False, "No OANDA accounts are accessible with this token", []

    if account_id:
        if not any(acc["id"] == account_id for acc in accounts):
            return False, f"Account {account_id} is not accessible with this token", accounts
        return True, f"OANDA connection successful (account {account_id})", accounts

    return True, f"OANDA connection successful ({len(accounts)} account(s) found)", accounts


def forex_pair_to_instrument(pair: str) -> str:
    """Convert ``EUR/USD`` to OANDA instrument id ``EUR_USD``."""
    return pair.replace("/", "_").strip().upper()


def oanda_price_precision(instrument: str) -> int:
    """Return decimal places for OANDA order prices on *instrument*.

    JPY-quoted pairs (``*_JPY``) use 3 dp; most other majors use 5 dp.
    """
    normalized = instrument.strip().upper().replace("/", "_")
    if normalized.endswith("_JPY"):
        return 3
    return 5


def format_oanda_price(price: float, instrument: str) -> str:
    """Format *price* for OANDA ``stopLossOnFill`` / ``takeProfitOnFill`` payloads."""
    precision = oanda_price_precision(instrument)
    return f"{price:.{precision}f}"


class OandaOrderError(ValueError):
    """Raised when OANDA rejects or cancels an order without a fill."""


def _raise_for_oanda_order_response(response: httpx.Response) -> dict[str, Any]:
    """Parse an OANDA order response and raise when no fill occurred."""
    if not response.is_success:
        response.raise_for_status()

    payload = response.json()
    reject = payload.get("orderRejectTransaction")
    if reject:
        reason = str(reject.get("rejectReason") or "ORDER_REJECTED")
        raise OandaOrderError(f"OANDA rejected order: {reason}")

    if payload.get("orderCancelTransaction") and not payload.get("orderFillTransaction"):
        cancel = payload["orderCancelTransaction"]
        reason = str(cancel.get("reason") or "ORDER_CANCELLED")
        raise OandaOrderError(f"OANDA cancelled order: {reason}")

    return payload


OANDA_GRANULARITY_BY_TIMEFRAME: dict[str, str] = {
    "M1": "M1",
    "M2": "M2",
    "M4": "M4",
    "M5": "M5",
    "M10": "M10",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H2": "H2",
    "H3": "H3",
    "H4": "H4",
    "H6": "H6",
    "H8": "H8",
    "H12": "H12",
    "D1": "D",
    "W1": "W",
    "MN": "M",
}


def granularity_to_duration(granularity: str) -> timedelta:
    """Map an OANDA granularity code to a bar duration."""
    for timeframe, mapped in OANDA_GRANULARITY_BY_TIMEFRAME.items():
        if mapped == granularity:
            from brokerai.bots.data_manager.candle_schedule import timeframe_to_duration

            return timeframe_to_duration(timeframe)
    raise ValueError(f"Unsupported OANDA granularity: {granularity}")


def timeframe_to_granularity(timeframe: str) -> str | None:
    return OANDA_GRANULARITY_BY_TIMEFRAME.get(timeframe)


def normalize_oanda_candle(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a closed OANDA candle payload to a compact OHLCV dict."""
    if raw.get("complete") is not True:
        return None

    mid = raw.get("mid") or raw.get("bid") or raw.get("ask")
    if not isinstance(mid, dict):
        return None

    try:
        return {
            "time": raw["time"],
            "open": float(mid["o"]),
            "high": float(mid["h"]),
            "low": float(mid["l"]),
            "close": float(mid["c"]),
            "volume": int(raw.get("volume") or 0),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _parse_oanda_candles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for raw in payload.get("candles") or []:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_oanda_candle(raw)
        if normalized is not None:
            candles.append(normalized)
    return candles


def _oanda_request_count(requested: int) -> int:
    """Request one extra bar so filtering incomplete candles still yields enough closed bars."""
    return max(1, min(int(requested) + 1, 5000))


def _trim_closed_candles(candles: list[dict[str, Any]], requested: int) -> list[dict[str, Any]]:
    if len(candles) <= requested:
        return candles
    return candles[-requested:]


async def _get_candles_payload(
    access_token: str,
    environment: str,
    instrument: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    http = await _http_client(access_token, environment)
    return await http.get_json(
        f"/v3/instruments/{instrument}/candles",
        params=params,
        timeout=30.0,
    )


async def fetch_candles(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    count: int,
    *,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    params = {
        "granularity": granularity,
        "count": _oanda_request_count(count),
        "price": price,
    }
    payload = await _get_candles_payload(access_token, environment, instrument, params)

    return _trim_closed_candles(_parse_oanda_candles(payload), count)


async def fetch_candles_to(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    to_time: str,
    *,
    count: int = 5000,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA ending at *to_time* (exclusive)."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    params = {
        "granularity": granularity,
        "to": to_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    payload = await _get_candles_payload(access_token, environment, instrument, params)

    return _trim_closed_candles(_parse_oanda_candles(payload), count)


async def fetch_candles_from(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    from_time: str,
    *,
    count: int = 5000,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch mid OHLCV candles from OANDA starting at *from_time* (inclusive)."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")

    params = {
        "granularity": granularity,
        "from": from_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    payload = await _get_candles_payload(access_token, environment, instrument, params)

    return _trim_closed_candles(_parse_oanda_candles(payload), count)


async def fetch_candles_range(
    access_token: str,
    environment: str,
    instrument: str,
    granularity: str,
    from_time: str,
    to_time: str,
    *,
    max_chunk: int = 5000,
    price: str = "M",
) -> list[dict[str, Any]]:
    """Fetch all closed candles in ``[from_time, to_time]`` with forward pagination."""
    if from_time > to_time:
        return []

    collected: list[dict[str, Any]] = []
    cursor = from_time
    chunk = max(1, min(int(max_chunk), 5000))

    while True:
        batch = await fetch_candles_from(
            access_token,
            environment,
            instrument,
            granularity,
            cursor,
            count=chunk,
            price=price,
        )
        if not batch:
            break

        for candle in batch:
            candle_time = str(candle.get("time", ""))
            if candle_time < from_time:
                continue
            if candle_time > to_time:
                return collected
            if not collected or collected[-1]["time"] != candle_time:
                collected.append(candle)

        last_time = str(batch[-1]["time"])
        if last_time >= to_time or len(batch) < chunk:
            break
        from brokerai.trading.data.time_utils import format_oanda_time, parse_oanda_time

        last_dt = parse_oanda_time(last_time)
        cursor = format_oanda_time(last_dt + granularity_to_duration(granularity))

    return collected


async def place_market_order(
    access_token: str,
    environment: str,
    account_id: str,
    instrument: str,
    *,
    units: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Place a market order on OANDA."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")
    if not account_id.strip():
        raise ValueError("OANDA account id is not configured")

    order: dict[str, Any] = {
        "type": "MARKET",
        "instrument": instrument,
        "units": str(int(units)) if units == int(units) else str(units),
        "timeInForce": "FOK",
        "positionFill": "DEFAULT",
    }
    if stop_loss is not None:
        order["stopLossOnFill"] = {"price": format_oanda_price(stop_loss, instrument)}
    if take_profit is not None:
        order["takeProfitOnFill"] = {"price": format_oanda_price(take_profit, instrument)}

    http = await _http_client(access_token, environment)
    response = await http.request(
        "POST",
        f"/v3/accounts/{account_id}/orders",
        json={"order": order},
        timeout=30.0,
    )
    return _raise_for_oanda_order_response(response)


async def close_broker_trade(
    access_token: str,
    environment: str,
    account_id: str,
    trade_id: str,
) -> dict[str, Any]:
    """Close an open OANDA trade by broker trade id."""
    if not access_token.strip():
        raise ValueError("OANDA access token is not configured")
    if not account_id.strip():
        raise ValueError("OANDA account id is not configured")
    if not trade_id.strip():
        raise ValueError("OANDA trade id is required")

    http = await _http_client(access_token, environment)
    response = await http.request(
        "PUT",
        f"/v3/accounts/{account_id}/trades/{trade_id}/close",
        json={"units": "ALL"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()
