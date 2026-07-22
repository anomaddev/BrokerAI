import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { Link } from "react-router-dom";
import type { CandleBar } from "../../api/client";
import ChartOhlcLegend from "../chart/ChartOhlcLegend";
import MarketClosureOverlay from "../chart/MarketClosureOverlay";
import BacktestActionFlagOverlay from "../backtests/BacktestActionFlagOverlay";
import SignalFlagOverlay from "../strategies/chart/SignalFlagOverlay";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import {
  CANDLESTICK_SERIES_OPTIONS,
  createBrokerChartOptions,
  fitTimeScaleToBounds,
} from "../../lib/chart/brokerChartOptions";
import { chartPriceFormat } from "../../lib/chart/formatChartPrice";
import { computeExploreOverlays } from "../../lib/chart/computeExploreOverlays";
import {
  FOCUS_SERIES_EDGE_BARS,
  FOCUS_VISIBLE_BARS,
  MAX_FOCUS_SERIES_BARS,
  chartFocusVisibleLogicalRange,
  clipExploreOverlayDataToFocus,
  extendCandlesForWarmup,
  focusWindowVisibleBars,
  sliceCandlesAroundUnix,
  sliceCandlesToFocusWindow,
  type ChartFocusWindow,
} from "../../lib/chart/chartFocusWindow";
import {
  applySignalLookback,
  mergeCrossoverSignals,
  type SignalLookback,
} from "../../lib/analysis/analysisRunChartSignals";
import type { BacktestChartMarker } from "../../lib/backtests/backtestChartMarkers";
import { candleBarsToChartCandles, dedupeCandleBars } from "../../lib/chart/candleBars";
import { timeframeToMs } from "../../lib/candleSchedule";
import { findMarketBoundariesForCandles } from "../../lib/chart/forexMarketClosures";
import { useCandleCrosshairOhlc } from "../../lib/chart/useCandleCrosshairOhlc";
import { applyChartTimeLocalization } from "../../lib/chart/chartTimeLocalization";
import {
  parseAppInstant,
} from "../../lib/formatTime";
import { isTailOnlyCandleChange, tailCandleUpdates } from "../../lib/mergeCandleDelta";
import type { StrategyIndicatorLine } from "../../lib/chart/computeExploreOverlays";
import type { CrossoverSignal } from "../../lib/chart/indicators";
import type { Timeframe } from "../../lib/strategyParams";

type ExploreCandleChartProps = {
  symbol: string | null;
  timeframe: Timeframe;
  candles: CandleBar[];
  loading: boolean;
  error: string | null;
  overlayItems: ChartOverlayItem[];
  /** When set, chart zooms to this window and uses full ``candles`` for indicator warmup. */
  focusWindow?: ChartFocusWindow | null;
  /** Signals to always show (e.g. analyzer-recorded crossover for an analysis run). */
  pinnedSignals?: CrossoverSignal[];
  /** When set, only crossover flags on the last N candles ending at the anchor are shown. */
  signalLookback?: SignalLookback | null;
  /**
   * Backtest action markers (entries/exits/skips). When provided, computed BUY/SELL
   * crossover flags are hidden so fills are not confused with skipped signals.
   */
  actionMarkers?: BacktestChartMarker[];
  /**
   * Highlights markers whose sequence is in this set (single action or trade group).
   * Prefer this over ``selectedActionSequence`` when multiple markers should be active.
   */
  selectedActionSequences?: number[] | null;
  /** @deprecated Use ``selectedActionSequences``. */
  selectedActionSequence?: number | null;
  /**
   * Identity of the current focus request (e.g. ``action:12:3`` / ``group:trade-4:5``).
   * Must change when the user re-selects an action even if the time window is unchanged,
   * so the chart re-centers after a pan or same-bar signal→entry step.
   */
  focusRequestKey?: string;
  /**
   * Override the default visible bar count when applying ``focusWindow``.
   * When omitted, derived from the focus window span for the timeframe.
   */
  focusVisibleBars?: number;
};

function toChartTime(isoTime: string): UTCTimestamp | null {
  const date = parseAppInstant(isoTime);
  if (!date) return null;
  return Math.floor(date.getTime() / 1000) as UTCTimestamp;
}

