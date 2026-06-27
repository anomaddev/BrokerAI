import type { AssetClass } from "../../../../api/client";
import type { StrategyAssignmentMode } from "../../../../lib/strategies/instruments";
import { TIMEFRAME_OPTIONS, type Timeframe } from "../../../../lib/strategyParams";

export type EmaCrossoverDirection = "long" | "short" | "both";
export type EmaCrossoverConfirmation = "close" | "pullback" | "aggressive";
export type StopLossType = "fixed_pips" | "atr_based" | "structure";
export type TakeProfitType = "fixed_pips" | "rr_ratio" | "atr_based";
export type OverlayMode = "clean" | "detailed";

export { TIMEFRAME_OPTIONS, type Timeframe };

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
  takeProfitType: TakeProfitType;
  riskRewardRatio: number;
  tpFixedPips: number;
  tpAtrMultiplier: number;
  trailingStop: boolean;
  trailAtrMultiplier: number;
  riskPerTrade: number;
  minConfidence: number;
  maxTradesPerDay: number;
  overrideAllStrategies: boolean;
  sessions: string[];
  overlayMode: OverlayMode;
  overlays: ChartOverlays;
};

export const DEFAULT_EMA_CROSSOVER_PARAMS: EmaCrossoverParams = {
  enabled: false,
  assignmentMode: "asset_class",
  assetClass: "forex",
  selectedInstruments: [],
  fastEma: 9,
  slowEma: 21,
  timeframe: "M15",
  adxFilter: true,
  adxPeriod: 14,
  adxThreshold: 25,
  atrFilter: true,
  atrPeriod: 14,
  minAtr: 0.0008,
  direction: "both",
  confirmation: "close",
  stopLossType: "atr_based",
  slAtrMultiplier: 1.5,
  slFixedPips: 15,
  slStructureLookback: 10,
  takeProfitType: "rr_ratio",
  riskRewardRatio: 2.0,
  tpFixedPips: 30,
  tpAtrMultiplier: 2.5,
  trailingStop: false,
  trailAtrMultiplier: 1.0,
  riskPerTrade: 1.0,
  minConfidence: 60,
  maxTradesPerDay: 3,
  overrideAllStrategies: false,
  sessions: ["London", "NY"],
  overlayMode: "detailed",
  overlays: {
    ema: true,
    signals: true,
    slTp: true,
    adx: true,
    atr: true,
  },
};

export const SESSION_OPTIONS = ["London", "NY", "Asia", "Sydney"] as const;
