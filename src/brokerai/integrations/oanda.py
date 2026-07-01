from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

OANDA_ENVIRONMENTS = ("practice", "live")

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def base_url(environment: str) -> str:
    return _BASE_URLS.get(environment, _BASE_URLS["practice"])


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token.strip()}"}


async def list_accounts(access_token: str, environment: str) -> list[dict[str, Any]]:
    """Return the sub-accounts accessible with the given token.

    Raises httpx.HTTPError on transport failures and httpx.HTTPStatusError on
    non-2xx responses so callers can translate them into user-facing messages.
    """
    url = f"{base_url(environment)}/v3/accounts"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    accounts = data.get("accounts") or []
    return [
        {"id": acc.get("id"), "tags": acc.get("tags") or []}
        for acc in accounts
        if acc.get("id")
    ]


async def get_account_summary(
    access_token: str,
    environment: str,
    account_id: str,
) -> dict[str, Any]:
    """Fetch account summary for a single OANDA account."""
    url = f"{base_url(environment)}/v3/accounts/{account_id}/summary"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
    account = data.get("account") or {}
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
        "unrealized_pl": unrealized_pl,
        "current_price": None,
        "open_time": raw.get("openTime"),
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

    url = f"{base_url(environment)}/v3/accounts/{account_id}/pricing"
    params = {"instruments": ",".join(unique)}
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token), params=params)
        response.raise_for_status()
        data = response.json()

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
    }


async def get_broker_trade(
    access_token: str,
    environment: str,
    account_id: str,
    trade_id: str,
) -> dict[str, Any] | None:
    """Fetch a single OANDA trade by id (open or closed)."""
    if not access_token.strip() or not account_id.strip() or not trade_id.strip():
        return None

    url = f"{base_url(environment)}/v3/accounts/{account_id}/trades/{trade_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        if response.status_code == 404:
            return None
        response.raise_for_status()
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
    url = f"{base_url(environment)}/v3/accounts/{account_id}/openTrades"
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers=_auth_headers(access_token))
        response.raise_for_status()
        data = response.json()
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


def _should_retry_oanda(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(_should_retry_oanda),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    reraise=True,
)
async def _get_candles(
    client: httpx.AsyncClient,
    url: str,
    *,
    access_token: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = await client.get(url, headers=_auth_headers(access_token), params=params)
    response.raise_for_status()
    return response.json()


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

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = await _get_candles(
            client,
            url,
            access_token=access_token,
            params=params,
        )

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

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "to": to_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = await _get_candles(
            client,
            url,
            access_token=access_token,
            params=params,
        )

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

    url = f"{base_url(environment)}/v3/instruments/{instrument}/candles"
    params = {
        "granularity": granularity,
        "from": from_time,
        "count": _oanda_request_count(count),
        "price": price,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = await _get_candles(
            client,
            url,
            access_token=access_token,
            params=params,
        )

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
        cursor = last_time

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

    url = f"{base_url(environment)}/v3/accounts/{account_id}/orders"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={**_auth_headers(access_token), "Content-Type": "application/json"},
            json={"order": order},
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

    url = f"{base_url(environment)}/v3/accounts/{account_id}/trades/{trade_id}/close"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            url,
            headers={**_auth_headers(access_token), "Content-Type": "application/json"},
            json={"units": "ALL"},
        )
        response.raise_for_status()
        return response.json()
