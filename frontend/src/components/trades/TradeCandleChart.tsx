import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type UTCTimestamp,
} from "lightweight-charts";
import { Link } from "react-router-dom";
import type { CandleBar, Trade } from "../../api/client";
import ChartOhlcLegend from "../chart/ChartOhlcLegend";
import MarketClosureOverlay from "../chart/MarketClosureOverlay";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import {
  CANDLESTICK_SERIES_OPTIONS,
  createBrokerChartOptions,
} from "../../lib/chart/brokerChartOptions";
import {
  computeExploreOverlays,
  type StrategyIndicatorLine,
} from "../../lib/chart/computeExploreOverlays";
import {
  candleBarsToChartCandles,
  dedupeCandleBars,
} from "../../lib/chart/candleBars";
import { findMarketBoundariesForCandles } from "../../lib/chart/forexMarketClosures";
import { useCandleCrosshairOhlc } from "../../lib/chart/useCandleCrosshairOhlc";
import { applyChartTimeLocalization } from "../../lib/chart/chartTimeLocalization";
import type { Timeframe } from "../../lib/strategyParams";
import {
  clipExploreOverlayData,
  sliceCandlesToWindow,
  tradeChartVisibleTimeRange,
  type TradeCandleWindow,
} from "../../lib/trades/tradeCandleWindow";
import { applyTradeFillAutoscale, clearTradeFillAutoscale } from "../../lib/trades/tradeChartAutoscale";
import { timeframeToMs } from "../../lib/candleSchedule";
import TradeEventFlagOverlay from "./TradeEventFlagOverlay";

type TradeCandleChartProps = {
  trade: Trade;
  timeframe: Timeframe;
  /** Full candle set including strategy warmup history before entry. */
  candles: CandleBar[];
  loading: boolean;
  error: string | null;
  overlayItems: ChartOverlayItem[];
  candleWindow: TradeCandleWindow | null;
};

function toSeriesTime(unixSeconds: number): UTCTimestamp {
  return unixSeconds as UTCTimestamp;
}

function syncLineSeriesMap(
  chart: IChartApi,
  seriesMap: Map<string, ISeriesApi<"Line">>,
  lines: StrategyIndicatorLine[],
) {
  const nextIds = new Set(lines.map((line) => line.id));
  for (const id of seriesMap.keys()) {
    if (nextIds.has(id)) continue;
    const series = seriesMap.get(id);
    if (series) chart.removeSeries(series);
    seriesMap.delete(id);
  }

  for (const line of lines) {
    let series = seriesMap.get(line.id);
    if (!series) {
      series = chart.addLineSeries({
        color: line.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        title: line.label,
      });
      seriesMap.set(line.id, series);
    }

    series.applyOptions({
      color: line.color,
      title: line.label,
      visible: line.visible,
    });
    series.setData(
      line.visible
        ? line.points.map((point) => ({
            time: toSeriesTime(point.time),
            value: point.value,
          }))
        : [],
    );
  }
}

function clampLogicalRange(
  range: LogicalRange,
  maxRange: LogicalRange,
  barCount: number,
): LogicalRange {
  const maxSpan = maxRange.to - maxRange.from;
  const span = range.to - range.from;

  if (span >= maxSpan - 0.001) {
    return { from: maxRange.from, to: maxRange.to };
  }

  let from = range.from;
  let to = range.to;

  if (from < 0) {
    from = 0;
    to = span;
  }
  if (to > barCount - 1) {
    to = barCount - 1;
    from = Math.max(0, to - span);
  }

  return { from, to };
}