function toSeriesTime(unixSeconds: number): UTCTimestamp {
  return unixSeconds as UTCTimestamp;
}

function syncLineSeriesMap(
  chart: IChartApi,
  seriesMap: Map<string, ISeriesApi<"Line">>,
  lines: StrategyIndicatorLine[],
  priceFormat?: ReturnType<typeof chartPriceFormat>,
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
        ...(priceFormat ? { priceFormat } : {}),
      });
      seriesMap.set(line.id, series);
    }

    series.applyOptions({
      color: line.color,
      title: line.label,
      visible: line.visible,
      ...(priceFormat ? { priceFormat } : {}),
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

export default function ExploreCandleChart({
  symbol,
  timeframe,
  candles,
  loading,
  error,
  overlayItems,
  focusWindow = null,
  pinnedSignals = [],
  signalLookback = null,
  actionMarkers = [],
  selectedActionSequences = null,
  selectedActionSequence = null,
  focusRequestKey = "",
  focusVisibleBars,
}: ExploreCandleChartProps) {
  const resolvedSelectedSequences = useMemo(() => {
    if (selectedActionSequences != null && selectedActionSequences.length > 0) {
      return selectedActionSequences;
    }
    if (selectedActionSequence != null) return [selectedActionSequence];
    return [];
  }, [selectedActionSequences, selectedActionSequence]);

  const resolvedFocusVisibleBars = useMemo(() => {
    if (focusVisibleBars != null && focusVisibleBars > 0) return focusVisibleBars;
    if (focusWindow) return focusWindowVisibleBars(focusWindow, timeframe);
    return FOCUS_VISIBLE_BARS;
  }, [focusVisibleBars, focusWindow, timeframe]);
  const { timeOptions } = useGeneralSettings();
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
  const hasFittedRef = useRef(false);
  /** Last focus window key we centered the viewport on (re-apply when it changes). */
  const appliedFocusKeyRef = useRef("");
  const prevCandlesRef = useRef<CandleBar[]>([]);
  const barCountRef = useRef(0);
  const pendingVisibleRangeRef = useRef<{ from: number; to: number } | null>(null);
  const shiftingWindowRef = useRef(false);
  const [layoutRevision, setLayoutRevision] = useState(0);

  const availableCandles = useMemo(() => {
    if (!focusWindow) return candles;
    const deduped = dedupeCandleBars(candles);
    return sliceCandlesToFocusWindow(
      deduped,
      focusWindow.displaySince,
      focusWindow.displayUntil,
      timeframe,
    );
  }, [candles, focusWindow, timeframe]);

  const focusVisibleKey = focusWindow
    ? `${focusWindow.visibleFromTime}:${focusWindow.visibleToTime}`
    : "";
  // Prefer an explicit request key so same-bar / re-click selections still re-snap.
  const appliedFocusIdentity = focusRequestKey || focusVisibleKey;

  // Focus anchor (action / step). Derived synchronously so the first focused paint
  // slices and centers correctly.
  const focusCenterUnix = focusWindow
    ? Math.floor((focusWindow.visibleFromTime + focusWindow.visibleToTime) / 2)
    : null;
  // Override while the user pans near the edge of a capped mounted series.
  const [panCenterUnix, setPanCenterUnix] = useState<number | null>(null);
  const renderCenterUnix = panCenterUnix ?? focusCenterUnix;

  useEffect(() => {
    setPanCenterUnix(null);
  }, [appliedFocusIdentity]);

  const displayCandles = useMemo(() => {
    if (!focusWindow) return availableCandles;
    if (renderCenterUnix == null) return availableCandles;
    if (availableCandles.length <= MAX_FOCUS_SERIES_BARS) return availableCandles;
    return sliceCandlesAroundUnix(
      availableCandles,
      renderCenterUnix,
      MAX_FOCUS_SERIES_BARS,
    );
  }, [availableCandles, focusWindow, renderCenterUnix]);

  const overlaySourceCandles = useMemo(() => {
    if (!focusWindow) return availableCandles;
    return extendCandlesForWarmup(availableCandles, displayCandles);
  }, [availableCandles, displayCandles, focusWindow]);

  const chartReady = Boolean(symbol && !loading && !error && displayCandles.length > 0);
  const ohlcSnapshot = useCandleCrosshairOhlc(
    priceChartRef,
    candleSeriesRef,
    displayCandles,
    chartReady,
    focusCenterUnix,
  );
  const marketBoundaries = useMemo(
    () => findMarketBoundariesForCandles(displayCandles, timeframe),
    [displayCandles, timeframe],
  );

  const overlayData = useMemo(() => {
    if (overlayItems.length === 0 || overlaySourceCandles.length === 0) return null;
    const computed = computeExploreOverlays(overlayItems, overlaySourceCandles);
    const candleTimes = computed.candles.map((candle) => candle.time);
    const withPinned = {
      ...computed,
      signals: applySignalLookback(
        mergeCrossoverSignals(computed.signals, pinnedSignals),
        candleTimes,
        signalLookback,
      ),
    };
    if (!focusWindow || displayCandles.length === 0) return withPinned;
    // Clip overlays to the mounted series so pan stays cheap; sliding window
    // reloads indicators for neighboring history as the user scrolls.
    const first = parseAppInstant(displayCandles[0]?.time);
    const last = parseAppInstant(displayCandles[displayCandles.length - 1]?.time);
    if (!first || !last) return withPinned;
    const displayFrom = Math.floor(first.getTime() / 1000);
    const displayTo =
      Math.floor(last.getTime() / 1000) + Math.floor(timeframeToMs(timeframe) / 1000);
    return clipExploreOverlayDataToFocus(withPinned, displayFrom, displayTo);
  }, [
    overlayItems,
    overlaySourceCandles,
    displayCandles,
    focusWindow,
    timeframe,
    pinnedSignals,
    signalLookback,
  ]);

  const showAdxPane = Boolean(overlayData?.adxLines.some((line) => line.visible));
  const showRsiPane = Boolean(overlayData?.rsiLines.some((line) => line.visible));
  const hasOverlays = Boolean(overlayData);
  const signalCandles = overlayData?.candles ?? [];
  const useActionMarkers = actionMarkers.length > 0;
  const showSignals = Boolean(overlayData?.signals.length) && !useActionMarkers;
  const markerCandles = useMemo(
    () => candleBarsToChartCandles(displayCandles),
    [displayCandles],
  );

  useEffect(() => {
    if (!priceContainerRef.current || !symbol) return;

    const chartOptions = createBrokerChartOptions({ locked: false });
    const priceChart = createChart(priceContainerRef.current, {
      ...chartOptions,
      width: priceContainerRef.current.clientWidth,
      height: Math.max(priceContainerRef.current.clientHeight, 280),
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
        height: Math.max(adxContainerRef.current.clientHeight, 80),
      });
      adxChartRef.current = adxChart;
      adxLineSeriesRef.current = new Map();
    }

    if (rsiContainerRef.current) {
      rsiChart = createChart(rsiContainerRef.current, {
        ...chartOptions,
        width: rsiContainerRef.current.clientWidth,
        height: Math.max(rsiContainerRef.current.clientHeight, 72),
      });
      rsiChartRef.current = rsiChart;
      rsiLineSeriesRef.current = new Map();
    }

    const syncCharts = () => {
      const range = priceChart.timeScale().getVisibleLogicalRange();
      if (!range) return;
      adxChart?.timeScale().setVisibleLogicalRange(range);
      rsiChart?.timeScale().setVisibleLogicalRange(range);
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncCharts);

    // Resize only updates pixel size — do not refit the time scale. Refitting
    // via fitTimeScaleToBounds was overwriting action/step-through focus zoom.
    const resizeObserver = new ResizeObserver(() => {
      if (priceContainerRef.current && priceChartRef.current) {
        priceChartRef.current.applyOptions({
          width: priceContainerRef.current.clientWidth,
          height: Math.max(priceContainerRef.current.clientHeight, 280),
        });
      }
      if (adxContainerRef.current && adxChartRef.current) {
        adxChartRef.current.applyOptions({
          width: adxContainerRef.current.clientWidth,
          height: Math.max(adxContainerRef.current.clientHeight, 80),
        });
      }
      if (rsiContainerRef.current && rsiChartRef.current) {
        rsiChartRef.current.applyOptions({
          width: rsiContainerRef.current.clientWidth,
          height: Math.max(rsiContainerRef.current.clientHeight, 72),
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
      hasFittedRef.current = false;
      appliedFocusKeyRef.current = "";
      prevCandlesRef.current = [];
      pendingVisibleRangeRef.current = null;
      shiftingWindowRef.current = false;
    };
  }, [symbol]);

  useEffect(() => {
    applyChartTimeLocalization(
      [priceChartRef.current, adxChartRef.current, rsiChartRef.current].filter(
        Boolean,
      ) as IChartApi[],
      timeOptions,
    );
  }, [timeOptions, symbol]);

  useEffect(() => {
    const priceChart = priceChartRef.current;
    const candleSeries = candleSeriesRef.current;
    if (!priceChart || !candleSeries) return;

    const data = displayCandles
      .map((candle) => {
        const time = toChartTime(candle.time);
        if (time == null) return null;
        return {
          time,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);

    const previousCandles = prevCandlesRef.current;
    const tailOnly = !focusWindow && isTailOnlyCandleChange(previousCandles, displayCandles);
    const samplePrice = data[data.length - 1]?.close ?? displayCandles[displayCandles.length - 1]?.close;
    const priceFormat = samplePrice != null ? chartPriceFormat(samplePrice) : undefined;
    if (priceFormat) {
      candleSeries.applyOptions({ priceFormat });
    }

    if (tailOnly && previousCandles.length > 0) {
      for (const bar of tailCandleUpdates(previousCandles, displayCandles)) {
        const time = toChartTime(bar.time);
        if (time == null) continue;
        candleSeries.update({
          time,
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
        });
      }
    } else {
      candleSeries.setData(data);
    }

    prevCandlesRef.current = displayCandles;
    barCountRef.current = data.length;

    syncLineSeriesMap(
      priceChart,
      priceLineSeriesRef.current,
      overlayData?.priceLines ?? [],
      priceFormat,
    );

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

    if (data.length > 0 && !tailOnly) {
      requestAnimationFrame(() => {
        const charts = [priceChart, adxChartRef.current, rsiChartRef.current].filter(
          Boolean,
        ) as IChartApi[];
        const pending = pendingVisibleRangeRef.current;
        if (pending) {
          pendingVisibleRangeRef.current = null;
          const range = {
            from: toSeriesTime(pending.from),
            to: toSeriesTime(pending.to),
          };
          for (const chart of charts) {
            try {
              chart.timeScale().setVisibleRange(range);
            } catch {
              /* range may briefly fall outside a shifted series */
            }
          }
          hasFittedRef.current = true;
          shiftingWindowRef.current = false;
        } else if (focusWindow) {
          // Re-center whenever the focus request changes (action click / step / group).
          // Do not gate on hasFittedRef — that ran before the focus-key reset
          // effect and left the viewport right-aligned on the series tip.
          // Identity includes focusRequestKey so same-bar_time re-selects still snap.
          if (appliedFocusKeyRef.current !== appliedFocusIdentity) {
            // Prior unfocused fits may have pinned the right edge; that clamps
            // the logical range so the anchor sits on the right instead of center.
            for (const chart of charts) {
              chart.timeScale().applyOptions({
                rightOffset: 0,
                fixLeftEdge: false,
                fixRightEdge: false,
              });
            }
            const logical = chartFocusVisibleLogicalRange(
              displayCandles,
              focusWindow,
              resolvedFocusVisibleBars,
            );
            if (logical) {
              for (const chart of charts) {
                try {
                  chart.timeScale().setVisibleLogicalRange(logical);
                } catch {
                  /* series may briefly be empty while shifting */
                }
              }
              appliedFocusKeyRef.current = appliedFocusIdentity;
              hasFittedRef.current = true;
            }
          }
        } else if (!hasFittedRef.current) {
          fitTimeScaleToBounds(priceChart, data.length, { fixEdges: true });
          if (adxChartRef.current) {
            fitTimeScaleToBounds(adxChartRef.current, data.length, { fixEdges: true });
          }
          if (rsiChartRef.current) {
            fitTimeScaleToBounds(rsiChartRef.current, data.length, { fixEdges: true });
          }
          hasFittedRef.current = true;
        }

        setLayoutRevision((revision) => revision + 1);
      });
    } else {
      setLayoutRevision((revision) => revision + 1);
    }
  }, [displayCandles, overlayData, focusWindow, appliedFocusIdentity, resolvedFocusVisibleBars]);

  useEffect(() => {
    hasFittedRef.current = false;
    appliedFocusKeyRef.current = "";
    prevCandlesRef.current = [];
    pendingVisibleRangeRef.current = null;
  }, [symbol, timeframe]);

  // Sliding window: when the user pans near either edge of the mounted series,
  // recenter on the visible midpoint so the rest of the period stays reachable.
  useEffect(() => {
    const priceChart = priceChartRef.current;
    if (!priceChart || !focusWindow) return;
    if (availableCandles.length <= MAX_FOCUS_SERIES_BARS) return;

    const onRangeChange = () => {
      if (shiftingWindowRef.current) return;
      const logical = priceChart.timeScale().getVisibleLogicalRange();
      if (!logical) return;
      const count = barCountRef.current;
      if (count < 1) return;
      const nearLeft = logical.from < FOCUS_SERIES_EDGE_BARS;
      const nearRight = logical.to > count - FOCUS_SERIES_EDGE_BARS;
      if (!nearLeft && !nearRight) return;

      const visible = priceChart.timeScale().getVisibleRange();
      if (!visible) return;
      const from = Number(visible.from);
      const to = Number(visible.to);
      if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return;
      const mid = Math.floor((from + to) / 2);
      if (renderCenterUnix != null && Math.abs(mid - renderCenterUnix) < 30) return;

      shiftingWindowRef.current = true;
      pendingVisibleRangeRef.current = { from, to };
      setPanCenterUnix(mid);
    };

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);
    return () => {
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
    };
  }, [focusWindow, availableCandles.length, renderCenterUnix, symbol]);

  if (!symbol) {
    return <div className="explore-chart explore-chart--idle" aria-hidden />;
  }

  const showEmpty = !loading && !error && displayCandles.length === 0;

  return (
    <div className={`explore-chart strategy-chart-shell${focusWindow ? " explore-chart--focused" : ""}`}>
      <div className="strategy-chart-toolbar explore-chart-ohlc-toolbar">
        <ChartOhlcLegend snapshot={ohlcSnapshot} timeOptions={timeOptions} />
      </div>

      <div className="strategy-chart-panes">
        <div className="strategy-chart-price-pane-wrap">
          {loading ? (
            <div className="explore-chart-status explore-chart-status--loading">Loading…</div>
          ) : null}

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
            <div className="explore-chart-status">
              {focusWindow ? "No candle data for this analysis window." : "No candle data available."}
            </div>
          ) : null}

          <div ref={priceContainerRef} className="strategy-chart-price-pane" />
          {hasOverlays && showSignals ? (
            <SignalFlagOverlay
              chartRef={priceChartRef}
              seriesRef={candleSeriesRef}
              paneRef={priceContainerRef}
              candles={signalCandles}
              signals={overlayData?.signals ?? []}
              visible
              locked={false}
              showDetailed
              layoutRevision={layoutRevision}
            />
          ) : null}
          {useActionMarkers ? (
            <BacktestActionFlagOverlay
              chartRef={priceChartRef}
              seriesRef={candleSeriesRef}
              paneRef={priceContainerRef}
              candles={markerCandles}
              markers={actionMarkers}
              selectedSequences={resolvedSelectedSequences}
              chartReady={chartReady}
              layoutRevision={layoutRevision}
            />
          ) : null}
          <MarketClosureOverlay
            chartRef={priceChartRef}
            paneRef={priceContainerRef}
            boundaries={marketBoundaries}
            layoutRevision={layoutRevision}
          />
        </div>

        <div
          ref={adxContainerRef}
          className={`strategy-chart-adx-pane${showAdxPane ? "" : " strategy-chart-adx-pane--hidden"}`}
        />
        <div
          ref={rsiContainerRef}
          className={`strategy-chart-adx-pane explore-chart-rsi-pane${
            showRsiPane ? "" : " strategy-chart-adx-pane--hidden"
          }`}
        />
      </div>
    </div>
  );
}
