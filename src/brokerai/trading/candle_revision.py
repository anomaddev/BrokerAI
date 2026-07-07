from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CandleRevisionTracker:
    """Tracks the latest candle time per (pair, timeframe) to skip unchanged analysis."""

    _revisions: dict[tuple[str, str], str] = field(default_factory=dict)

    def mark_updated(self, pair: str, timeframe: str, latest_time: str | None) -> None:
        if latest_time:
            self._revisions[(pair, timeframe)] = latest_time

    def has_changed(self, pair: str, timeframe: str, latest_time: str | None) -> bool:
        if not latest_time:
            return False
        previous = self._revisions.get((pair, timeframe))
        return previous != latest_time

    def covers_expected(
        self,
        pair: str,
        timeframe: str,
        expected: datetime | None,
    ) -> bool:
        """Return True when analysis revision is at or past *expected* closed bar."""
        if expected is None:
            return False
        stored = self._revisions.get((pair, timeframe))
        if not stored:
            return False
        from brokerai.trading.data.time_utils import parse_oanda_time

        try:
            parsed = parse_oanda_time(stored)
        except ValueError:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        expected_utc = expected if expected.tzinfo else expected.replace(tzinfo=timezone.utc)
        return parsed >= expected_utc.astimezone(timezone.utc)

    def snapshot(self) -> dict[str, str]:
        return {
            f"{pair}|{timeframe}": revision
            for (pair, timeframe), revision in sorted(self._revisions.items())
        }


# Tracks the latest candle time the pipeline last processed per (pair, timeframe).
GLOBAL_CANDLE_REVISIONS = CandleRevisionTracker()

# Alias for Secretary-coordinated pipeline revision tracking.
PipelineRevisionTracker = CandleRevisionTracker
