from __future__ import annotations

from datetime import date


async def load_weekly_bot_results(week_start: date, week_end: date) -> str | None:
    """Load bot trades and results for a weekly debrief.

    Placeholder until live execution and trade persistence exist.
    """
    _ = week_start, week_end
    return None
