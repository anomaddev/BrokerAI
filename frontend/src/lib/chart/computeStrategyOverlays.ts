import type { StrategyParamsV1, IndicatorSpec } from "../strategyParams";
import { candleBarsToChartCandles, type ChartCandle } from "./candleBars";
import type { CandleBar } from "../../api/client";
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
};

export type StrategyOverlayData = {
  candles: ChartCandle[];
  priceLines: StrategyIndicatorLine[];
  rsiLine: StrategyIndicatorLine | null;
  adxLine: StrategyIndicatorLine | null;
  adxThreshold: number | null;
  signals: CrossoverSignal[];
};

const INDICATOR_COLORS = ["#3b82f6", "#f59e0b", "#22c55e", "#a78bfa", "#ec4899", "#14b8a6"];

function indicatorLabel(id: string, spec: IndicatorSpec): string {
  switch (spec.type) {
    case "ema":
      return `EMA ${spec.period}`;
    case "sma":
      return `SMA ${spec.period}`;
    case "rsi":
      return `RSI ${spec.period}`;
    default:
      return id;
  }
}

function computeIndicatorSeries(
  candles: ChartCandle[],
  id: string,
  spec: IndicatorSpec,
): StrategyIndicatorLine {
  const source = spec.source ?? "close";
  let points: IndicatorPoint[] = [];
  let pane: StrategyIndicatorLine["pane"] = "price";

  switch (spec.type) {
    case "ema":
      points = computeEmaSeries(candles, spec.period, source);
      break;
    case "sma":
      points = computeSmaSeries(candles, spec.period, source);
      break;
    case "rsi":
      points = computeRsiSeries(candles, spec.period, source);
      pane = "rsi";
      break;
    default:
      break;
  }

  const colorFromSpec = spec.type === "ema" ? spec.color : undefined;
  const colorIndex = id.length + (spec.type === "ema" ? spec.period : 0);
  return {
    id,
    label: indicatorLabel(id, spec),
    color: colorFromSpec ?? INDICATOR_COLORS[colorIndex % INDICATOR_COLORS.length],
    pane,
    points,
  };
}

export function computeStrategyOverlays(
  params: StrategyParamsV1,
  bars: CandleBar[],
): StrategyOverlayData {
  const candles = candleBarsToChartCandles(bars);
  const indicatorEntries = Object.entries(params.indicators ?? {});

  const computed = indicatorEntries.map(([id, spec], index) => ({
    ...computeIndicatorSeries(candles, id, spec),
    color: INDICATOR_COLORS[index % INDICATOR_COLORS.length],
  }));

  const priceLines = computed.filter((line) => line.pane === "price" && line.points.length > 0);
  const rsiCandidates = computed.filter((line) => line.pane === "rsi" && line.points.length > 0);
  const rsiLine = rsiCandidates[0] ?? null;

  const adxFilter = params.filters.find((filter) => filter.type === "adx" && filter.enabled);
  const adxLine =
    adxFilter?.type === "adx"
      ? {
          id: "adx-filter",
          label: `ADX ${adxFilter.period}`,
          color: "#a78bfa",
          pane: "adx" as const,
          points: computeAdxSeries(candles, adxFilter.period),
        }
      : null;

  let signals: CrossoverSignal[] = [];
  if (params.signal.type === "ema_crossover") {
    const fastRef = params.signal.fast_ref;
    const slowRef = params.signal.slow_ref;
    const fastLine = computed.find((line) => line.id === fastRef);
    const slowLine = computed.find((line) => line.id === slowRef);
    const adxPoints = adxLine?.points ?? [];

    if (fastLine && slowLine) {
      let crossoverSignals = findEmaCrossovers(
        fastLine.points,
        slowLine.points,
        adxPoints,
        params.execution.min_confidence,
      );

      if (params.signal.direction === "long") {
        crossoverSignals = crossoverSignals.filter((signal) => signal.type === "bullish");
      } else if (params.signal.direction === "short") {
        crossoverSignals = crossoverSignals.filter((signal) => signal.type === "bearish");
      }

      signals = crossoverSignals;
    }
  }

  return {
    candles,
    priceLines,
    rsiLine,
    adxLine: adxLine && adxLine.points.length > 0 ? adxLine : null,
    adxThreshold: adxFilter?.type === "adx" ? adxFilter.threshold : null,
    signals,
  };
}
