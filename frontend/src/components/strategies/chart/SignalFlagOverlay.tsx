import { useEffect, useState, type RefObject } from "react";
import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import type { Candle, CrossoverSignal } from "../../../pages/strategies/presets/emaCrossover/mockData";

export type SignalFlagLayout = {
  id: string;
  x: number;
  y: number;
  height: number;
  type: CrossoverSignal["type"];
  label: string;
};

type SignalFlagOverlayProps = {
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  paneRef: RefObject<HTMLDivElement | null>;
  candles: Candle[];
  signals: CrossoverSignal[];
  visible: boolean;
  locked: boolean;
  showDetailed: boolean;
  layoutRevision: number;
};

function toChartTime(unixSeconds: number): UTCTimestamp {
  return unixSeconds as UTCTimestamp;
}

function buildSignalLabel(
  signal: CrossoverSignal,
  options: { showDetailed: boolean; locked: boolean },
): string {
  const isBull = signal.type === "bullish";
  const showConfidence = options.locked || options.showDetailed;
  if (showConfidence) {
    return `${isBull ? "BUY" : "SELL"} ${signal.confidence}%`;
  }
  return isBull ? "BUY" : "SELL";
}

export function computeSignalFlagLayouts(
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  candles: Candle[],
  signals: CrossoverSignal[],
  options: { visible: boolean; locked: boolean; showDetailed: boolean },
): SignalFlagLayout[] {
  if (!options.visible || signals.length === 0) return [];

  const candleByTime = new Map(candles.map((candle) => [candle.time, candle]));
  const timeScale = chart.timeScale();
  const poleHeight = options.locked ? 100 : 80;
  const layouts: SignalFlagLayout[] = [];

  for (const signal of signals) {
    const candle = candleByTime.get(signal.time);
    if (!candle) continue;

    const x = timeScale.timeToCoordinate(toChartTime(signal.time));
    if (x === null) continue;

    const isBull = signal.type === "bullish";
    const anchorPrice = isBull ? candle.low : candle.high;
    const y = series.priceToCoordinate(anchorPrice);
    if (y === null) continue;

    layouts.push({
      id: `${signal.time}-${signal.type}`,
      x,
      y,
      height: poleHeight,
      type: signal.type,
      label: buildSignalLabel(signal, options),
    });
  }

  return layouts;
}

export default function SignalFlagOverlay({
  chartRef,
  seriesRef,
  paneRef,
  candles,
  signals,
  visible,
  locked,
  showDetailed,
  layoutRevision,
}: SignalFlagOverlayProps) {
  const [layouts, setLayouts] = useState<SignalFlagLayout[]>([]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const pane = paneRef.current;
    if (!chart || !series || !pane) {
      setLayouts([]);
      return;
    }

    const refresh = () => {
      setLayouts(
        computeSignalFlagLayouts(chart, series, candles, signals, {
          visible,
          locked,
          showDetailed,
        }),
      );
    };

    refresh();

    const timeScale = chart.timeScale();
    timeScale.subscribeVisibleLogicalRangeChange(refresh);
    const resizeObserver = new ResizeObserver(refresh);
    resizeObserver.observe(pane);

    return () => {
      timeScale.unsubscribeVisibleLogicalRangeChange(refresh);
      resizeObserver.disconnect();
    };
  }, [chartRef, seriesRef, paneRef, candles, signals, visible, locked, showDetailed, layoutRevision]);

  if (!visible || layouts.length === 0) return null;

  return (
    <div className="strategy-signal-flag-overlay" aria-hidden="true">
      {layouts.map((flag) => {
        const isBull = flag.type === "bullish";
        const top = isBull ? flag.y : flag.y - flag.height;

        return (
          <div
            key={flag.id}
            className={`strategy-signal-flag strategy-signal-flag--${isBull ? "buy" : "sell"}`}
            style={{
              left: `${flag.x}px`,
              top: `${top}px`,
              height: `${flag.height}px`,
            }}
          >
            {!isBull && (
              <span className="strategy-signal-flag-label">{flag.label}</span>
            )}
            <span className="strategy-signal-flag-pole" />
            <span className="strategy-signal-flag-anchor" />
            {isBull && (
              <span className="strategy-signal-flag-label">{flag.label}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
