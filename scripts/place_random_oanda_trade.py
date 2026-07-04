#!/usr/bin/env python3
"""Place a random OANDA market order for manual testing.

Uses OANDA credentials stored in MongoDB (Settings → Exchange Connections).
Defaults to the practice environment and small unit sizes.

Examples:
  python scripts/place_random_oanda_trade.py --dry-run
  python scripts/place_random_oanda_trade.py --record
  python scripts/place_random_oanda_trade.py --pair EUR/USD --direction long
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from typing import Any

from brokerai.db.client import close_db, get_db
from brokerai.db.repositories.asset_settings import FOREX_PAIR_CATALOG
from brokerai.db.repositories.exchange_connections import ExchangeConnectionsRepository
from brokerai.db.repositories.broker_lots import BrokerLotsRepository
from brokerai.trading.broker.models import PositionLot
from brokerai.integrations.oanda import (
    OANDA_ENVIRONMENTS,
    extract_broker_trade_id,
    fetch_candles,
    forex_pair_to_instrument,
    place_market_order,
    test_connection,
)

# Liquid majors — safer defaults for smoke tests than exotic crosses.
DEFAULT_PAIRS = (
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "USD/CAD",
    "AUD/USD",
    "NZD/USD",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place a random OANDA market order for testing.",
    )
    parser.add_argument(
        "--pair",
        help="Forex pair (e.g. EUR/USD). Random major pair when omitted.",
    )
    parser.add_argument(
        "--direction",
        choices=("long", "short"),
        help="Trade direction. Random when omitted.",
    )
    parser.add_argument(
        "--units",
        type=float,
        default=1000.0,
        help="Absolute unit size before direction sign (default: 1000).",
    )
    parser.add_argument(
        "--all-pairs",
        action="store_true",
        help="Pick randomly from the full forex catalog instead of majors only.",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Allow placing orders on a live OANDA account (default: practice only).",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Persist the trade in MongoDB via BrokerLotsRepository.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the order that would be placed without calling OANDA.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )
    return parser.parse_args(argv)


def _choose_pair(args: argparse.Namespace) -> str:
    if args.pair:
        normalized = args.pair.strip().upper().replace("_", "/")
        if "/" not in normalized and len(normalized) == 6:
            normalized = f"{normalized[:3]}/{normalized[3:]}"
        if normalized not in FOREX_PAIR_CATALOG:
            raise ValueError(
                f"Unknown forex pair {args.pair!r}. "
                f"Use one of: {', '.join(FOREX_PAIR_CATALOG)}"
            )
        return normalized

    pool = list(FOREX_PAIR_CATALOG if args.all_pairs else DEFAULT_PAIRS)
    return random.choice(pool)


def _choose_direction(args: argparse.Namespace) -> str:
    return args.direction or random.choice(("long", "short"))


def _signed_units(units: float, direction: str) -> float:
    magnitude = abs(units)
    if magnitude <= 0:
        raise ValueError("--units must be greater than zero")
    return magnitude if direction == "long" else -magnitude


async def _load_oanda_config() -> dict[str, Any]:
    await get_db()
    return await ExchangeConnectionsRepository().get_oanda()


async def _latest_mid_price(
    access_token: str,
    environment: str,
    instrument: str,
) -> float | None:
    candles = await fetch_candles(access_token, environment, instrument, "M1", 1)
    if not candles:
        return None
    return float(candles[-1]["close"])


async def _place_trade(args: argparse.Namespace) -> dict[str, Any]:
    oanda = await _load_oanda_config()
    access_token = str(oanda.get("access_token") or "").strip()
    environment = str(oanda.get("environment") or "practice").strip()
    account_id = str(oanda.get("account_id") or "").strip()

    if not access_token or not account_id:
        raise RuntimeError(
            "OANDA is not configured. Set access token and account id in "
            "Settings → Exchange Connections (or MongoDB exchange_connections)."
        )
    if environment not in OANDA_ENVIRONMENTS:
        raise RuntimeError(f"Unknown OANDA environment {environment!r}")
    if environment == "live" and not args.allow_live:
        raise RuntimeError(
            "Refusing to trade on a live OANDA account. "
            "Use --allow-live if you really intend to."
        )

    ok, message, _accounts = await test_connection(access_token, environment, account_id)
    if not ok:
        raise RuntimeError(message)

    pair = _choose_pair(args)
    direction = _choose_direction(args)
    instrument = forex_pair_to_instrument(pair)
    units = _signed_units(args.units, direction)

    plan = {
        "pair": pair,
        "instrument": instrument,
        "direction": direction,
        "units": units,
        "environment": environment,
        "account_id": account_id,
    }

    if args.dry_run:
        return {"ok": True, "dry_run": True, "plan": plan}

    response = await place_market_order(
        access_token,
        environment,
        account_id,
        instrument,
        units=units,
    )
    order_fill = response.get("orderFillTransaction") or response.get("orderCreateTransaction") or {}
    broker_trade_id = extract_broker_trade_id(response) or str(order_fill.get("id") or "") or None
    fill_price_raw = order_fill.get("price")
    try:
        fill_price = float(fill_price_raw) if fill_price_raw is not None else None
    except (TypeError, ValueError):
        fill_price = None

    result: dict[str, Any] = {
        "ok": True,
        "dry_run": False,
        "plan": plan,
        "broker_trade_id": broker_trade_id,
        "fill_price": fill_price,
        "oanda_response": response,
    }

    if args.record:
        entry_price = fill_price
        if entry_price is None:
            entry_price = await _latest_mid_price(access_token, environment, instrument)
        trade_payload = {
            "strategy_id": "test-script",
            "strategy_name": "Random OANDA Test Trade",
            "pair": pair,
            "asset_class": "forex",
            "direction": direction,
            "confidence": 0.0,
            "entry_price": entry_price or 0.0,
            "stop_loss": None,
            "take_profit": None,
            "exit_mode": "manual",
            "risk_pct": 0.0,
            "units": units,
            "execution_reason": "random_trade",
            "metadata": {"source": "scripts/place_random_oanda_trade.py"},
        }
        recorded = await BrokerLotsRepository().upsert_lot(
            PositionLot(
                exchange_id="oanda",
                account_id="",
                broker_lot_id=str(broker_trade_id),
                asset_class="forex",
                state="open",
                instrument=pair.replace("/", "_"),
                symbol=pair.replace("/", "_"),
                direction=direction,
                initial_qty=abs(float(units)),
                current_qty=abs(float(units)),
                entry_price=entry_price or 0.0,
                strategy_id="test-script",
                strategy_name="Random OANDA Test Trade",
                execution_reason="random_trade",
                confidence=0.0,
                risk_pct=0.0,
                exit_mode="manual",
            ),
            preserve_overlay=False,
        )
        result["recorded_trade"] = recorded

    return result


def _print_result(result: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return

    if result.get("dry_run"):
        plan = result["plan"]
        print("Dry run — no order sent.")
        print(f"  Pair:        {plan['pair']} ({plan['instrument']})")
        print(f"  Direction:   {plan['direction']}")
        print(f"  Units:       {plan['units']}")
        print(f"  Environment: {plan['environment']}")
        print(f"  Account:     {plan['account_id']}")
        return

    plan = result["plan"]
    print("Order placed.")
    print(f"  Pair:        {plan['pair']}")
    print(f"  Direction:   {plan['direction']}")
    print(f"  Units:       {plan['units']}")
    print(f"  Trade id:    {result.get('broker_trade_id') or '(unknown)'}")
    if result.get("fill_price") is not None:
        print(f"  Fill price:  {result['fill_price']}")
    if recorded := result.get("recorded_trade"):
        print(f"  Mongo id:    {recorded.get('id')}")


async def _async_main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = await _place_trade(args)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        await close_db()

    _print_result(result, as_json=args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
