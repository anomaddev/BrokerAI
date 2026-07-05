import type { CandleBar } from "../../api/client";
import type { ExploreOverlayData, StrategyIndicatorLine } from "./computeExploreOverlays";
import { isKnownTimeframe, timeframeToMs, type Timeframe } from "../candleSchedule";

export type ChartFocusWindow = {
  since: string;
  until: string;
  displaySince: string;
  displayUntil: string;
  visibleFromTime: number;
  visibleToTime: number;
};

function parseInstant(value: string | null | undefined): number | null {
  if (!value?.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Keep bars whose open time falls within the display window (plus one bar past ``until``). */
export function sliceCandlesToFocusWindow(
  bars: CandleBar[],
  since: string,
  until: string,
  timeframe?: Timeframe,
): CandleBar[] {
  const sinceMs = parseInstant(since);
  const untilMs = parseInstant(until);
  if (sinceMs == null || untilMs == null) return bars;

  const barMs = timeframe && isKnownTimeframe(timeframe) ? timeframeToMs(timeframe) : 0;
  const inclusiveUntilMs = untilMs + barMs;

  return bars.filter((bar) => {
    const barMsValue = parseInstant(bar.time);
    return barMsValue != null && barMsValue >= sinceMs && barMsValue <= inclusiveUntilMs;
  });
}

function clipIndicatorLine(
  line: StrategyIndicatorLine,
  fromUnix: number,
  toUnix: number,
): StrategyIndicatorLine {
  return {
    ...line,
    points: line.points.filter((point) => point.time >= fromUnix && point.time <= toUnix),
  };
}

/** Restrict indicator overlays to the visible chart window after warmup computation. */
export function clipExploreOverlayDataToFocus(
  data: ExploreOverlayData,
  fromUnix: number,
  toUnix: number,
): ExploreOverlayData {
  const clip = (line: StrategyIndicatorLine) => clipIndicatorLine(line, fromUnix, toUnix);

  return {
    ...data,
    candles: data.candles.filter((candle) => candle.time >= fromUnix && candle.time <= toUnix),
    priceLines: data.priceLines.map(clip).filter((line) => line.points.length > 0),
    rsiLines: data.rsiLines.map(clip).filter((line) => line.points.length > 0),
    adxLines: data.adxLines.map(clip).filter((line) => line.points.length > 0),
    signals: data.signals.filter((signal) => signal.time >= fromUnix && signal.time <= toUnix),
  };
}

export function chartFocusVisibleTimeRange(
  window: Pick<ChartFocusWindow, "visibleFromTime" | "visibleToTime">,
): { from: number; to: number } {
  return {
    from: window.visibleFromTime,
    to: Math.max(window.visibleFromTime, window.visibleToTime),
  };
}
