from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from brokerai.db.repositories.shadow_trading import TradeOutcomeRecordsRepository

ET = ZoneInfo("America/New_York")


def _week_bounds_et(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    """Inclusive ET day bounds for weekly outcome summarization.

    ``week_end`` is treated as an inclusive calendar day (typically Friday).
    When ``week_end`` is before ``week_start``, the end is clamped to start
    (empty window) so callers cannot invert the range by accident.
    """
    start = datetime.combine(week_start, time.min, tzinfo=ET)
    end_day = week_end if week_end >= week_start else week_start
    # Inclusive through end-of-day ET: use just before next midnight.
    end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=ET) - timedelta(
        microseconds=1
    )
    return start, end


async def load_weekly_bot_results(week_start: date, week_end: date) -> str | None:
    """Load bot trades and results for a weekly debrief.

    Summarizes ``trade_outcome_records`` (shadow + live) whose ``exit_ts`` falls
    in the ET week window. Returns a short plain-text block, or None when there
    were no closed trades in range.
    """
    start, end = _week_bounds_et(week_start, week_end)
    summary = await TradeOutcomeRecordsRepository().summarize_week(
        week_start=start, week_end=end
    )
    total = int(summary.get("total_trades") or 0)
    if total <= 0:
        return None

    wins = int(summary.get("wins") or 0)
    losses = int(summary.get("losses") or 0)
    pnl = float(summary.get("realized_pnl") or 0.0)
    shadow = int(summary.get("shadow") or 0)
    live = int(summary.get("live") or 0)
    win_rate = (wins / total * 100.0) if total else 0.0

    lines = [
        f"Bot results ({week_start.isoformat()} → {week_end.isoformat()} ET):",
        f"- Closed trades: {total} (wins={wins}, losses={losses}, win_rate={win_rate:.0f}%)",
        f"- Realized PnL: {pnl:.2f}",
        f"- Modes: shadow={shadow}, live={live}",
    ]
    return "\n".join(lines)
