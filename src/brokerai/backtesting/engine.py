"""Bar-by-bar backtest engine that reuses live ``run_strategy_analysis``."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from brokerai.backtesting.actions import (
    build_entry_action,
    build_exit_action,
    build_signal_actions,
)
from brokerai.backtesting.metrics import compute_stats, downsample_equity_curve
from brokerai.backtesting.periods import format_oanda_bound, resolve_period_window
from brokerai.backtesting.simulator import BacktestSimulator
from brokerai.bots.data_manager.candle_requirements import strategy_params
from brokerai.db.repositories.asset_settings import AssetSettingsRepository
from brokerai.db.repositories.backtest_actions import BacktestActionsRepository
from brokerai.db.repositories.backtest_runs import (
    BacktestRunsRepository,
    normalize_account_margin,
)
from brokerai.strategies.candles import effective_min_candles
from brokerai.trading.data.candle_cache import CandleCache, OANDA_SOURCE
from brokerai.trading.data.time_utils import parse_oanda_time
from brokerai.trading.execution_gates import is_executor_eligible, passes_execution_gates
from brokerai.trading.indicator_cache import IndicatorCache, IndicatorCacheView
from brokerai.trading.pipeline import ensure_trading_registries, run_strategy_analysis
from brokerai.trading.session_hold import (
    should_force_close_market,
    should_force_close_session_boundary,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 1.5
HEARTBEAT_EVERY_N_BARS = 25
ACTION_FLUSH_SIZE = 50

# Exit reasons that reuse the strategy's entry signal. Closing on these must not
# also open the opposite side on the same bar (no flip entries).
_SIGNAL_EXIT_REASONS = frozenset({"reverse_crossover"})


def blocks_same_bar_entry(exit_reason: str | None) -> bool:
    """Return True when a same-bar exit should suppress a new entry.

    Reverse-crossover (and similar signal exits) close the open trade using the
    opposite crossover. That same bar's analysis would otherwise immediately
    open the flipped side — which is not desired.
    """
    if not exit_reason:
        return False
    return str(exit_reason).strip().lower() in _SIGNAL_EXIT_REASONS


def _slice_indicator_view(
    view: IndicatorCacheView,
    through_time: str,
) -> IndicatorCacheView:
    """Truncate indicator series so evaluators only see data through *through_time*."""
    sliced: dict[str, Any] = {}
    for key, value in view._values.items():
        if isinstance(value, list):
            sliced[key] = [
                point
                for point in value
                if isinstance(point, dict) and str(point.get("time") or "") <= through_time
            ]
        else:
            sliced[key] = value
    return IndicatorCacheView(pair=view.pair, timeframe=view.timeframe, _values=sliced)


def _candle_dt(candle: dict[str, Any]) -> datetime | None:
    raw = candle.get("time")
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.astimezone(timezone.utc) if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    parsed = parse_oanda_time(str(raw))
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sort_candles_oldest_first(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return candles in ascending open-time order (oldest → newest).

    The bar loop must walk history forward so indicators, gates, and fills match
    live bot behavior. Cache/API results are normally ascending, but overrides
    and some fetch paths can arrive reversed — sort defensively.
    """
    if len(candles) < 2:
        return list(candles)

    def sort_key(candle: dict[str, Any]) -> tuple[int, str]:
        dt = _candle_dt(candle)
        if dt is None:
            return (1, str(candle.get("time") or ""))
        return (0, dt.isoformat())

    ordered = sorted(candles, key=sort_key)
    first = _candle_dt(ordered[0])
    last = _candle_dt(ordered[-1])
    if first is not None and last is not None and first > last:
        # Should be unreachable after sort; keep a hard guard for bad timestamps.
        ordered.reverse()
    return ordered


