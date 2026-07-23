import type { AssetClass } from "../../../../api/client";
import type { StrategyAssignmentMode } from "../../../../lib/strategies/instruments";
import { SESSION_OPTIONS } from "../../../../lib/marketSessionDefs";
import { TIMEFRAME_OPTIONS, type Timeframe, type TakeProfitMode, type TrailMode } from "../../../../lib/strategyParams";
import { computeBuilderMinCandles } from "../../../../lib/strategyParams/helpers";

export type EmaCrossoverDirection = "long" | "short" | "both";
export type EmaCrossoverConfirmation = "close" | "pullback" | "aggressive";
export type StopLossType = "fixed_pips" | "atr_based" | "structure";
export type OverlayMode = "clean" | "detailed";

export { TIMEFRAME_OPTIONS, type Timeframe, type TakeProfitMode, type TrailMode };

export type ChartOverlays = {
  ema: boolean;
  signals: boolean;
  slTp: boolean;
  adx: boolean;
  atr: boolean;
};

export type EmaCrossoverParams = {
  enabled: boolean;
  assignmentMode: StrategyAssignmentMode;
  assetClass: AssetClass;
  selectedInstruments: string[];
  fastEma: number;
  slowEma: number;
  timeframe: Timeframe;
  minCandles: number;
  adxFilter: boolean;
  adxPeriod: number;
  adxThreshold: number;
  atrFilter: boolean;
  atrPeriod: number;
  minAtr: number;
  /** ATR floor for JPY-quote pairs (USD/JPY, …). */
  minAtrJpy: number;
  direction: EmaCrossoverDirection;
  confirmation: EmaCrossoverConfirmation;
  stopLossEnabled: boolean;
  stopLossType: StopLossType;
  slAtrMultiplier: number;
  slFixedPips: number;
  /** Fixed-pip SL distance used when the traded pair quotes in JPY. */
  slFixedPipsJpy: number;
  slStructureLookback: number;
  takeProfitEnabled: boolean;
  takeProfitType: TakeProfitMode;
  riskRewardRatio: number;
  tpFixedPips: number;
  tpAtrMultiplier: number;
  trailMode: TrailMode;
  trailAtrMultiplier: number;
  reverseCrossoverEnabled: boolean;
  reverseCrossoverMinBarsAfterEntry: number;
  reverseCrossoverMinConfirmationBars: number;
  reverseCrossoverMinSeparationAtr: number;
  approachingEnabled: boolean;
  approachingMaxGapAtr: number;
  approachingMinNarrowBars: number;
  postStopCooldownBars: number;
  htfBiasEnabled: boolean;
  htfBiasTimeframe: "H1" | "H4";
  riskPerTrade: number;
  minConfidence: number;
  maxTradesPerDay: number;
  overrideAllStrategies: boolean;
  priority: number;
  sessions: string[];
  dontHoldBetweenSessions: boolean;
  dontHoldBetweenMarkets: boolean;
  closeBeforeMarketHours: number;
  noLateMarketTrading: boolean;
  lateMarketHours: number;
  overlayMode: OverlayMode;
  overlays: ChartOverlays;
};

const BASE_DEFAULTS = {
  enabled: false,
  assignmentMode: "asset_class" as StrategyAssignmentMode,
  assetClass: "forex" as AssetClass,
  selectedInstruments: [] as string[],
  fastEma: 9,
  slowEma: 21,
  timeframe: "M15" as Timeframe,
  adxFilter: true,
  adxPeriod: 14,
  adxThreshold: 25,
  atrFilter: true,
  atrPeriod: 14,
  minAtr: 0.0008,
  minAtrJpy: 0.05,
  direction: "both" as EmaCrossoverDirection,
  confirmation: "close" as EmaCrossoverConfirmation,
  stopLossEnabled: true,
  stopLossType: "atr_based" as StopLossType,
  slAtrMultiplier: 1.5,
  slFixedPips: 15,
  slFixedPipsJpy: 50,
  slStructureLookback: 10,
  takeProfitEnabled: true,
  takeProfitType: "reverse_crossover" as TakeProfitMode,
  riskRewardRatio: 2.0,
  tpFixedPips: 30,
  tpAtrMultiplier: 2.5,
  trailMode: "atr" as TrailMode,
  trailAtrMultiplier: 1.0,
  reverseCrossoverEnabled: true,
  reverseCrossoverMinBarsAfterEntry: 6,
  reverseCrossoverMinConfirmationBars: 2,
  reverseCrossoverMinSeparationAtr: 0.2,
  approachingEnabled: true,
  approachingMaxGapAtr: 0.5,
  approachingMinNarrowBars: 2,
  postStopCooldownBars: 0,
  htfBiasEnabled: false,
  htfBiasTimeframe: "H4" as const,
  riskPerTrade: 1.0,
  minConfidence: 60,
  maxTradesPerDay: 3,
  overrideAllStrategies: false,
  priority: 50,
  sessions: ["London", "NY"],
  dontHoldBetweenSessions: true,
  dontHoldBetweenMarkets: true,
  closeBeforeMarketHours: 2,
  noLateMarketTrading: true,
  lateMarketHours: 2,
  overlayMode: "detailed" as OverlayMode,
  overlays: {
    ema: true,
    signals: true,
    slTp: true,
    adx: true,
    atr: true,
  },
};

export const DEFAULT_EMA_CROSSOVER_PARAMS: EmaCrossoverParams = {
  ...BASE_DEFAULTS,
  // Floor above indicator warmup so new strategies have a consistent lookback.
  minCandles: Math.max(
    200,
    computeBuilderMinCandles({
      fastEma: BASE_DEFAULTS.fastEma,
      slowEma: BASE_DEFAULTS.slowEma,
      adxFilter: BASE_DEFAULTS.adxFilter,
      atrFilter: BASE_DEFAULTS.atrFilter,
      adxPeriod: BASE_DEFAULTS.adxPeriod,
      atrPeriod: BASE_DEFAULTS.atrPeriod,
      slStructureLookback: BASE_DEFAULTS.slStructureLookback,
    }),
  ),
};

export { SESSION_OPTIONS };
