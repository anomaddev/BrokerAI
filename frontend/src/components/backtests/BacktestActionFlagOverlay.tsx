import { Fragment, useEffect, useState, type RefObject } from "react";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { ChartCandle } from "../../lib/chart/candleBars";
import type { BacktestChartMarker } from "../../lib/backtests/backtestChartMarkers";
import {
  resolveTradeEventPriceCoordinate,
  resolveTradeEventTimeCoordinate,
} from "../../lib/trades/tradeEventCoordinates";

type Layout = {
  id: string;
  x: number;
  y: number;
  role: BacktestChartMarker["role"];
  direction: "long" | "short";
  label: string;
  active: boolean;
};

type BacktestActionFlagOverlayProps = {
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  paneRef: RefObject<HTMLDivElement | null>;
  candles: ChartCandle[];
  markers: BacktestChartMarker[];
  /** Sequences to highlight (single action or full trade group). */
  selectedSequences?: number[] | null;
  /** @deprecated Use ``selectedSequences``. */
  selectedSequence?: number | null;
  chartReady: boolean;
  layoutRevision: number;
};

const ANCHOR_SIZE = 8;

function candleAnchorPrice(
  candle: ChartCandle | undefined,
  direction: "long" | "short",
  role: BacktestChartMarker["role"],
): number | null {
  if (!candle) return null;
  if (role === "entry" || role === "signal") return direction === "long" ? candle.low : candle.high;
  if (role === "exit") return direction === "long" ? candle.high : candle.low;
  return direction === "long" ? candle.low : candle.high;
}

function roleClass(role: BacktestChartMarker["role"], direction: "long" | "short"): string {
  if (role === "skipped") return "skipped";
  if (role === "signal") return direction === "long" ? "signal-long" : "signal-short";
  if (role === "entry") return direction === "long" ? "entry-long" : "entry-short";
  return direction === "long" ? "exit-long" : "exit-short";
}

function resolveSelectedSet(
  selectedSequences: number[] | null | undefined,
  selectedSequence: number | null | undefined,
): Set<number> {
  if (selectedSequences != null && selectedSequences.length > 0) {
    return new Set(selectedSequences);
  }
  if (selectedSequence != null) return new Set([selectedSequence]);
  return new Set();
}

export function computeBacktestActionFlagLayouts(
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  candles: ChartCandle[],
  markers: BacktestChartMarker[],
  selectedSequences: number[] | null | undefined,
  selectedSequence?: number | null,
): Layout[] {
  if (markers.length === 0 || candles.length === 0) return [];
  const candleByTime = new Map(candles.map((candle) => [candle.time, candle]));
  const selected = resolveSelectedSet(selectedSequences, selectedSequence);
  const layouts: Layout[] = [];

  for (const marker of markers) {
    const candle = candleByTime.get(marker.time);
    const x = resolveTradeEventTimeCoordinate(chart, candles, marker.time);
    if (x === null) continue;

    const price =
      marker.price ?? candleAnchorPrice(candle, marker.direction, marker.role) ?? candle?.close;
    if (price == null || !Number.isFinite(price)) continue;
    const y = resolveTradeEventPriceCoordinate(series, price);
    if (y === null) continue;

    layouts.push({
      id: marker.id,
      x,
      y,
      role: marker.role,
      direction: marker.direction,
      label: marker.label,
      active: selected.has(marker.sequence),
    });
  }

  return layouts;
}

export default function BacktestActionFlagOverlay({
  chartRef,
  seriesRef,
  paneRef,
  candles,
  markers,
  selectedSequences = null,
  selectedSequence = null,
  chartReady,
  layoutRevision,
}: BacktestActionFlagOverlayProps) {
  const [layouts, setLayouts] = useState<Layout[]>([]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const pane = paneRef.current;
    if (!chart || !series || !pane || !chartReady || candles.length === 0) {
      setLayouts([]);
      return;
    }

    let rafId = 0;
    const refresh = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        setLayouts(
          computeBacktestActionFlagLayouts(
            chart,
            series,
            candles,
            markers,
            selectedSequences,
            selectedSequence,
          ),
        );
      });
    };

    refresh();
    const raf2 = requestAnimationFrame(refresh);
    const timeScale = chart.timeScale();
    timeScale.subscribeVisibleLogicalRangeChange(refresh);
    timeScale.subscribeVisibleTimeRangeChange(refresh);
    const resizeObserver = new ResizeObserver(refresh);
    resizeObserver.observe(pane);

    return () => {
      cancelAnimationFrame(rafId);
      cancelAnimationFrame(raf2);
      timeScale.unsubscribeVisibleLogicalRangeChange(refresh);
      timeScale.unsubscribeVisibleTimeRangeChange(refresh);
      resizeObserver.disconnect();
    };
  }, [
    chartRef,
    seriesRef,
    paneRef,
    candles,
    markers,
    selectedSequences,
    selectedSequence,
    chartReady,
    layoutRevision,
  ]);

  if (!chartReady || layouts.length === 0) return null;

  return (
    <div className="strategy-signal-flag-overlay backtest-action-flag-overlay" aria-hidden="true">
      {layouts.map((flag) => {
        const tone = roleClass(flag.role, flag.direction);
        const labelSide =
          flag.role === "exit"
            ? flag.direction === "short"
              ? "left"
              : "right"
            : flag.direction === "long"
              ? "left"
              : "right";

        return (
          <Fragment key={flag.id}>
            {flag.active ? (
              <div
                className={`backtest-action-line backtest-action-line--${tone} backtest-action-line--active`}
                style={{ left: `${flag.x}px` }}
              />
            ) : null}
            <span
              className={`backtest-action-dot backtest-action-dot--${tone}${
                flag.active ? " backtest-action-dot--active" : ""
              } backtest-action-dot--${flag.role}`}
              style={{
                left: `${flag.x}px`,
                top: `${flag.y}px`,
                width: `${ANCHOR_SIZE}px`,
                height: `${ANCHOR_SIZE}px`,
              }}
              title={flag.label}
            />
            {flag.active ? (
              <span
                className={`backtest-action-chip backtest-action-chip--${tone} backtest-action-chip--active backtest-action-chip--${labelSide}`}
                style={{ left: `${flag.x}px`, top: `${flag.y}px` }}
              >
                {flag.label}
              </span>
            ) : null}
          </Fragment>
        );
      })}
    </div>
  );
}