async def _ensure_candles(
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    log: logging.Logger,
) -> list[dict[str, Any]]:
    cache = CandleCache()
    since = format_oanda_bound(start)
    until = format_oanda_bound(end)
    candles = await cache.read_candles(
        symbol,
        timeframe,
        source=OANDA_SOURCE,
        since=since,
        until=until,
    )
    if candles:
        first = str(candles[0].get("time") or "")
        last = str(candles[-1].get("time") or "")
        # Backfill if the cache does not cover the requested window.
        if first > since or last < until:
            log.info("Backfilling candle gap for %s %s [%s .. %s]", symbol, timeframe, since, until)
            result = await cache.backfill(symbol, timeframe, since, until)
            if result.error:
                log.warning("Candle backfill warning: %s", result.error)
            candles = await cache.read_candles(
                symbol,
                timeframe,
                source=OANDA_SOURCE,
                since=since,
                until=until,
            )
    else:
        log.info("No local candles — backfilling %s %s [%s .. %s]", symbol, timeframe, since, until)
        result = await cache.backfill(symbol, timeframe, since, until)
        if result.error:
            raise RuntimeError(f"Unable to load candles: {result.error}")
        candles = await cache.read_candles(
            symbol,
            timeframe,
            source=OANDA_SOURCE,
            since=since,
            until=until,
        )
    return _sort_candles_oldest_first(candles)


