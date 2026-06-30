import { useEffect, useState, type RefObject } from "react";
import type {
  CandlestickData,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  UTCTimestamp,
} from "lightweight-charts";
import type { CandleBar } from "../../api/client";
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

function lastSnapshot(candles: CandleBar[]): OhlcSnapshot | null {
  const last = candles[candles.length - 1];
  return last ? candleBarToSnapshot(last) : null;
}

export function useCandleCrosshairOhlc(
  chartRef: RefObject<IChartApi | null>,
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>,
  candles: CandleBar[],
  enabled: boolean,
): OhlcSnapshot | null {
  const [snapshot, setSnapshot] = useState<OhlcSnapshot | null>(() => lastSnapshot(candles));

  useEffect(() => {
    setSnapshot(lastSnapshot(candles));
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series || !enabled) return;

    const handler = (param: MouseEventParams) => {
      if (!param.time) {
        setSnapshot(lastSnapshot(candles));
        return;
      }

      const data = param.seriesData.get(series);
      if (!data || typeof data !== "object" || !("open" in data)) {
        setSnapshot(lastSnapshot(candles));
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
  }, [chartRef, seriesRef, candles, enabled]);

  return snapshot;
}
