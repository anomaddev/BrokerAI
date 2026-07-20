import type { CandleBar } from "../../api/client";
import type { ExploreOverlayData, StrategyIndicatorLine } from "./computeExploreOverlays";
import { MAX_VISIBLE_CANDLES } from "./brokerChartOptions";
import { CANDLE_LIMIT_MAX } from "../exploreChartPresets";
import { timeframeToMs, type Timeframe } from "../candleSchedule";
import { parseAppInstant } from "../formatTime";

export type ChartFocusWindow = {
  since: string;
  until: string;
  displaySince: string;
  displayUntil: string;
  visibleFromTime: number;
  visibleToTime: number;
};

/** Max bars mounted on a focused chart series (backtests can load far more). */
export const MAX_FOCUS_SERIES_BARS = CANDLE_LIMIT_MAX;

/** Extra history before the render window for indicator warmup. */
export const FOCUS_INDICATOR_WARMUP_BARS = 300;

/** When the visible logical range is within this many bars of an edge, shift the window. */
export const FOCUS_SERIES_EDGE_BARS = 50;

/**
 * Bars shown when focusing a backtest action / step-through anchor.
 * Matches the explore chart's default viewport so context stays readable.
 */
export const FOCUS_VISIBLE_BARS = MAX_VISIBLE_CANDLES;

function parseInstant(value: string | null | undefined): number | null {
  const date = parseAppInstant(value);
  return date ? date.getTime() : null;
}

/** Keep bars whose open time falls within ``since`` … ``until`` (both bar open times). */
export function sliceCandlesToFocusWindow(
  bars: CandleBar[],
  since: string,
  until: string,
  timeframe?: Timeframe,
): CandleBar[] {
  const sinceMs = parseInstant(since);
  const untilMs = parseInstant(until);
  if (sinceMs == null || untilMs == null) return bars;

  return bars.filter((bar) => {
    const barMsValue = parseInstant(bar.time);
    return barMsValue != null && barMsValue >= sinceMs && barMsValue <= untilMs;
  });
}

/** Nearest bar index at or before ``centerUnix`` (seconds). */
export function findCandleIndexNearUnix(
  bars: Array<{ time: string }>,
  centerUnix: number,
): number {
  if (bars.length === 0) return 0;
  let lo = 0;
  let hi = bars.length - 1;
  let best = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const ms = parseInstant(bars[mid]?.time);
    if (ms == null) {
      lo = mid + 1;
      continue;
    }
    const unix = Math.floor(ms / 1000);
    if (unix <= centerUnix) {
      best = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return best;
}

/**
 * Cap a long series to ``maxBars`` centered on ``centerUnix``.
 * Used so backtest charts can keep a full period in memory without mounting every bar.
 */
export function sliceCandlesAroundUnix(
  bars: CandleBar[],
  centerUnix: number,
  maxBars: number = MAX_FOCUS_SERIES_BARS,
): CandleBar[] {
  if (bars.length <= maxBars) return bars;
  const idx = findCandleIndexNearUnix(bars, centerUnix);
  const half = Math.floor(maxBars / 2);
  let start = Math.max(0, idx - half);
  let end = Math.min(bars.length, start + maxBars);
  start = Math.max(0, end - maxBars);
  return bars.slice(start, end);
}

/** Extend ``windowBars`` backward into ``allBars`` for indicator seed history. */
export function extendCandlesForWarmup(
  allBars: CandleBar[],
  windowBars: CandleBar[],
  warmupBars: number = FOCUS_INDICATOR_WARMUP_BARS,
): CandleBar[] {
  if (windowBars.length === 0 || allBars.length === 0) return windowBars;
  const firstTime = windowBars[0]?.time;
  if (!firstTime) return windowBars;
  const startIdx = allBars.findIndex((bar) => bar.time === firstTime);
  if (startIdx <= 0) return windowBars;
  const warmStart = Math.max(0, startIdx - warmupBars);
  if (warmStart === startIdx) return windowBars;
  return allBars.slice(warmStart, startIdx).concat(windowBars);
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

/**
 * Build a focus window centered on ``anchorIso``.
 *
 * ``displaySince`` / ``displayUntil`` bound the pannable series (usually the full
 * backtest period). The initial zoom uses a fixed number of bars for the
 * strategy timeframe so M15 and D1 both show a readable context — not 1–2 candles.
 */
export function buildCenteredBarFocusWindow(options: {
  anchorIso: string;
  timeframe: Timeframe;
  displaySinceMs: number;
  displayUntilMs: number;
  visibleBars?: number;
}): ChartFocusWindow | null {
  const centerMs = parseInstant(options.anchorIso);
  if (centerMs == null) return null;
  if (!Number.isFinite(options.displaySinceMs) || !Number.isFinite(options.displayUntilMs)) {
    return null;
  }

  const visibleBars = Math.max(10, options.visibleBars ?? FOCUS_VISIBLE_BARS);
  const halfBars = Math.floor(visibleBars / 2);
  const barMs = timeframeToMs(options.timeframe);
  const padMs = halfBars * barMs;

  return {
    since: new Date(options.displaySinceMs).toISOString(),
    until: new Date(options.displayUntilMs).toISOString(),
    displaySince: new Date(options.displaySinceMs).toISOString(),
    displayUntil: new Date(options.displayUntilMs).toISOString(),
    visibleFromTime: Math.floor((centerMs - padMs) / 1000),
    visibleToTime: Math.floor((centerMs + padMs) / 1000),
  };
}

/**
 * Logical range centered on the bar nearest the focus window midpoint.
 *
 * Prefer this over ``setVisibleRange`` so the viewport always shows a fixed
 * number of candles of context (wall-clock ranges collapse across gaps / TF).
 */
export function chartFocusVisibleLogicalRange(
  bars: Array<{ time: string }>,
  focusWindow: Pick<ChartFocusWindow, "visibleFromTime" | "visibleToTime">,
  visibleBars: number = FOCUS_VISIBLE_BARS,
): { from: number; to: number } | null {
  if (bars.length === 0) return null;

  const centerUnix = Math.floor(
    (focusWindow.visibleFromTime + focusWindow.visibleToTime) / 2,
  );
  const idx = findCandleIndexNearUnix(bars, centerUnix);
  const span = Math.max(10, visibleBars);
  const half = Math.floor(span / 2);

  return {
    from: idx - half,
    to: idx + half,
  };
}
