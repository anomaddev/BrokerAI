import { Fragment, useEffect, useState, type RefObject } from "react";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { Trade } from "../../api/client";
import type { ChartCandle } from "../../lib/chart/candleBars";
import { parseAppInstant } from "../../lib/formatTime";
import { tradeExitPrice, tradeIsOpen } from "../../lib/trades";
import {
  resolveTradeEventPriceCoordinate,
  resolveTradeEventTimeCoordinate,
} from "../../lib/trades/tradeEventCoordinates";

export type TradeEventFlagLayout = {
  id: string;
  x: number;
  y: number;
  height: number;
  kind: "entry" | "exit";
  direction: "long" | "short";
  label: string;
};

type TradeEventFlagOverlayProps = {
  chartRef: RefObject<IChartApi | null>;
  seriesRef: RefObject<ISeriesApi<"Candlestick"> | null>;
  paneRef: RefObject<HTMLDivElement | null>;
  trade: Trade;
  candles: ChartCandle[];
  chartReady: boolean;
  layoutRevision: number;
};

const FLAG_HEIGHT = 80;
const ANCHOR_SIZE = 7;

function toUnixSeconds(isoTime: string | null | undefined): number | null {
  const date = parseAppInstant(isoTime);
  if (!date) return null;
  return Math.floor(date.getTime() / 1000);
}

function flagModifier(kind: "entry" | "exit", _direction: "long" | "short"): string {
  return kind === "entry" ? "buy" : "sell";
}

function flagExtendsDown(kind: "entry" | "exit", direction: "long" | "short"): boolean {
  if (kind === "exit") {
    return direction === "short";
  }
  return direction === "long";
}

export function computeTradeEventFlagLayouts(
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  trade: Trade,
  candles: ChartCandle[],
): TradeEventFlagLayout[] {
  const layouts: TradeEventFlagLayout[] = [];
  const direction = trade.direction === "short" ? "short" : "long";

  const entryUnix = toUnixSeconds(trade.opened_at);
  if (entryUnix != null && Number.isFinite(trade.entry_price)) {
    const x = resolveTradeEventTimeCoordinate(chart, candles, entryUnix);
    const y = resolveTradeEventPriceCoordinate(series, trade.entry_price);
    if (x !== null && y !== null) {
      layouts.push({
        id: "entry",
        x,
        y,
        height: FLAG_HEIGHT,
        kind: "entry",
        direction,
        label: "ENTRY",
      });
    }
  }

  if (!tradeIsOpen(trade) && trade.closed_at) {
    const exitUnix = toUnixSeconds(trade.closed_at);
    const exitPrice = tradeExitPrice(trade);
    if (exitUnix != null && exitPrice != null && Number.isFinite(exitPrice)) {
      const x = resolveTradeEventTimeCoordinate(chart, candles, exitUnix);
      const y = resolveTradeEventPriceCoordinate(series, exitPrice);
      if (x !== null && y !== null) {
        layouts.push({
          id: "exit",
          x,
          y,
          height: FLAG_HEIGHT,
          kind: "exit",
          direction,
          label: "EXIT",
        });
      }
    }
  }

  return layouts;
}

export default function TradeEventFlagOverlay({
  chartRef,
  seriesRef,
  paneRef,
  trade,
  candles,
  chartReady,
  layoutRevision,
}: TradeEventFlagOverlayProps) {
  const [layouts, setLayouts] = useState<TradeEventFlagLayout[]>([]);

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
        setLayouts(computeTradeEventFlagLayouts(chart, series, trade, candles));
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
  }, [chartRef, seriesRef, paneRef, trade, candles, chartReady, layoutRevision]);

  if (!chartReady || layouts.length === 0) return null;

  return (
    <div className="strategy-signal-flag-overlay trade-event-flag-overlay" aria-hidden="true">
      {layouts.map((flag) => {
        const extendsDown = flagExtendsDown(flag.kind, flag.direction);
        const top = extendsDown ? flag.y : flag.y - flag.height;
        const anchorCenterY = extendsDown ? flag.y + ANCHOR_SIZE / 2 : flag.y - ANCHOR_SIZE / 2;
        const modifier = flagModifier(flag.kind, flag.direction);

        return (
          <Fragment key={flag.id}>
            <div
              key={`${flag.id}-line`}
              className={`trade-event-line trade-event-line--${modifier}`}
              style={{ left: `${flag.x}px` }}
            />
            <div
              key={`${flag.id}-flag`}
              className={`strategy-signal-flag strategy-signal-flag--${modifier}`}
              style={{
                left: `${flag.x}px`,
                top: `${top}px`,
                height: `${flag.height}px`,
              }}
            >
              {extendsDown ? (
                <>
                  <span className="strategy-signal-flag-anchor" />
                  <span className="strategy-signal-flag-pole" />
                </>
              ) : (
                <>
                  <span className="strategy-signal-flag-pole" />
                  <span className="strategy-signal-flag-anchor" />
                </>
              )}
            </div>
            <span
              key={`${flag.id}-label`}
              className={`trade-event-label trade-event-label--${modifier} ${
                flag.kind === "entry" ? "trade-event-label--left" : "trade-event-label--right"
              }`}
              style={{
                left: `${flag.x}px`,
                top: `${anchorCenterY}px`,
              }}
            >
              {flag.label}
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}
