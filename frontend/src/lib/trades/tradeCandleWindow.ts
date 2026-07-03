import type { CandleBar, Trade } from "../../api/client";
import type { ExploreOverlayData, StrategyIndicatorLine } from "../chart/computeExploreOverlays";
import { isKnownTimeframe, timeframeToMs, type Timeframe } from "../candleSchedule";
import { tradeIsOpen } from "../trades";

/** Wall-clock padding before open and after close on trade detail charts. */
export const TRADE_CHART_PADDING_MS = 60 * 60 * 1000;

export type TradeCandleWindow = {
  since: string;
  until: string;
  displaySince: string;
  displayUntil: string;
  /** Entry instant as unix seconds (exact ``opened_at``). */
  entryTime: number;
  /** Exit instant as unix seconds, or null when trade is open. */
  exitTime: number | null;
  /** Initial chart zoom start (unix seconds). */
  visibleFromTime: number;
  /** Initial chart zoom end (unix seconds). */
  visibleToTime: number;
};

function parseInstant(value: string | null | undefined): number | null {
  if (!value?.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Resolve strategy timeframe with a safe default. */
export function tradeChartTimeframe(raw: string | null | undefined): Timeframe {
  if (raw && isKnownTimeframe(raw)) return raw;
  return "M15";
}

/**
 * Build the trade chart lifecycle window from open/close instants.
 *
 * ``displaySince`` / ``displayUntil`` bound the visible chart. ``since`` / ``until``
 * include extra warmup history returned by the API for indicator computation.
 */
export function buildTradeCandleWindow(
  trade: Pick<Trade, "opened_at" | "closed_at" | "status" | "state">,
  bounds?: {
    since?: string | null;
    until?: string | null;
    displaySince?: string | null;
    displayUntil?: string | null;
  } | null,
): TradeCandleWindow | null {
  const openedMs = parseInstant(trade.opened_at);
  if (openedMs == null) return null;

  const isOpen = tradeIsOpen(trade);
  const closedMs = isOpen ? Date.now() : parseInstant(trade.closed_at);
  if (closedMs == null) return null;

  const displaySinceMs =
    parseInstant(bounds?.displaySince) ?? openedMs - TRADE_CHART_PADDING_MS;
  const displayUntilMs =
    parseInstant(bounds?.displayUntil) ??
    (isOpen ? Date.now() : closedMs + TRADE_CHART_PADDING_MS);
  const sinceMs = parseInstant(bounds?.since) ?? displaySinceMs;
  const untilMs = parseInstant(bounds?.until) ?? displayUntilMs;

  return {
    since: new Date(sinceMs).toISOString(),
    until: new Date(untilMs).toISOString(),
    displaySince: new Date(displaySinceMs).toISOString(),
    displayUntil: new Date(displayUntilMs).toISOString(),
    entryTime: Math.floor(openedMs / 1000),
    exitTime: isOpen ? null : Math.floor(closedMs / 1000),
    visibleFromTime: Math.floor(displaySinceMs / 1000),
    visibleToTime: Math.floor(displayUntilMs / 1000),
  };
}

export function tradeChartVisibleTimeRange(
  window: Pick<TradeCandleWindow, "visibleFromTime" | "visibleToTime">,
): { from: number; to: number } {
  return {
    from: window.visibleFromTime,
    to: Math.max(window.visibleFromTime, window.visibleToTime),
  };
}

/** Keep bars whose open time falls within the display window (plus one bar past ``until``). */
export function sliceCandlesToWindow(
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
export function clipExploreOverlayData(
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
