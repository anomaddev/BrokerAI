import type { EmaCrossoverParams } from "./defaults";
import {
  SCHEMA_VERSION,
  TIMEFRAMES,
  roundUpMinCandles,
  type StrategyParamsV1,
  type TakeProfitSpec,
  type Timeframe,
} from "../../../../lib/strategyParams";

function normalizeTimeframe(v1: StrategyParamsV1): Timeframe {
  if (v1.timeframe && TIMEFRAMES.includes(v1.timeframe)) {
    return v1.timeframe;
  }
  return "M15";
}

function takeProfitToApi(
  params: EmaCrossoverParams,
  trailEmaRef = "slow",
): TakeProfitSpec {
  if (params.takeProfitType === "trailing_stop") {
    if (params.trailMode === "ema_slow") {
      return {
        enabled: params.takeProfitEnabled,
        mode: "trailing_stop",
        trail_mode: "ema_slow",
        trail_ema_ref: trailEmaRef,
      };
    }
    return {
      enabled: params.takeProfitEnabled,
      mode: "trailing_stop",
      trail_mode: "atr",
      trail_atr_multiplier: params.trailAtrMultiplier,
    };
  }

  if (params.takeProfitType === "reverse_crossover") {
    return { enabled: params.takeProfitEnabled, mode: "reverse_crossover" };
  }

  return {
    enabled: params.takeProfitEnabled,
    mode: params.takeProfitType,
    risk_reward_ratio: params.riskRewardRatio,
    fixed_pips: params.tpFixedPips,
    atr_multiplier: params.tpAtrMultiplier,
  };
}

function takeProfitFromApi(takeProfit: TakeProfitSpec, params: EmaCrossoverParams): EmaCrossoverParams {
  if (takeProfit.mode === "trailing_stop") {
    return {
      ...params,
      takeProfitType: "trailing_stop",
      trailMode: takeProfit.trail_mode ?? "atr",
      trailAtrMultiplier: takeProfit.trail_atr_multiplier ?? params.trailAtrMultiplier,
    };
  }

  if (takeProfit.mode === "reverse_crossover") {
    return { ...params, takeProfitType: "reverse_crossover" };
  }

  return {
    ...params,
    takeProfitType: takeProfit.mode,
    riskRewardRatio: takeProfit.risk_reward_ratio ?? params.riskRewardRatio,
    tpFixedPips: takeProfit.fixed_pips ?? params.tpFixedPips,
    tpAtrMultiplier: takeProfit.atr_multiplier ?? params.tpAtrMultiplier,
  };
}

export function emaCrossoverParamsToV1(
  params: EmaCrossoverParams,
  sessions?: string[],
  extras?: {
    additionalTimeframes?: Timeframe[];
    fastEmaColor?: string;
    slowEmaColor?: string;
    extraEmas?: { period: number; color: string }[];
  },
): StrategyParamsV1 {
  const indicators: StrategyParamsV1["indicators"] = {
    fast: {
      type: "ema",
      period: params.fastEma,
      source: "close",
      color: extras?.fastEmaColor,
    },
    slow: {
      type: "ema",
      period: params.slowEma,
      source: "close",
      color: extras?.slowEmaColor,
    },
  };
  extras?.extraEmas?.forEach((ema, index) => {
    indicators[`ema_${index + 3}`] = {
      type: "ema",
      period: ema.period,
      source: "close",
      color: ema.color,
    };
  });

  return {
    schema_version: SCHEMA_VERSION,
    timeframe: params.timeframe,
    min_candles: params.minCandles,
    additional_timeframes: (() => {
      const extrasTf = extras?.additionalTimeframes ?? [];
      const needed = new Set(extrasTf);
      if (params.htfBiasEnabled) {
        needed.add(params.htfBiasTimeframe);
      }
      return needed.size > 0 ? ([...needed] as Timeframe[]) : undefined;
    })(),
    indicators,
    signal: {
      type: "ema_crossover",
      fast_ref: "fast",
      slow_ref: "slow",
      direction: params.direction,
      confirmation: params.confirmation,
      approaching: {
        enabled: params.approachingEnabled,
        max_gap_atr: params.approachingMaxGapAtr,
        min_narrow_bars: params.approachingMinNarrowBars,
      },
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
        min_value_jpy: params.minAtrJpy,
      },
      ...(params.htfBiasEnabled
        ? [
            {
              id: "htf_bias",
              type: "htf_bias" as const,
              enabled: true,
              timeframe: params.htfBiasTimeframe,
            },
          ]
        : []),
    ],
    exits: {
      stop_loss: {
        enabled: params.stopLossEnabled,
        mode: params.stopLossType,
        atr_multiplier: params.slAtrMultiplier,
        fixed_pips: params.slFixedPips,
        fixed_pips_jpy: params.slFixedPipsJpy,
        structure_lookback: params.slStructureLookback,
      },
      take_profit: takeProfitToApi(params),
      reverse_crossover: {
        enabled: params.takeProfitType === "reverse_crossover",
        min_bars_after_entry: params.reverseCrossoverMinBarsAfterEntry,
        min_confirmation_bars: params.reverseCrossoverMinConfirmationBars,
        min_separation_atr: params.reverseCrossoverMinSeparationAtr,
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
      priority: params.priority,
      dont_hold_between_sessions: params.dontHoldBetweenSessions,
      dont_hold_between_markets: params.dontHoldBetweenMarkets,
      close_before_market_hours: params.closeBeforeMarketHours,
      no_late_market_trading: params.noLateMarketTrading,
      late_market_hours: params.lateMarketHours,
      post_stop_cooldown_bars: params.postStopCooldownBars,
    },
  };
}

