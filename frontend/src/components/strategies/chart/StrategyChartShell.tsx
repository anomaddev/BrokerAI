import { useEffect, useMemo, useRef, useState } from "react";
import {
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import ChartOverlayToggle from "./ChartOverlayToggle";
import SignalFlagOverlay from "./SignalFlagOverlay";
import type { EmaCrossoverParams } from "../../../pages/strategies/presets/emaCrossover/defaults";
import {
  CANDLESTICK_SERIES_OPTIONS,
  createBrokerChartOptions,
  fitTimeScaleToBounds,
} from "../../../lib/chart/brokerChartOptions";
import {
  computeAdx,
  computeAtr,
  computeEma,
  computeSlTpDistances,
  findCrossovers,
  generateMockCandles,
} from "../../../pages/strategies/presets/emaCrossover/mockData";
import { useGeneralSettings } from "../../../hooks/useGeneralSettings";
import { applyChartTimeLocalization } from "../../../lib/chart/chartTimeLocalization";

type StrategyChartShellProps = {
  params: EmaCrossoverParams;
  locked?: boolean;
  onOverlayChange: (key: keyof EmaCrossoverParams["overlays"], value: boolean) => void;
};

function toChartTime(unixSeconds: number): UTCTimestamp {
  return unixSeconds as UTCTimestamp;
}

export default function StrategyChartShell({
  params,
  locked = false,
  onOverlayChange,
}: StrategyChartShellProps) {
  const { timeOptions } = useGeneralSettings();
  const priceContainerRef = useRef<HTMLDivElement>(null);
  const adxContainerRef = useRef<HTMLDivElement>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const adxChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const fastEmaRef = useRef<ISeriesApi<"Line"> | null>(null);
  const slowEmaRef = useRef<ISeriesApi<"Line"> | null>(null);
  const adxSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const candlePriceLinesRef = useRef<IPriceLine[]>([]);
  const adxPriceLinesRef = useRef<IPriceLine[]>([]);
  const barCountRef = useRef(0);
  const hasFittedTimeScaleRef = useRef(false);
  const [chartLayoutRevision, setChartLayoutRevision] = useState(0);

  const candles = useMemo(() => generateMockCandles(120), []);
  const chartData = useMemo(() => {
    const fast = computeEma(candles, params.fastEma);
    const slow = computeEma(candles, params.slowEma);
    const adx = computeAdx(candles, params.adxPeriod);
    const atr = computeAtr(candles, params.atrPeriod);
    const signals = findCrossovers(fast, slow, adx);
    const lastBullish = [...signals].reverse().find((s) => s.type === "bullish");
    const entry = lastBullish?.price ?? candles[candles.length - 1].close;
    const { slDistance, tpDistance } = computeSlTpDistances(params, candles, atr, entry);
    return { fast, slow, adx, atr, signals, entry, slDistance, tpDistance, lastBullish };
  }, [candles, params]);

  const showDetailed = params.overlayMode === "detailed";
  const showSignals = params.overlays.signals;

  const filteredSignals = useMemo(
    () =>
      chartData.signals.filter((signal) => {
        if (params.direction === "long" && signal.type === "bearish") return false;
        if (params.direction === "short" && signal.type === "bullish") return false;
        if (signal.confidence < params.minConfidence) return false;
        return true;
      }),
    [chartData.signals, params.direction, params.minConfidence],
  );

  useEffect(() => {
    if (!priceContainerRef.current || !adxContainerRef.current) return;

    const signalScaleMargin = locked ? 0.32 : 0.22;
    const chartOptions = createBrokerChartOptions({
      locked,
      fontSize: locked ? 12 : 11,
      signalScaleMargin,
      fixTimeScaleEdges: true,
    });

    const priceChart = createChart(priceContainerRef.current, {
      ...chartOptions,
      width: priceContainerRef.current.clientWidth,
      height: Math.max(priceContainerRef.current.clientHeight, 280),
    });
    const adxChart = createChart(adxContainerRef.current, {
      ...chartOptions,
      width: adxContainerRef.current.clientWidth,
      height: Math.max(adxContainerRef.current.clientHeight, 80),
    });

    priceChartRef.current = priceChart;
    adxChartRef.current = adxChart;

    const candleSeries = priceChart.addCandlestickSeries(CANDLESTICK_SERIES_OPTIONS);
    const fastSeries = priceChart.addLineSeries({
      color: "#3b82f6",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: `EMA ${params.fastEma}`,
    });
    const slowSeries = priceChart.addLineSeries({
      color: "#f59e0b",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: `EMA ${params.slowEma}`,
    });
    const adxSeries = adxChart.addLineSeries({
      color: "#a78bfa",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "ADX",
    });

    candleSeriesRef.current = candleSeries;
    fastEmaRef.current = fastSeries;
    slowEmaRef.current = slowSeries;
    adxSeriesRef.current = adxSeries;
    candlePriceLinesRef.current = [];
    adxPriceLinesRef.current = [];

    const syncCharts = () => {
      const range = priceChart.timeScale().getVisibleLogicalRange();
      if (range) adxChart.timeScale().setVisibleLogicalRange(range);
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncCharts);

    const refitTimeScales = () => {
      const count = barCountRef.current;
      if (count < 1) return;
      requestAnimationFrame(() => {
        fitTimeScaleToBounds(priceChart, count, { fixEdges: true });
        fitTimeScaleToBounds(adxChart, count, { fixEdges: true });
      });
    };

    const resizeObserver = new ResizeObserver(() => {
      if (priceContainerRef.current) {
        priceChart.applyOptions({
          width: priceContainerRef.current.clientWidth,
          height: Math.max(priceContainerRef.current.clientHeight, 280),
        });
      }
      if (adxContainerRef.current) {
        adxChart.applyOptions({
          width: adxContainerRef.current.clientWidth,
          height: Math.max(adxContainerRef.current.clientHeight, 80),
        });
      }
      refitTimeScales();
    });
    resizeObserver.observe(priceContainerRef.current);
    resizeObserver.observe(adxContainerRef.current);

    applyChartTimeLocalization([priceChart, adxChart], timeOptions);

    return () => {
      resizeObserver.disconnect();
      priceChart.remove();
      adxChart.remove();
      priceChartRef.current = null;
      adxChartRef.current = null;
      candleSeriesRef.current = null;
      fastEmaRef.current = null;
      slowEmaRef.current = null;
      adxSeriesRef.current = null;
      candlePriceLinesRef.current = [];
      adxPriceLinesRef.current = [];
    };
  }, [locked]);

  useEffect(() => {
    applyChartTimeLocalization(
      [priceChartRef.current, adxChartRef.current].filter(Boolean) as IChartApi[],
      timeOptions,
    );
  }, [timeOptions, locked]);

  function clearPriceLines(
    series: ISeriesApi<"Candlestick"> | ISeriesApi<"Line">,
    lines: IPriceLine[],
  ) {
    for (const line of lines) {
      series.removePriceLine(line);
    }
    lines.length = 0;
  }

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const fastSeries = fastEmaRef.current;
    const slowSeries = slowEmaRef.current;
    const adxSeries = adxSeriesRef.current;
    if (!candleSeries || !fastSeries || !slowSeries || !adxSeries) return;

    const showEma = params.overlays.ema && params.overlayMode !== "clean" ? true : params.overlays.ema;
    const showSlTp = params.overlays.slTp && showDetailed;
    const showAdx = params.overlays.adx && params.adxFilter && params.overlayMode === "detailed";
    const showAtr = params.overlays.atr && params.atrFilter && showDetailed;

    candleSeries.setData(
      candles.map((c) => ({
        time: toChartTime(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    fastSeries.setData(
      showEma
        ? chartData.fast.map((p) => ({ time: toChartTime(p.time), value: p.value }))
        : [],
    );
    fastSeries.applyOptions({ title: `EMA ${params.fastEma}` });

    slowSeries.setData(
      showEma
        ? chartData.slow.map((p) => ({ time: toChartTime(p.time), value: p.value }))
        : [],
    );
    slowSeries.applyOptions({ title: `EMA ${params.slowEma}` });

    adxSeries.setData(
      showAdx
        ? chartData.adx.map((p) => ({ time: toChartTime(p.time), value: p.value }))
        : [],
    );

    candleSeries.setMarkers([]);

    clearPriceLines(candleSeries, candlePriceLinesRef.current);

    if (showSlTp && chartData.lastBullish) {
      const entry = chartData.entry;
      const sl = entry - chartData.slDistance;
      const tp = entry + chartData.tpDistance;
      candlePriceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: entry,
          color: "#3b82f6",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "Entry",
        }),
      );
      candlePriceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: sl,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title:
            params.stopLossType === "fixed_pips"
              ? `SL ${params.slFixedPips}p`
              : params.stopLossType === "structure"
                ? "SL swing"
                : "SL",
        }),
      );
      candlePriceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: tp,
          color: "#22c55e",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title:
            params.takeProfitType === "fixed_pips"
              ? `TP ${params.tpFixedPips}p`
              : params.takeProfitType === "atr_based"
                ? `TP ${params.tpAtrMultiplier}×ATR`
                : `TP ${params.riskRewardRatio.toFixed(1)}R`,
        }),
      );
      if (params.takeProfitType === "trailing_stop" && params.trailMode === "atr") {
        candlePriceLinesRef.current.push(
          candleSeries.createPriceLine({
            price: entry - chartData.atr * params.trailAtrMultiplier,
            color: "#f59e0b",
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: "Trail",
          }),
        );
      }
    }

    if (showAtr) {
      const lastClose = candles[candles.length - 1].close;
      const band = chartData.atr * 1.5;
      candlePriceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: lastClose + band,
          color: "rgba(139, 156, 179, 0.4)",
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: false,
          title: "",
        }),
      );
      candlePriceLinesRef.current.push(
        candleSeries.createPriceLine({
          price: lastClose - band,
          color: "rgba(139, 156, 179, 0.4)",
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: false,
          title: "",
        }),
      );
    }

    clearPriceLines(adxSeries, adxPriceLinesRef.current);
    if (showAdx) {
      adxPriceLinesRef.current.push(
        adxSeries.createPriceLine({
          price: params.adxThreshold,
          color: "#8b9cb3",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `ADX ${params.adxThreshold}`,
        }),
      );
    }

    barCountRef.current = candles.length;
    requestAnimationFrame(() => {
      if (!hasFittedTimeScaleRef.current) {
        hasFittedTimeScaleRef.current = true;
        if (priceChartRef.current) fitTimeScaleToBounds(priceChartRef.current, candles.length, { fixEdges: true });
        if (adxChartRef.current) fitTimeScaleToBounds(adxChartRef.current, candles.length, { fixEdges: true });
      }
      setChartLayoutRevision((revision) => revision + 1);
    });
  }, [candles, chartData, params, locked, showDetailed]);

  const showAdxPane = params.overlays.adx && params.adxFilter && params.overlayMode === "detailed";
  const adxBadge =
    chartData.adx.length > 0 ? chartData.adx[chartData.adx.length - 1].value : 0;

  return (
    <div className={`strategy-chart-shell${locked ? " strategy-chart-shell--locked" : ""}`}>
      <div className="strategy-chart-toolbar">
        <div className="strategy-chart-overlay-toggles">
          <ChartOverlayToggle
            label="EMA"
            active={params.overlays.ema}
            onChange={(v) => onOverlayChange("ema", v)}
          />
          <ChartOverlayToggle
            label="Signals"
            active={params.overlays.signals}
            onChange={(v) => onOverlayChange("signals", v)}
          />
          <ChartOverlayToggle
            label="SL-TP"
            active={params.overlays.slTp}
            onChange={(v) => onOverlayChange("slTp", v)}
          />
          <ChartOverlayToggle
            label="ADX"
            active={params.overlays.adx}
            onChange={(v) => onOverlayChange("adx", v)}
          />
          <ChartOverlayToggle
            label="ATR"
            active={params.overlays.atr}
            onChange={(v) => onOverlayChange("atr", v)}
          />
        </div>
        {locked && (
          <span className="strategy-chart-example-label">Example chart</span>
        )}
        <div className="strategy-chart-legend">
          {params.overlays.signals && (
            <>
              <span className="strategy-chart-legend-item">
                <span className="strategy-chart-legend-flag strategy-chart-legend-flag--buy" aria-hidden="true">
                  <span className="strategy-chart-legend-flag-pole" />
                  <span className="strategy-chart-legend-flag-badge" />
                </span>
                Buy
              </span>
              <span className="strategy-chart-legend-item">
                <span className="strategy-chart-legend-flag strategy-chart-legend-flag--sell" aria-hidden="true">
                  <span className="strategy-chart-legend-flag-badge" />
                  <span className="strategy-chart-legend-flag-pole" />
                </span>
                Sell
              </span>
            </>
          )}
          {params.overlays.ema && (
            <>
              <span className="strategy-chart-legend-item">
                <span className="strategy-chart-legend-swatch strategy-chart-legend-swatch--fast" />
                EMA {params.fastEma}
              </span>
              <span className="strategy-chart-legend-item">
                <span className="strategy-chart-legend-swatch strategy-chart-legend-swatch--slow" />
                EMA {params.slowEma}
              </span>
            </>
          )}
        </div>
      </div>
      <div className="strategy-chart-panes">
        <div className="strategy-chart-price-pane-wrap">
          <div ref={priceContainerRef} className="strategy-chart-price-pane" />
          <SignalFlagOverlay
            chartRef={priceChartRef}
            seriesRef={candleSeriesRef}
            paneRef={priceContainerRef}
            candles={candles}
            signals={filteredSignals}
            visible={showSignals}
            locked={locked}
            showDetailed={showDetailed}
            layoutRevision={chartLayoutRevision}
          />
        </div>
        <div
          ref={adxContainerRef}
          className={`strategy-chart-adx-pane${showAdxPane ? "" : " strategy-chart-adx-pane--hidden"}`}
        />
        {!showAdxPane && (
          <div className="strategy-chart-adx-badge">
            ADX {adxBadge.toFixed(0)} {adxBadge >= params.adxThreshold ? "✓" : ""}
          </div>
        )}
        {locked && <div className="strategy-chart-lock-shield" aria-hidden="true" />}
      </div>
    </div>
  );
}
