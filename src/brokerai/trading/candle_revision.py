from __future__ import annotations

from dataclasses import dataclass, field


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

    def snapshot(self) -> dict[str, str]:
        return {
            f"{pair}|{timeframe}": revision
            for (pair, timeframe), revision in sorted(self._revisions.items())
        }


# Tracks the latest candle time the data analyzer last processed per (pair, timeframe).
GLOBAL_CANDLE_REVISIONS = CandleRevisionTracker()