function emaPeriodFromRef(
  indicators: StrategyParamsV1["indicators"],
  ref: string | undefined,
  fallback: number,
): number {
  if (!ref) return fallback;
  const spec = indicators[ref];
  return spec?.type === "ema" ? spec.period : fallback;
}

export function v1ToEmaCrossoverParams(v1: StrategyParamsV1): EmaCrossoverParams {
  const adx = v1.filters.find((f) => f.id === "adx" && f.type === "adx");
  const atr = v1.filters.find((f) => f.id === "atr" && f.type === "atr");
  const htfBias = v1.filters.find((f) => f.type === "htf_bias");
  const approaching =
    v1.signal.type === "ema_crossover" ? v1.signal.approaching : undefined;

  let fastEma = 9;
  let slowEma = 21;
  if (v1.signal.type === "ema_crossover") {
    fastEma = emaPeriodFromRef(v1.indicators, v1.signal.fast_ref, 9);
    slowEma = emaPeriodFromRef(v1.indicators, v1.signal.slow_ref, 21);
  } else {
    fastEma = emaPeriodFromRef(v1.indicators, "fast", 9);
    slowEma = emaPeriodFromRef(v1.indicators, "slow", 21);
  }

  let params: EmaCrossoverParams = {
    enabled: false,
    assignmentMode: "asset_class",
    assetClass: "forex",
    selectedInstruments: [],
    fastEma,
    slowEma,
    timeframe: normalizeTimeframe(v1),
    minCandles: roundUpMinCandles(v1.min_candles ?? 200),
    adxFilter: adx?.type === "adx" ? adx.enabled : true,
    adxPeriod: adx?.type === "adx" ? adx.period : 14,
    adxThreshold: adx?.type === "adx" ? adx.threshold : 25,
    atrFilter: atr?.type === "atr" ? atr.enabled : true,
    atrPeriod: atr?.type === "atr" ? atr.period : 14,
    minAtr: atr?.type === "atr" ? (atr.min_value ?? 0.0008) : 0.0008,
    minAtrJpy: atr?.type === "atr" ? (atr.min_value_jpy ?? 0.05) : 0.05,
    direction: v1.signal.type === "ema_crossover" ? v1.signal.direction : "both",
    confirmation: v1.signal.type === "ema_crossover" ? v1.signal.confirmation : "close",
    stopLossEnabled: v1.exits.stop_loss.enabled ?? true,
    stopLossType: v1.exits.stop_loss.mode,
    slAtrMultiplier: v1.exits.stop_loss.atr_multiplier ?? 1.5,
    slFixedPips: v1.exits.stop_loss.fixed_pips ?? 15,
    slFixedPipsJpy: v1.exits.stop_loss.fixed_pips_jpy ?? 50,
    slStructureLookback: v1.exits.stop_loss.structure_lookback ?? 10,
    takeProfitEnabled: v1.exits.take_profit.enabled ?? true,
    takeProfitType: v1.exits.take_profit.mode,
    riskRewardRatio: v1.exits.take_profit.risk_reward_ratio ?? 2.0,
    tpFixedPips: v1.exits.take_profit.fixed_pips ?? 30,
    tpAtrMultiplier: v1.exits.take_profit.atr_multiplier ?? 2.5,
    trailMode: v1.exits.take_profit.trail_mode ?? "atr",
    trailAtrMultiplier: v1.exits.take_profit.trail_atr_multiplier ?? 1.0,
    reverseCrossoverEnabled:
      v1.exits.take_profit.mode === "reverse_crossover"
        ? true
        : (v1.exits.reverse_crossover?.enabled ?? false),
    reverseCrossoverMinBarsAfterEntry: v1.exits.reverse_crossover?.min_bars_after_entry ?? 6,
    reverseCrossoverMinConfirmationBars: v1.exits.reverse_crossover?.min_confirmation_bars ?? 2,
    reverseCrossoverMinSeparationAtr: v1.exits.reverse_crossover?.min_separation_atr ?? 0.2,
    approachingEnabled: approaching?.enabled ?? true,
    approachingMaxGapAtr: approaching?.max_gap_atr ?? 0.5,
    approachingMinNarrowBars: approaching?.min_narrow_bars ?? 2,
    postStopCooldownBars: v1.execution.post_stop_cooldown_bars ?? 0,
    htfBiasEnabled: Boolean(htfBias?.enabled),
    htfBiasTimeframe:
      htfBias && "timeframe" in htfBias && (htfBias.timeframe === "H1" || htfBias.timeframe === "H4")
        ? htfBias.timeframe
        : "H4",
    riskPerTrade: v1.risk.risk_per_trade_pct,
    minConfidence: v1.execution.min_confidence,
    maxTradesPerDay: v1.risk.max_trades_per_day,
    overrideAllStrategies: v1.execution.override_all_strategies ?? false,
    priority: v1.execution.priority ?? 50,
    sessions: [...v1.execution.sessions],
    dontHoldBetweenSessions: v1.execution.dont_hold_between_sessions ?? true,
    dontHoldBetweenMarkets: v1.execution.dont_hold_between_markets ?? true,
    closeBeforeMarketHours: v1.execution.close_before_market_hours ?? 2,
    noLateMarketTrading: v1.execution.no_late_market_trading ?? true,
    lateMarketHours: v1.execution.late_market_hours ?? 2,
    overlayMode: "detailed",
    overlays: {
      ema: true,
      signals: true,
      slTp: true,
      adx: adx?.type === "adx" ? adx.enabled : true,
      atr: atr?.type === "atr" ? atr.enabled : true,
    },
  };

  params = takeProfitFromApi(v1.exits.take_profit, params);
  return params;
}

export const emaCrossoverParamsToApi = emaCrossoverParamsToV1;
