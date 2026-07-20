import { useEffect, useState, type RefObject } from "react";
import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  UTCTimestamp,
} from "lightweight-charts";
import type { CandleBar } from "../../api/client";
import { findCandleIndexNearUnix } from "./chartFocusWindow";
import { parseAppInstant } from "../formatTime";

export type OhlcSnapshot = {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
};

function candleBarToSnapshot(candle: CandleBar): OhlcSnapshot | null {
  const date = parseAppInstant(candle.time);
  if (!date) return null;
  return {
    time: Math.floor(date.getTime() / 1000) as UTCTimestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };
}

/** Prefer the focus/selection center; fall back to the last mounted candle. */
export function defaultOhlcSnapshot(
  candles: CandleBar[],
  focusCenterUnix?: number | null,
): OhlcSnapshot | null {
  if (candles.length === 0) return null;
  if (focusCenterUnix != null && Number.isFinite(focusCenterUnix)) {
    const idx = findCandleIndexNearUnix(candles, focusCenterUnix);
    const focused = candleBarToSnapshot(candles[idx]!);
    if (focused) return focused;
  }
  return candleBarToSnapshot(candles[candles.length - 1]!);
}

export function useCandleCrosshairOhlc(
  chartRef: RefObject<IChartApi | null>,
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>,
  candles: CandleBar[],
  enabled: boolean,
  /** When set (focused backtest/analysis), idle OHLC follows this unix second. */
  focusCenterUnix?: number | null,
): OhlcSnapshot | null {
  const [snapshot, setSnapshot] = useState<OhlcSnapshot | null>(() =>
    defaultOhlcSnapshot(candles, focusCenterUnix),
  );

  useEffect(() => {
    setSnapshot(defaultOhlcSnapshot(candles, focusCenterUnix));
  }, [candles, focusCenterUnix]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series || !enabled) return;

    const handler = (param: MouseEventParams) => {
      if (!param.time) {
        setSnapshot(defaultOhlcSnapshot(candles, focusCenterUnix));
        return;
      }

      const data = param.seriesData.get(series);
      if (!data || typeof data !== "object" || !("open" in data)) {
        setSnapshot(defaultOhlcSnapshot(candles, focusCenterUnix));
        return;
      }

      const bar = data as CandlestickData;
      setSnapshot({
        time: param.time as UTCTimestamp,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      });
    };

    chart.subscribeCrosshairMove(handler);
    return () => chart.unsubscribeCrosshairMove(handler);
  }, [chartRef, seriesRef, candles, enabled, focusCenterUnix]);

  return snapshot;
}
