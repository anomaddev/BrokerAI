import { timeframeToMs } from "../candleSchedule";
import { parseAppInstant } from "../formatTime";
import type { Timeframe } from "../strategyParams";

export type MarketBoundaryKind = "close" | "open";

export type MarketBoundary = {
  time: number;
  kind: MarketBoundaryKind;
  label: string;
};

export type CandleTimeLike = {
  time: string;
};

/** Gaps longer than ~36 hours are treated as the weekly forex close. */
const WEEKLY_GAP_MS = 36 * 3_600_000;

/** Place vertical markers on the last bar before and first bar after each timeline gap. */
export function findMarketBoundariesForCandles(
  candles: CandleTimeLike[],
  timeframe: Timeframe,
): MarketBoundary[] {
  if (candles.length < 2) return [];

  const barMs = timeframeToMs(timeframe);
  const gapThreshold = barMs * 1.5;
  const boundaries: MarketBoundary[] = [];

  for (let index = 1; index < candles.length; index += 1) {
    const previous = parseAppInstant(candles[index - 1].time);
    const current = parseAppInstant(candles[index].time);
    if (!previous || !current) continue;

    const gapMs = current.getTime() - previous.getTime();
    if (gapMs <= gapThreshold) continue;

    const weekly = gapMs >= WEEKLY_GAP_MS;
    const prevSec = Math.floor(previous.getTime() / 1000);
    const currSec = Math.floor(current.getTime() / 1000);

    boundaries.push({
      time: prevSec,
      kind: "close",
      label: weekly ? "Close" : "Close",
    });
    boundaries.push({
      time: currSec,
      kind: "open",
      label: weekly ? "Open" : "Open",
    });
  }

  return boundaries;
}
