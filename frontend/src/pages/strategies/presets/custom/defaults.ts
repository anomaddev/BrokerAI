import type { EmaCrossoverParams } from "../emaCrossover/defaults";
import { DEFAULT_EMA_CROSSOVER_PARAMS, SESSION_OPTIONS } from "../emaCrossover/defaults";
import { emaCrossoverParamsToV1, v1ToEmaCrossoverParams } from "../emaCrossover/apiParams";
import type { SignalCatalogType } from "../../../../lib/strategyParams/catalog";
import type { StrategyParamsV1 } from "../../../../lib/strategyParams";

export type CustomBuilderParams = EmaCrossoverParams & {
  signalType: SignalCatalogType | "";
  hasAdx: boolean;
  hasAtr: boolean;
};

export const DEFAULT_CUSTOM_BUILDER_PARAMS: CustomBuilderParams = {
  ...DEFAULT_EMA_CROSSOVER_PARAMS,
  signalType: "",
  hasAdx: false,
  hasAtr: false,
  adxFilter: true,
  atrFilter: true,
  stopLossEnabled: false,
  takeProfitEnabled: false,
};

function buildFilters(params: CustomBuilderParams) {
  return [
    ...(params.hasAdx
      ? [
          {
            id: "adx",
            type: "adx" as const,
            enabled: params.adxFilter,
            period: params.adxPeriod,
            threshold: params.adxThreshold,
            compare: "gte" as const,
          },
        ]
      : []),
    ...(params.hasAtr
      ? [
          {
            id: "atr",
            type: "atr" as const,
            enabled: params.atrFilter,
            period: params.atrPeriod,
            min_value: params.minAtr,
          },
        ]
      : []),
  ];
}

export function customBuilderParamsToV1(params: CustomBuilderParams, sessions?: string[]): StrategyParamsV1 {
  if (!params.signalType) {
    throw new Error("A signal type is required");
  }

  const base = emaCrossoverParamsToV1(
    {
      ...params,
      adxFilter: params.hasAdx ? params.adxFilter : false,
      atrFilter: params.hasAtr ? params.atrFilter : false,
    },
    sessions,
  );

  if (params.signalType === "ema_crossover") {
    return { ...base, filters: buildFilters(params) };
  }

  return {
    ...base,
    indicators: {},
    signal: { type: params.signalType },
    filters: buildFilters(params),
  };
}

export function v1ToCustomBuilderParams(v1: StrategyParamsV1): CustomBuilderParams {
  const adx = v1.filters.find((f) => f.id === "adx" && f.type === "adx");
  const atr = v1.filters.find((f) => f.id === "atr" && f.type === "atr");
  const signalType = (v1.signal?.type ?? "") as SignalCatalogType | "";

  if (signalType === "ema_crossover") {
    const ema = v1ToEmaCrossoverParams(v1);
    return {
      ...ema,
      signalType: "ema_crossover",
      hasAdx: Boolean(adx),
      hasAtr: Boolean(atr),
      adxFilter: adx?.type === "adx" ? adx.enabled : true,
      adxPeriod: adx?.type === "adx" ? adx.period : 14,
      adxThreshold: adx?.type === "adx" ? adx.threshold : 25,
      atrFilter: atr?.type === "atr" ? atr.enabled : true,
      atrPeriod: atr?.type === "atr" ? atr.period : 14,
      minAtr: atr?.type === "atr" ? (atr.min_value ?? 0.0008) : 0.0008,
      overlays: {
        ...ema.overlays,
        adx: Boolean(adx) && (adx?.type === "adx" ? adx.enabled : true),
        atr: Boolean(atr) && (atr?.type === "atr" ? atr.enabled : true),
      },
    };
  }

  const ema = v1ToEmaCrossoverParams({
    ...v1,
    signal: {
      type: "ema_crossover",
      fast_ref: "fast",
      slow_ref: "slow",
      direction: "both",
      confirmation: "close",
    },
    indicators: {
      fast: { type: "ema", period: 9, source: "close" },
      slow: { type: "ema", period: 21, source: "close" },
    },
  });

  return {
    ...ema,
    signalType,
    hasAdx: Boolean(adx),
    hasAtr: Boolean(atr),
    adxFilter: adx?.type === "adx" ? adx.enabled : true,
    adxPeriod: adx?.type === "adx" ? adx.period : 14,
    adxThreshold: adx?.type === "adx" ? adx.threshold : 25,
    atrFilter: atr?.type === "atr" ? atr.enabled : true,
    atrPeriod: atr?.type === "atr" ? atr.period : 14,
    minAtr: atr?.type === "atr" ? (atr.min_value ?? 0.0008) : 0.0008,
    overlays: {
      ...ema.overlays,
      adx: Boolean(adx) && (adx?.type === "adx" ? adx.enabled : true),
      atr: Boolean(atr) && (atr?.type === "atr" ? atr.enabled : true),
    },
  };
}

export { SESSION_OPTIONS };