export default function TradeCandleChart({
  trade,
  timeframe,
  candles,
  loading,
  error,
  overlayItems,
  candleWindow,
}: TradeCandleChartProps) {
  const { timeOptions } = useGeneralSettings();
  const priceWrapRef = useRef<HTMLDivElement>(null);
  const priceContainerRef = useRef<HTMLDivElement>(null);
  const adxContainerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const adxChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const priceLineSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const adxLineSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const rsiLineSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const adxPriceLinesRef = useRef<Map<string, IPriceLine[]>>(new Map());
  const maxLogicalRangeRef = useRef<LogicalRange | null>(null);
  const barCountRef = useRef(0);
  const clampingRef = useRef(false);
  const [layoutRevision, setLayoutRevision] = useState(0);

  const warmupCandles = useMemo(() => dedupeCandleBars(candles), [candles]);

  const displayCandles = useMemo(() => {
    if (!candleWindow) return warmupCandles;
    return sliceCandlesToWindow(
      warmupCandles,
      candleWindow.displaySince,
      candleWindow.displayUntil,
      timeframe,
    );
  }, [warmupCandles, candleWindow]);

  const chartReady = !loading && !error && displayCandles.length > 0;
  const chartCandles = useMemo(
    () => candleBarsToChartCandles(displayCandles),
    [displayCandles],
  );

  const ohlcSnapshot = useCandleCrosshairOhlc(priceChartRef, candleSeriesRef, displayCandles, chartReady);
  const marketBoundaries = useMemo(
    () => findMarketBoundariesForCandles(displayCandles, timeframe),
    [displayCandles, timeframe],
  );

  const overlayData = useMemo(() => {
    if (overlayItems.length === 0 || warmupCandles.length === 0) return null;
    const computed = computeExploreOverlays(overlayItems, warmupCandles);
    if (!candleWindow) return computed;
    return clipExploreOverlayData(
      computed,
      candleWindow.visibleFromTime,
      candleWindow.visibleToTime + Math.floor(timeframeToMs(timeframe) / 1000),
    );
  }, [overlayItems, warmupCandles, candleWindow]);

  const showAdxPane = Boolean(overlayData?.adxLines.some((line) => line.visible));
  const showRsiPane = Boolean(overlayData?.rsiLines.some((line) => line.visible));

  const applyClampedRange = (charts: IChartApi[], range: LogicalRange) => {
    for (const chart of charts) {
      chart.timeScale().setVisibleLogicalRange(range);
    }
  };

  const applyVisibleTimeRange = (charts: IChartApi[], from: number, to: number) => {
    const range = { from: toSeriesTime(from), to: toSeriesTime(to) };
    for (const chart of charts) {
      chart.timeScale().setVisibleRange(range);
    }
  };

  const enforceZoomLimits = (sourceChart: IChartApi) => {
    const maxRange = maxLogicalRangeRef.current;
    const barCount = barCountRef.current;
    if (!maxRange || barCount < 1 || clampingRef.current) return;

    const range = sourceChart.timeScale().getVisibleLogicalRange();
    if (!range) return;

    const clamped = clampLogicalRange(range, maxRange, barCount);
    if (
      Math.abs(clamped.from - range.from) > 0.001 ||
      Math.abs(clamped.to - range.to) > 0.001
    ) {
      clampingRef.current = true;
      const charts = [priceChartRef.current, adxChartRef.current, rsiChartRef.current].filter(
        Boolean,
      ) as IChartApi[];
      applyClampedRange(charts, clamped);
      clampingRef.current = false;
    }
  };

  useEffect(() => {
    if (!priceContainerRef.current) return;

    const chartOptions = createBrokerChartOptions({
      locked: false,
      fixTimeScaleEdges: true,
      signalScaleMargin: 0.22,
      secondsVisible: true,
    });
    const priceChart = createChart(priceContainerRef.current, {
      ...chartOptions,
      width: priceContainerRef.current.clientWidth,
      height: priceContainerRef.current.clientHeight,
    });
    const candleSeries = priceChart.addCandlestickSeries(CANDLESTICK_SERIES_OPTIONS);

    priceChartRef.current = priceChart;
    candleSeriesRef.current = candleSeries;
    priceLineSeriesRef.current = new Map();

    let adxChart: IChartApi | null = null;
    let rsiChart: IChartApi | null = null;

    if (adxContainerRef.current) {
      adxChart = createChart(adxContainerRef.current, {
        ...chartOptions,
        width: adxContainerRef.current.clientWidth,
        height: adxContainerRef.current.clientHeight,
      });
      adxChartRef.current = adxChart;
      adxLineSeriesRef.current = new Map();
    }

    if (rsiContainerRef.current) {
      rsiChart = createChart(rsiContainerRef.current, {
        ...chartOptions,
        width: rsiContainerRef.current.clientWidth,
        height: rsiContainerRef.current.clientHeight,
      });
      rsiChartRef.current = rsiChart;
      rsiLineSeriesRef.current = new Map();
    }

    const syncCharts = () => {
      enforceZoomLimits(priceChart);
      const range = priceChart.timeScale().getVisibleLogicalRange();
      if (!range) return;
      adxChart?.timeScale().setVisibleLogicalRange(range);
      rsiChart?.timeScale().setVisibleLogicalRange(range);
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncCharts);

    const resizeObserver = new ResizeObserver(() => {
      if (priceContainerRef.current && priceChartRef.current) {
        priceChartRef.current.applyOptions({
          width: priceContainerRef.current.clientWidth,
          height: priceContainerRef.current.clientHeight,
        });
      }
      if (adxContainerRef.current && adxChartRef.current) {
        adxChartRef.current.applyOptions({
          width: adxContainerRef.current.clientWidth,
          height: adxContainerRef.current.clientHeight,
        });
      }
      if (rsiContainerRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({
          width: rsiContainerRef.current.clientWidth,
          height: rsiContainerRef.current.clientHeight,
        });
      }
      setLayoutRevision((revision) => revision + 1);
    });

    resizeObserver.observe(priceContainerRef.current);
    if (adxContainerRef.current) resizeObserver.observe(adxContainerRef.current);
    if (rsiContainerRef.current) resizeObserver.observe(rsiContainerRef.current);

    applyChartTimeLocalization(
      [priceChart, adxChart, rsiChart].filter(Boolean) as IChartApi[],
      timeOptions,
    );

    return () => {
      resizeObserver.disconnect();
      clearTradeFillAutoscale(candleSeries);
      priceChart.remove();
      adxChart?.remove();
      rsiChart?.remove();
      priceChartRef.current = null;
      adxChartRef.current = null;
      rsiChartRef.current = null;
      candleSeriesRef.current = null;
      priceLineSeriesRef.current = new Map();
      adxLineSeriesRef.current = new Map();
      rsiLineSeriesRef.current = new Map();
      adxPriceLinesRef.current = new Map();
      maxLogicalRangeRef.current = null;
      barCountRef.current = 0;
    };
  }, [trade.id]);

  useEffect(() => {
    applyChartTimeLocalization(
      [priceChartRef.current, adxChartRef.current, rsiChartRef.current].filter(
        Boolean,
      ) as IChartApi[],
      timeOptions,
    );
  }, [timeOptions, trade.id]);

  useEffect(() => {
    const priceChart = priceChartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!priceChart || !candleSeries) return;

    const data = chartCandles;

    candleSeries.setData(data);
    barCountRef.current = data.length;
    applyTradeFillAutoscale(candleSeries, trade);

    syncLineSeriesMap(priceChart, priceLineSeriesRef.current, overlayData?.priceLines ?? []);

    const adxChart = adxChartRef.current;
    if (adxChart) {
      syncLineSeriesMap(adxChart, adxLineSeriesRef.current, overlayData?.adxLines ?? []);

      for (const [lineId, lines] of adxPriceLinesRef.current) {
        const series = adxLineSeriesRef.current.get(lineId);
        if (!series) continue;
        for (const priceLine of lines) {
          series.removePriceLine(priceLine);
        }
      }
      adxPriceLinesRef.current = new Map();

      for (const threshold of overlayData?.adxThresholds ?? []) {
        const series = adxLineSeriesRef.current.get(threshold.lineId);
        const line = overlayData?.adxLines.find((entry) => entry.id === threshold.lineId);
        if (!series || !line?.visible) continue;

        const priceLines = [
          series.createPriceLine({
            price: threshold.value,
            color: "#8b9cb3",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `ADX ${threshold.value}`,
          }),
        ];
        adxPriceLinesRef.current.set(threshold.lineId, priceLines);
      }
    }

    const rsiChart = rsiChartRef.current;
    if (rsiChart) {
      syncLineSeriesMap(rsiChart, rsiLineSeriesRef.current, overlayData?.rsiLines ?? []);
    }

    if (data.length > 0) {
      requestAnimationFrame(() => {
        const charts = [priceChart, adxChartRef.current, rsiChartRef.current].filter(
          Boolean,
        ) as IChartApi[];

        maxLogicalRangeRef.current = { from: 0, to: Math.max(0, data.length - 1) };

        if (candleWindow) {
          const { from, to } = tradeChartVisibleTimeRange(candleWindow);
          applyVisibleTimeRange(charts, from, to);
        } else {
          applyClampedRange(charts, maxLogicalRangeRef.current);
        }

        requestAnimationFrame(() => {
          setLayoutRevision((revision) => revision + 1);
        });
      });
    } else {
      maxLogicalRangeRef.current = null;
      setLayoutRevision((revision) => revision + 1);
    }
  }, [chartCandles, overlayData, trade, candleWindow]);

  const showEmpty = !loading && !error && displayCandles.length === 0;

  return (
    <div className="trade-candle-chart strategy-chart-shell">
      <div className="strategy-chart-toolbar explore-chart-ohlc-toolbar">
        <ChartOhlcLegend snapshot={ohlcSnapshot} timeOptions={timeOptions} />
      </div>

      <div className="strategy-chart-panes trade-candle-chart-panes">
        <div
          ref={priceWrapRef}
          className="strategy-chart-price-pane-wrap trade-candle-chart-price-wrap"
        >
          {!loading && error ? (
            <div className="explore-chart-status explore-chart-status--error">
              <p>{error}</p>
              {error.toLowerCase().includes("oanda") ? (
                <Link to="/settings/exchanges/oanda" className="btn btn-secondary btn-sm">
                  Open OANDA settings
                </Link>
              ) : null}
            </div>
          ) : null}

          {showEmpty ? (
            <div className="explore-chart-status">No candle data for this trade window.</div>
          ) : null}

          <div ref={priceContainerRef} className="strategy-chart-price-pane trade-candle-chart-pane" />
          <TradeEventFlagOverlay
            chartRef={priceChartRef}
            seriesRef={candleSeriesRef}
            paneRef={priceContainerRef}
            trade={trade}
            candles={chartCandles}
            chartReady={chartReady}
            layoutRevision={layoutRevision}
          />
          <MarketClosureOverlay
            chartRef={priceChartRef}
            paneRef={priceContainerRef}
            boundaries={marketBoundaries}
            layoutRevision={layoutRevision}
          />
        </div>

        <div
          ref={adxContainerRef}
          className={`strategy-chart-adx-pane trade-candle-chart-subpane${
            showAdxPane ? "" : " strategy-chart-adx-pane--hidden"
          }`}
        />
        <div
          ref={rsiContainerRef}
          className={`strategy-chart-adx-pane explore-chart-rsi-pane trade-candle-chart-subpane${
            showRsiPane ? "" : " strategy-chart-adx-pane--hidden"
          }`}
        />
      </div>
    </div>
  );
}
