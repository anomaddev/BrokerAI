#!/usr/bin/env python3
"""Read-only diagnostic: compare each broker lot's recorded entry_price against the
candle(s) it should relate to (the anchored ``entry_candle_open`` bar AND the true
"signal" bar = the last CLOSED bar before the fill).

This does NOT modify any data. It prints a summary and (with ``--verbose``) one NDJSON
record per lot so we can quantify, across the whole dataset, *why* fills land outside
the candle range (mid-vs-bid/ask spread vs. fill-bar/signal-bar mismatch).

Usage:
    ./venv/bin/python -m scripts.diagnose_entry_vs_candle
    ./venv/bin/python -m scripts.diagnose_entry_vs_candle --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

_TIMEFRAME_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D": 1440,
}

_VERBOSE = False
_MARKET_DATA_SOURCE = "oanda"


def _log(payload: dict) -> None:
    """Emit one NDJSON record per lot to stdout when ``--verbose`` is set."""
    if not _VERBOSE:
        return
    payload = {**payload, "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)}
    print(json.dumps(payload, default=str))


def _pip_size(symbol: str) -> float:
    quote = symbol.replace("/", "_").split("_")[-1].upper()
    return 0.01 if quote == "JPY" else 0.0001


def _parse_instant(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        txt = value.replace("Z", "+00:00")
        # trim excessive fractional-second precision (OANDA nanoseconds)
        if "." in txt and "+" in txt:
            head, tail = txt.split(".", 1)
            frac, tz = tail.split("+", 1)
            txt = f"{head}.{frac[:6]}+{tz}"
        try:
            return datetime.fromisoformat(txt)
        except ValueError:
            return None
    return None


async def _fetch_candle(
    session,
    *,
    symbol: str,
    timeframe: str,
    time_value: str | None = None,
    ts: datetime | None = None,
) -> dict | None:
    from brokerai.db.pg.models import MarketCandle
    from sqlalchemy import select

    stmt = select(MarketCandle).where(
        MarketCandle.symbol == symbol,
        MarketCandle.timeframe == timeframe,
        MarketCandle.source == _MARKET_DATA_SOURCE,
    )
    if time_value is not None:
        stmt = stmt.where(MarketCandle.time == time_value)
    if ts is not None:
        stmt = stmt.where(MarketCandle.ts == ts)
    row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
    if row is None:
        return None
    return {
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "time": row.time,
    }


async def diagnose() -> dict[str, int]:
    from brokerai.db.client import init_pg
    from brokerai.db.pg.client import session_scope
    from brokerai.db.pg.models import BrokerLotRow
    from sqlalchemy import select

    await init_pg()
    async with session_scope() as session:
        rows = (await session.execute(select(BrokerLotRow))).scalars().all()
        lots = [
            dict(row.doc)
            for row in rows
            if float(row.doc.get("entry_price") or 0) > 0
        ]

    stats = {
        "scanned": len(lots),
        "no_anchor": 0,
        "no_candle": 0,
        "inside_anchor": 0,
        "outside_anchor": 0,
        "inside_signalbar": 0,
        "outside_signalbar": 0,
        "long_above_high": 0,
        "short_below_low": 0,
    }

    for lot in lots:
        symbol = str(lot.get("symbol") or "").strip()
        db_symbol = symbol.replace("_", "/")
        entry = float(lot.get("entry_price") or 0)
        direction = str(lot.get("direction") or "").lower()
        timeframe = str(lot.get("timeframe") or "M15")
        anchor = lot.get("entry_candle_open")
        open_time = _parse_instant(lot.get("open_time") or lot.get("opened_at"))

        if not anchor or not symbol:
            stats["no_anchor"] += 1
            _log({"hypothesisId": "C", "location": "diagnose:no_anchor",
                  "message": "lot missing entry_candle_open",
                  "data": {"lot": lot.get("broker_lot_id"), "symbol": symbol}})
            continue

        async with session_scope() as session:
            anchored = await _fetch_candle(
                session,
                symbol=db_symbol,
                timeframe=timeframe,
                time_value=str(anchor),
            )
            minutes = _TIMEFRAME_MINUTES.get(timeframe, 15)
            anchor_dt = _parse_instant(anchor)
            signal_bar = None
            if anchor_dt is not None:
                prev_dt = anchor_dt - timedelta(minutes=minutes)
                signal_bar = await _fetch_candle(
                    session,
                    symbol=db_symbol,
                    timeframe=timeframe,
                    ts=prev_dt,
                )

        if not anchored:
            stats["no_candle"] += 1
            _log({"hypothesisId": "D", "location": "diagnose:no_candle",
                  "message": "no stored candle for anchor bar",
                  "data": {"lot": lot.get("broker_lot_id"), "symbol": db_symbol,
                           "timeframe": timeframe, "anchor": anchor}})
            continue

        pip = _pip_size(symbol)
        a_low, a_high = float(anchored["low"]), float(anchored["high"])
        inside_anchor = a_low <= entry <= a_high
        above = entry - a_high
        below = a_low - entry
        gap_pips = (above if above > 0 else below if below > 0 else 0.0) / pip

        if inside_anchor:
            stats["inside_anchor"] += 1
        else:
            stats["outside_anchor"] += 1
            if above > 0:
                stats["long_above_high"] += 1
            elif below > 0:
                stats["short_below_low"] += 1

        sig_inside = None
        if signal_bar:
            s_low, s_high = float(signal_bar["low"]), float(signal_bar["high"])
            sig_inside = s_low <= entry <= s_high
            if sig_inside:
                stats["inside_signalbar"] += 1
            else:
                stats["outside_signalbar"] += 1

        _log({
            "hypothesisId": "A/B/C/E",
            "location": "diagnose:compare",
            "message": "entry vs anchored candle",
            "data": {
                "lot": lot.get("broker_lot_id"),
                "strategy_id": lot.get("strategy_id"),
                "symbol": symbol,
                "direction": direction,
                "timeframe": timeframe,
                "entry_price": entry,
                "open_time": str(open_time),
                "anchor_bar": anchor,
                "anchor_ohlc": {k: anchored.get(k) for k in ("open", "high", "low", "close")},
                "inside_anchor": inside_anchor,
                "gap_pips_outside_anchor": round(gap_pips, 2),
                "offset_direction": ("above_high" if above > 0 else "below_low" if below > 0 else "inside"),
                "signal_bar": (signal_bar or {}).get("time"),
                "signal_ohlc": ({k: signal_bar.get(k) for k in ("open", "high", "low", "close")} if signal_bar else None),
                "inside_signal_bar": sig_inside,
            },
        })

    _log({"hypothesisId": "SUMMARY", "location": "diagnose:summary",
          "message": "diagnostic summary", "data": stats})
    return stats


def main() -> int:
    global _VERBOSE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit one NDJSON record per lot (entry vs anchored/signal candle) to stdout",
    )
    args = parser.parse_args()
    _VERBOSE = args.verbose

    async def run() -> int:
        from brokerai.db.client import close_db
        try:
            stats = await diagnose()
            print(json.dumps(stats, indent=2))
            return 0
        finally:
            await close_db()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