async def run_backtest_engine(
    run_doc: dict[str, Any],
    *,
    log: logging.Logger,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    candles_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a full backtest for *run_doc*. Returns finish payload fields."""
    ensure_trading_registries()
    runs_repo = BacktestRunsRepository()
    actions_repo = BacktestActionsRepository()
    run_id = str(run_doc["id"])
    strategy_id = str(run_doc.get("strategy_id") or "")
    pair = str(run_doc.get("instrument") or (run_doc.get("instruments") or [None])[0] or "")
    if not pair:
        raise RuntimeError("Backtest run has no instrument")

    params = dict(run_doc.get("params_snapshot") or {})
    timeframe = str(run_doc.get("timeframe") or params.get("timeframe") or "M15")
    strategy = {
        "id": strategy_id,
        "name": run_doc.get("strategy_name") or strategy_id,
        "timeframe": timeframe,
        "params": params,
        "asset_class": run_doc.get("asset_class") or "forex",
    }
    params = strategy_params(strategy)
    strategy["params"] = params
    account_margin = normalize_account_margin(run_doc.get("account_margin"))

    from brokerai.market_sessions import normalize_enabled_sessions

    try:
        asset_settings = await AssetSettingsRepository().get("forex")
        asset_enabled_sessions = (
            asset_settings.get("enabled_sessions") if isinstance(asset_settings, dict) else None
        )
    except Exception:
        # Unit tests / offline runs without Postgres fall back to all sessions on.
        asset_enabled_sessions = normalize_enabled_sessions(None)
        log.debug("Asset settings unavailable; defaulting enabled_sessions to all-on")

    period = str(run_doc.get("period") or "6m")
    if run_doc.get("period_start") and run_doc.get("period_end"):
        start = datetime.fromisoformat(str(run_doc["period_start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(run_doc["period_end"]).replace("Z", "+00:00"))
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    else:
        start, end = resolve_period_window(period)

    min_required = effective_min_candles(params)
    # Extra warmup bars before the period so indicators are valid at period start.
    warmup_pad_seconds = max(min_required, 50) * 15 * 60  # approx; refined by slicing
    warmup_start = datetime.fromtimestamp(start.timestamp() - warmup_pad_seconds, tz=timezone.utc)

    await runs_repo.update_progress(
        run_id,
        progress_pct=1,
        status_message=f"Loading candles for {pair} {timeframe}",
    )
    # Drain any buffered backtest logs before the long candle backfill so a
    # failed fetch still leaves useful INFO lines in the DB.
    for handler in log.handlers:
        flush = getattr(handler, "flush_async", None)
        if callable(flush):
            await flush()

    if candles_override is not None:
        all_candles = _sort_candles_oldest_first(list(candles_override))
    else:
        all_candles = await _ensure_candles(
            symbol=pair,
            timeframe=timeframe,
            start=warmup_start,
            end=end,
            log=log,
        )

    if len(all_candles) < min_required:
        raise RuntimeError(
            f"Insufficient candles for backtest: have {len(all_candles)}, need {min_required}"
        )

    first_dt = _candle_dt(all_candles[0])
    last_dt = _candle_dt(all_candles[-1])
    if first_dt is not None and last_dt is not None and first_dt > last_dt:
        raise RuntimeError(
            "Candle series is not in oldest-to-newest order after sorting; refusing to run"
        )

    # Index where the evaluation period begins.
    period_start_idx = 0
    for idx, candle in enumerate(all_candles):
        dt = _candle_dt(candle)
        if dt is not None and dt >= start.astimezone(timezone.utc):
            period_start_idx = idx
            break
    period_start_idx = max(period_start_idx, min_required - 1)

    log.info(
        "Loaded %d candles oldest→newest (%s .. %s); evaluating from index %d through %d",
        len(all_candles),
        all_candles[0].get("time"),
        all_candles[-1].get("time"),
        period_start_idx,
        len(all_candles) - 1,
    )

    cache = IndicatorCache()
    full_view = cache.warm(pair, timeframe, all_candles, [params])
    sim = BacktestSimulator(pair=pair, params=params, initial_equity=account_margin)
    action_buffer: list[dict[str, Any]] = []
    sequence = 0
    last_heartbeat = time.monotonic()
    total_bars = max(1, len(all_candles) - period_start_idx)

    # Seed live stats so the UI shows 0s instead of blanks while the bar loop runs.
    await runs_repo.update_progress(
        run_id,
        progress_pct=2,
        status_message="Simulating",
        stats=compute_stats([], equity_curve=[], initial_equity=account_margin),
    )

    async def flush_actions() -> None:
        nonlocal action_buffer
        if not action_buffer:
            return
        batch = action_buffer
        action_buffer = []
        await actions_repo.insert_many(run_id, batch)

    for i in range(period_start_idx, len(all_candles)):
        if cancel_check is not None and await cancel_check():
            await flush_actions()
            return {
                "status": "cancelled",
                "stats": compute_stats(
                    sim.closed_trades,
                    equity_curve=sim.equity_curve,
                    initial_equity=account_margin,
                ),
                "equity_curve": downsample_equity_curve(sim.equity_curve),
                "status_message": "Cancelled",
            }

        candle = all_candles[i]
        window = all_candles[: i + 1]
        through_time = str(candle.get("time") or "")
        indicators = _slice_indicator_view(full_view, through_time)

        # 1) Exits first (SL/TP then monitors) — mirrors live broker ordering.
        closed = sim.check_sl_tp(candle)
        if closed is None:
            closed = await sim.check_exit_monitors(window, indicators)

        # 1b) Session-island / major-market hold rules (after strategy exits).
        bar_when = _candle_dt(candle)
        if closed is None and sim.has_open_position() and bar_when is not None:
            hold_reason: str | None = None
            if should_force_close_session_boundary(
                params,
                when=bar_when,
                timeframe=timeframe,
                asset_enabled_sessions=asset_enabled_sessions,
            ):
                hold_reason = "session_boundary"
            elif should_force_close_market(
                params,
                when=bar_when,
                asset_enabled_sessions=asset_enabled_sessions,
            ):
                hold_reason = "market_close"
            if hold_reason is not None:
                closed = sim._close(
                    price=float(candle["close"]),
                    time=through_time,
                    reason=hold_reason,
                )

        closed_reason = (
            str(closed.get("exit_reason") or "exit") if closed is not None else None
        )
        if closed is not None:
            action_buffer.append(
                build_exit_action(
                    sequence=sequence,
                    candle=candle,
                    reason=closed_reason or "exit",
                    price=float(closed.get("exit_price") or 0),
                    pnl=float(closed.get("realized_pnl") or 0),
                )
            )
            sequence += 1
            log.info(action_buffer[-1]["message"])

        # 2) Live-parity analysis on the prefix window.
        analysis = run_strategy_analysis(
            strategy,
            pair,
            window,
            indicators,
            timeframe=timeframe,
            catchup=False,
        )

        open_pairs = {pair} if sim.has_open_position() else set()
        # Session hierarchy (global ∩ strategy) applies in backtests; pair/asset
        # global enablement is a live-trading concern and is not required here.
        gate_passed, gate_reasons, gate_details = passes_execution_gates(
            analysis,
            params,
            trade_counts={},
            when=bar_when,
            asset_enabled_sessions=asset_enabled_sessions,
            open_pairs=open_pairs,
            only_one_position_per_pair=True,
        )

        # Do not flip into a new trade on the same bar/signal that closed the last one.
        if blocks_same_bar_entry(closed_reason):
            if gate_passed and analysis.direction:
                gate_reasons = [*gate_reasons, "closed_on_signal"]
                gate_details = {
                    **gate_details,
                    "closed_on_signal": {"exit_reason": closed_reason},
                }
            gate_passed = False

        signal_actions = build_signal_actions(
            analysis,
            candle,
            sequence_start=sequence,
            gate_passed=gate_passed,
            gate_reasons=gate_reasons,
            gate_details=gate_details,
        )
        if signal_actions:
            action_buffer.extend(signal_actions)
            sequence = signal_actions[-1]["sequence"] + 1
            for act in signal_actions:
                log.info(act["message"])

        # Live-parity: approaching / none signals are watch-only and must not enter.
        # Without this gate, backtests opened trades with no preceding SIGNAL action,
        # so the next real crossover looked "out of order" after an orphan ENTRY.
        if (
            gate_passed
            and is_executor_eligible(analysis)
            and not sim.has_open_position()
        ):
            entry_price = float(candle["close"])
            pos = sim.open_position(
                strategy_id=strategy_id,
                direction=str(analysis.direction),
                entry_price=entry_price,
                entry_time=through_time,
                candles=window,
            )
            if pos is not None:
                action_buffer.append(
                    build_entry_action(
                        sequence=sequence,
                        candle=candle,
                        direction=pos.direction,
                        price=pos.entry_price,
                        units=pos.units,
                    )
                )
                sequence += 1
                log.info(action_buffer[-1]["message"])

        sim.mark_equity(candle)

        if len(action_buffer) >= ACTION_FLUSH_SIZE:
            await flush_actions()

        done = i - period_start_idx + 1
        now = time.monotonic()
        trade_closed = closed is not None
        if (
            trade_closed
            or done % HEARTBEAT_EVERY_N_BARS == 0
            or (now - last_heartbeat) >= HEARTBEAT_INTERVAL_S
        ):
            pct = min(99.0, (done / total_bars) * 100.0)
            live_stats = compute_stats(
                sim.closed_trades,
                equity_curve=sim.equity_curve,
                initial_equity=account_margin,
            )
            await runs_repo.update_progress(
                run_id,
                progress_pct=pct,
                current_bar=_candle_dt(candle),
                status_message=f"Processing {through_time}",
                stats=live_stats,
            )
            last_heartbeat = now

    # Force-close any open position at the last bar close.
    if sim.has_open_position() and all_candles:
        last = all_candles[-1]
        closed = sim._close(
            price=float(last["close"]),
            time=str(last.get("time") or ""),
            reason="end_of_backtest",
        )
        if closed is not None:
            action_buffer.append(
                build_exit_action(
                    sequence=sequence,
                    candle=last,
                    reason="end_of_backtest",
                    price=float(closed.get("exit_price") or 0),
                    pnl=float(closed.get("realized_pnl") or 0),
                )
            )
            sequence += 1

    await flush_actions()
    stats = compute_stats(
        sim.closed_trades,
        equity_curve=sim.equity_curve,
        initial_equity=account_margin,
    )
    curve = downsample_equity_curve(sim.equity_curve)
    await runs_repo.update_progress(
        run_id,
        progress_pct=100,
        status_message="Completed",
        current_bar=_candle_dt(all_candles[-1]) if all_candles else None,
    )
    log.info(
        "Backtest complete: trades=%s win_rate=%s pnl=%s max_dd=%s",
        stats.get("total_trades"),
        stats.get("win_rate"),
        stats.get("realized_pnl"),
        stats.get("max_drawdown"),
    )
    return {
        "status": "completed",
        "stats": stats,
        "equity_curve": curve,
        "status_message": "Completed",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
    }
