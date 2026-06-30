import type { CandleBar } from "../../api/client";
import { candleBarsToChartCandles, type ChartCandle } from "./candleBars";
import {
  isIndicatorOverlay,
  isSignalsOverlay,
  type ChartOverlayItem,
  type IndicatorOverlayItem,
} from "./chartOverlayState";
import {
  isAdxSpec,
  overlayIndicatorLabel,
  overlayIndicatorPane,
  type OverlayIndicatorSpec,
} from "./indicatorCatalog";
import {
  computeAdxSeries,
  computeEmaSeries,
  computeRsiSeries,
  computeSmaSeries,
  findEmaCrossovers,
  type CrossoverSignal,
  type IndicatorPoint,
} from "./indicators";

export type StrategyIndicatorLine = {
  id: string;
  label: string;
  color: string;
  pane: "price" | "rsi" | "adx";
  points: IndicatorPoint[];
  visible: boolean;
};

export type ExploreOverlayData = {
  candles: ChartCandle[];
  priceLines: StrategyIndicatorLine[];
  rsiLines: StrategyIndicatorLine[];
  adxLines: StrategyIndicatorLine[];
  adxThresholds: { lineId: string; value: number }[];
  signals: CrossoverSignal[];
};

function computeSeriesPoints(
  candles: ChartCandle[],
  spec: OverlayIndicatorSpec,
): IndicatorPoint[] {
  if (isAdxSpec(spec)) {
    return computeAdxSeries(candles, spec.period);
  }

  const source = spec.source ?? "close";
  switch (spec.type) {
    case "ema":
      return computeEmaSeries(candles, spec.period, source);
    case "sma":
      return computeSmaSeries(candles, spec.period, source);
    case "rsi":
      return computeRsiSeries(candles, spec.period, source);
    default:
      return [];
  }
}

function computeIndicatorLine(
  item: IndicatorOverlayItem,
  candles: ChartCandle[],
): StrategyIndicatorLine {
  const points = computeSeriesPoints(candles, item.spec);
  const ref = item.source.kind === "strategy" ? item.source.ref : undefined;
  return {
    id: item.id,
    label: overlayIndicatorLabel(item.spec, ref),
    color: item.color,
    pane: overlayIndicatorPane(item.spec),
    points,
    visible: item.visible,
  };
}

export function computeExploreOverlays(
  items: ChartOverlayItem[],
  bars: CandleBar[],
): ExploreOverlayData {
  const candles = candleBarsToChartCandles(bars);
  const indicatorItems = items.filter(isIndicatorOverlay);
  const signalItems = items.filter(isSignalsOverlay);

  const computedLines = indicatorItems.map((item) => computeIndicatorLine(item, candles));

  const priceLines = computedLines.filter(
    (line) => line.pane === "price" && line.points.length > 0,
  );
  const rsiLines = computedLines.filter(
    (line) => line.pane === "rsi" && line.points.length > 0,
  );
  const adxLines = computedLines.filter(
    (line) => line.pane === "adx" && line.points.length > 0,
  );

  const adxThresholds: ExploreOverlayData["adxThresholds"] = [];
  for (const item of indicatorItems) {
    if (!isAdxSpec(item.spec) || item.adxThreshold == null) continue;
    adxThresholds.push({ lineId: item.id, value: item.adxThreshold });
  }

  const linesByStrategyRef = new Map<string, StrategyIndicatorLine>();
  for (const item of indicatorItems) {
    if (item.source.kind !== "strategy") continue;
    const line = computedLines.find((entry) => entry.id === item.id);
    if (line) {
      linesByStrategyRef.set(`${item.source.strategyId}:${item.source.ref}`, line);
    }
  }

  let signals: CrossoverSignal[] = [];
  for (const signalItem of signalItems) {
    if (!signalItem.visible) continue;

    const strategyId = signalItem.source.strategyId;
    const fastLine = linesByStrategyRef.get(`${strategyId}:${signalItem.fastRef}`);
    const slowLine = linesByStrategyRef.get(`${strategyId}:${signalItem.slowRef}`);
    if (!fastLine || !slowLine) continue;

    const adxForStrategy = indicatorItems.find(
      (item) =>
        item.source.kind === "strategy" &&
        item.source.strategyId === strategyId &&
        isAdxSpec(item.spec),
    );
    const adxLine = adxForStrategy
      ? computedLines.find((line) => line.id === adxForStrategy.id)
      : null;

    let crossoverSignals = findEmaCrossovers(
      fastLine.points,
      slowLine.points,
      adxLine?.points ?? [],
      signalItem.minConfidence,
    );

    if (signalItem.direction === "long") {
      crossoverSignals = crossoverSignals.filter((signal) => signal.type === "bullish");
    } else if (signalItem.direction === "short") {
      crossoverSignals = crossoverSignals.filter((signal) => signal.type === "bearish");
    }

    signals = [...signals, ...crossoverSignals];
  }

  return {
    candles,
    priceLines,
    rsiLines,
    adxLines,
    adxThresholds,
    signals,
  };
}
