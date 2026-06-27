import type { EmaCrossoverParams } from "./defaults";
import { SCHEMA_VERSION, TIMEFRAMES, type StrategyParamsV1, type Timeframe } from "../../../../lib/strategyParams";

function normalizeTimeframe(v1: StrategyParamsV1 & { timeframes?: Timeframe[] }): Timeframe {
  if (v1.timeframe && TIMEFRAMES.includes(v1.timeframe)) {
    return v1.timeframe;
  }
  if (v1.timeframes?.length) {
    const match = v1.timeframes.find((tf): tf is Timeframe => TIMEFRAMES.includes(tf));
    if (match) return match;
  }
  return "M15";
}

export function emaCrossoverParamsToV1(
  params: EmaCrossoverParams,
  sessions?: string[],
): StrategyParamsV1 {
  return {
    schema_version: SCHEMA_VERSION,
    timeframe: params.timeframe,
    indicators: {
      fast: { type: "ema", period: params.fastEma, source: "close" },
      slow: { type: "ema", period: params.slowEma, source: "close" },
    },
    signal: {
      type: "ema_crossover",
      fast_ref: "fast",
      slow_ref: "slow",
      direction: params.direction,
      confirmation: params.confirmation,
    },
    filters: [
      {
        id: "adx",
        type: "adx",
        enabled: params.adxFilter,
        period: params.adxPeriod,
        threshold: params.adxThreshold,
        compare: "gte",
      },
      {
        id: "atr",
        type: "atr",
        enabled: params.atrFilter,
        period: params.atrPeriod,
        min_value: params.minAtr,
      },
    ],
    exits: {
      stop_loss: {
        mode: params.stopLossType,
        atr_multiplier: params.slAtrMultiplier,
        fixed_pips: params.slFixedPips,
        structure_lookback: params.slStructureLookback,
      },
      take_profit: {
        mode: params.takeProfitType,
        risk_reward_ratio: params.riskRewardRatio,
        fixed_pips: params.tpFixedPips,
        atr_multiplier: params.tpAtrMultiplier,
      },
      trailing: {
        enabled: params.trailingStop,
        atr_multiplier: params.trailAtrMultiplier,
      },
    },
    risk: {
      risk_per_trade_pct: params.riskPerTrade,
      max_trades_per_day: params.maxTradesPerDay,
    },
    execution: {
      sessions: sessions ?? [...params.sessions],
      min_confidence: params.minConfidence,
      override_all_strategies: params.overrideAllStrategies,
    },
  };
}

export function v1ToEmaCrossoverParams(v1: StrategyParamsV1): EmaCrossoverParams {
  const fast = v1.indicators.fast;
  const slow = v1.indicators.slow;
  const adx = v1.filters.find((f) => f.id === "adx" && f.type === "adx");
  const atr = v1.filters.find((f) => f.id === "atr" && f.type === "atr");

  return {
    enabled: false,
    assignmentMode: "asset_class",
    assetClass: "forex",
    selectedInstruments: [],
    fastEma: fast?.type === "ema" ? fast.period : 9,
    slowEma: slow?.type === "ema" ? slow.period : 21,
    timeframe: normalizeTimeframe(v1),
    adxFilter: adx?.type === "adx" ? adx.enabled : true,
    adxPeriod: adx?.type === "adx" ? adx.period : 14,
    adxThreshold: adx?.type === "adx" ? adx.threshold : 25,
    atrFilter: atr?.type === "atr" ? atr.enabled : true,
    atrPeriod: atr?.type === "atr" ? atr.period : 14,
    minAtr: atr?.type === "atr" ? (atr.min_value ?? 0.0008) : 0.0008,
    direction: v1.signal.direction,
    confirmation: v1.signal.confirmation,
    stopLossType: v1.exits.stop_loss.mode,
    slAtrMultiplier: v1.exits.stop_loss.atr_multiplier ?? 1.5,
    slFixedPips: v1.exits.stop_loss.fixed_pips ?? 15,
    slStructureLookback: v1.exits.stop_loss.structure_lookback ?? 10,
    takeProfitType: v1.exits.take_profit.mode,
    riskRewardRatio: v1.exits.take_profit.risk_reward_ratio ?? 2.0,
    tpFixedPips: v1.exits.take_profit.fixed_pips ?? 30,
    tpAtrMultiplier: v1.exits.take_profit.atr_multiplier ?? 2.5,
    trailingStop: v1.exits.trailing.enabled,
    trailAtrMultiplier: v1.exits.trailing.atr_multiplier,
    riskPerTrade: v1.risk.risk_per_trade_pct,
    minConfidence: v1.execution.min_confidence,
    maxTradesPerDay: v1.risk.max_trades_per_day,
    overrideAllStrategies: v1.execution.override_all_strategies ?? false,
    sessions: [...v1.execution.sessions],
    overlayMode: "standard",
    overlays: { ema: true, signals: true, slTp: true, adx: false, atr: false },
  };
}

/** @deprecated Use emaCrossoverParamsToV1 */
export function emaCrossoverBuilderParamsToApi(params: EmaCrossoverParams): StrategyParamsV1 {
  return emaCrossoverParamsToV1(params);
}
