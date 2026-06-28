import type { AssetClass } from "../../../../api/client";
import type { StrategyAssignmentMode } from "../../../../lib/strategies/instruments";
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
  direction: EmaCrossoverDirection;
  confirmation: EmaCrossoverConfirmation;
  stopLossType: StopLossType;
  slAtrMultiplier: number;
  slFixedPips: number;
  slStructureLookback: number;
  takeProfitType: TakeProfitMode;
  riskRewardRatio: number;
  tpFixedPips: number;
  tpAtrMultiplier: number;
  trailMode: TrailMode;
  trailAtrMultiplier: number;
  riskPerTrade: number;
  minConfidence: number;
  maxTradesPerDay: number;
  overrideAllStrategies: boolean;
  priority: number;
  sessions: string[];
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
  direction: "both" as EmaCrossoverDirection,
  confirmation: "close" as EmaCrossoverConfirmation,
  stopLossType: "atr_based" as StopLossType,
  slAtrMultiplier: 1.5,
  slFixedPips: 15,
  slStructureLookback: 10,
  takeProfitType: "rr_ratio" as TakeProfitMode,
  riskRewardRatio: 2.0,
  tpFixedPips: 30,
  tpAtrMultiplier: 2.5,
  trailMode: "atr" as TrailMode,
  trailAtrMultiplier: 1.0,
  riskPerTrade: 1.0,
  minConfidence: 60,
  maxTradesPerDay: 3,
  overrideAllStrategies: false,
  priority: 50,
  sessions: ["London", "NY"],
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
  minCandles: computeBuilderMinCandles({
    fastEma: BASE_DEFAULTS.fastEma,
    slowEma: BASE_DEFAULTS.slowEma,
    adxFilter: BASE_DEFAULTS.adxFilter,
    atrFilter: BASE_DEFAULTS.atrFilter,
    adxPeriod: BASE_DEFAULTS.adxPeriod,
    atrPeriod: BASE_DEFAULTS.atrPeriod,
    slStructureLookback: BASE_DEFAULTS.slStructureLookback,
  }),
};

export const SESSION_OPTIONS = ["London", "NY", "Asia", "Sydney"] as const;
