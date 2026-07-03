import type { CandleBar } from "../../api/client";
import { parseAppInstant } from "../formatTime";
import type { PriceSource } from "../strategyParams";

export type ChartCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export function candleBarToChartCandle(bar: CandleBar): ChartCandle | null {
  const date = parseAppInstant(bar.time);
  if (!date) return null;
  return {
    time: Math.floor(date.getTime() / 1000),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
}

export function candleBarsToChartCandles(bars: CandleBar[]): ChartCandle[] {
  const byTime = new Map<number, ChartCandle>();
  for (const bar of bars) {
    const candle = candleBarToChartCandle(bar);
    if (candle != null) {
      byTime.set(candle.time, candle);
    }
  }
  return [...byTime.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, candle]) => candle);
}

/** Drop duplicate bars that map to the same lightweight-charts unix time (last wins). */
export function dedupeCandleBars(bars: CandleBar[]): CandleBar[] {
  const byTime = new Map<number, CandleBar>();
  for (const bar of bars) {
    const date = parseAppInstant(bar.time);
    if (!date) continue;
    byTime.set(Math.floor(date.getTime() / 1000), bar);
  }
  return [...byTime.entries()]
    .sort(([left], [right]) => left - right)
    .map(([, bar]) => bar);
}

export function priceFromSource(candle: ChartCandle, source: PriceSource = "close"): number {
  switch (source) {
    case "open":
      return candle.open;
    case "high":
      return candle.high;
    case "low":
      return candle.low;
    case "hl2":
      return (candle.high + candle.low) / 2;
    case "hlc3":
      return (candle.high + candle.low + candle.close) / 3;
    case "ohlc4":
      return (candle.open + candle.high + candle.low + candle.close) / 4;
    default:
      return candle.close;
  }
}
