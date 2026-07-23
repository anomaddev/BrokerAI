import type {
  Confirmation,
  Direction,
  IndicatorSpec,
  StrategyParamsV1,
  Timeframe,
} from "../strategyParams";
import type { SignalCatalogType } from "../strategyParams/catalog";
import { DEFAULT_EMA_COLORS, DEFAULT_MARKET_SESSIONS } from "./components";
import {
  createEmaComponent,
  createMarketsComponent,
  createPrimaryTimeframe,
  createAdditionalTimeframes,
  createSignalComponent,
  ensureMarkets,
  ensurePrimaryTimeframe,
  getAdditionalTimeframes,
  getEmaComponents,
  getMarketsComponent,
  getPrimaryTimeframe,
  getSignalComponent,
  reconcileCrossoverEmaSelection,
  sortComponents,
  type EmaComponent,
  type StrategyBuilderComponent,
} from "./components";

function emaById(
  components: StrategyBuilderComponent[],
  id: string | undefined,
): EmaComponent | undefined {
  if (!id) return undefined;
  return getEmaComponents(components).find((ema) => ema.id === id);
}

/** Derive fast/slow EMA periods from the signal's selected EMA components. */
export function emaPeriodsFromComponents(components: StrategyBuilderComponent[]): {
  fastEma: number;
  slowEma: number;
  fastEmaId?: string;
  slowEmaId?: string;
  fastColor?: string;
  slowColor?: string;
} {
  const signal = getSignalComponent(components);
  const emas = getEmaComponents(components);
  const fast = emaById(components, signal?.fastEmaId) ?? emas[0];
  const slow =
    emaById(components, signal?.slowEmaId) ??
    emas.find((ema) => ema.id !== fast?.id) ??
    emas[1];

  if (!fast && !slow) return { fastEma: 9, slowEma: 21 };
  if (fast && !slow) {
    return {
      fastEma: fast.period,
      slowEma: Math.min(100, fast.period + 12),
      fastEmaId: fast.id,
      fastColor: fast.color,
    };
  }
  if (!fast && slow) {
    return {
      fastEma: Math.max(2, slow.period - 12),
      slowEma: slow.period,
      slowEmaId: slow.id,
      slowColor: slow.color,
    };
  }

  // If periods are reversed, treat the shorter as fast so saves stay valid.
  if (fast!.period > slow!.period) {
    return {
      fastEma: slow!.period,
      slowEma: fast!.period,
      fastEmaId: slow!.id,
      slowEmaId: fast!.id,
      fastColor: slow!.color,
      slowColor: fast!.color,
    };
  }

  return {
    fastEma: fast!.period,
    slowEma: slow!.period,
    fastEmaId: fast!.id,
    slowEmaId: slow!.id,
    fastColor: fast!.color,
    slowColor: slow!.color,
  };
}

export function applyComponentsToBuilderFields(
  components: StrategyBuilderComponent[],
): {
  timeframe: Timeframe;
  minCandles: number;
  fastEma: number;
  slowEma: number;
  additionalTimeframes: Timeframe[];
  sessions: string[];
  signalType: SignalCatalogType | "";
  direction: Direction;
  confirmation: Confirmation;
} {
  const primary = getPrimaryTimeframe(components);
  const additional = getAdditionalTimeframes(components);
  const markets = getMarketsComponent(components);
  const signal = getSignalComponent(components);
  const { fastEma, slowEma } = emaPeriodsFromComponents(components);
  return {
    timeframe: primary?.timeframe ?? "M15",
    minCandles: primary?.minCandles ?? 200,
    fastEma,
    slowEma,
    additionalTimeframes: additional?.timeframes ?? [],
    sessions: markets?.sessions?.length ? [...markets.sessions] : [...DEFAULT_MARKET_SESSIONS],
    signalType: signal?.signalType ?? "",
    direction: signal?.direction ?? "both",
    confirmation: signal?.confirmation ?? "close",
  };
}

export function indicatorsFromEmaComponents(
  components: StrategyBuilderComponent[],
): Record<string, IndicatorSpec> {
  const emas = getEmaComponents(components);
  const indicators: Record<string, IndicatorSpec> = {};
  for (const ema of emas) {
    indicators[ema.id] = {
      type: "ema",
      period: ema.period,
      source: "close",
      color: ema.color,
    };
  }
  return indicators;
}

export function mergeComponentsIntoParamsV1(
  base: StrategyParamsV1,
  components: StrategyBuilderComponent[],
): StrategyParamsV1 {
  const fields = applyComponentsToBuilderFields(components);
  const signal = getSignalComponent(components);
  const emaIndicators = indicatorsFromEmaComponents(components);
  const periods = emaPeriodsFromComponents(components);

  const preserved: Record<string, IndicatorSpec> = {};
  for (const [key, spec] of Object.entries(base.indicators ?? {})) {
    if (spec.type !== "ema") preserved[key] = spec;
  }

  let nextSignal = base.signal;
  if (signal?.signalType === "ema_crossover" && periods.fastEmaId && periods.slowEmaId) {
    nextSignal = {
      type: "ema_crossover",
      fast_ref: periods.fastEmaId,
      slow_ref: periods.slowEmaId,
      direction: signal.direction,
      confirmation: signal.confirmation,
    };
  } else if (signal?.signalType === "monthly_high" || signal?.signalType === "monthly_low") {
    nextSignal = { type: signal.signalType };
  }

  let nextExits = base.exits;
  if (
    base.exits.take_profit.mode === "trailing_stop" &&
    base.exits.take_profit.trail_mode === "ema_slow" &&
    periods.slowEmaId
  ) {
    nextExits = {
      ...base.exits,
      take_profit: {
        ...base.exits.take_profit,
        trail_ema_ref: periods.slowEmaId,
      },
    };
  }

  return {
    ...base,
    timeframe: fields.timeframe,
    min_candles: fields.minCandles,
    additional_timeframes:
      fields.additionalTimeframes.length > 0 ? fields.additionalTimeframes : undefined,
    indicators: { ...preserved, ...emaIndicators },
    signal: nextSignal,
    exits: nextExits,
    execution: {
      ...base.execution,
      sessions: fields.sessions,
    },
  };
}

export function componentsFromParamsV1(
  params: StrategyParamsV1,
  fallbackMinCandles = 200,
): StrategyBuilderComponent[] {
  const primary = createPrimaryTimeframe(params.timeframe, params.min_candles ?? fallbackMinCandles);
  const additional =
    params.additional_timeframes && params.additional_timeframes.length > 0
      ? [createAdditionalTimeframes(params.additional_timeframes)]
      : [];

  const emaEntries = Object.entries(params.indicators ?? {}).filter(
    ([, spec]) => spec.type === "ema",
  );

  const ordered: EmaComponent[] = [];
  const idByKey = new Map<string, string>();

  for (const [key, spec] of emaEntries) {
    if (spec.type !== "ema") continue;
    if (ordered.some((existing) => existing.period === spec.period)) {
      const existing = ordered.find((item) => item.period === spec.period);
      if (existing) idByKey.set(key, existing.id);
      continue;
    }
    const ema: EmaComponent = {
      id: key.startsWith("ema_") || key === "fast" || key === "slow" ? createEmaComponent(spec.period).id : key,
      type: "ema",
      period: spec.period,
      color: spec.color ?? DEFAULT_EMA_COLORS[ordered.length % DEFAULT_EMA_COLORS.length],
    };
    // Prefer stable generated ids for legacy fast/slow keys; keep custom ids otherwise.
    if (key === "fast" || key === "slow") {
      const created = createEmaComponent(
        spec.period,
        spec.color ?? DEFAULT_EMA_COLORS[ordered.length % DEFAULT_EMA_COLORS.length],
        ordered,
      );
      ordered.push(created);
      idByKey.set(key, created.id);
      continue;
    }
    ordered.push(ema);
    idByKey.set(key, ema.id);
  }

  let fastEmaId: string | undefined;
  let slowEmaId: string | undefined;
  const signalSpec = params.signal;
  if (signalSpec.type === "ema_crossover") {
    const fastRef = signalSpec.fast_ref;
    const slowRef = signalSpec.slow_ref;
    fastEmaId =
      idByKey.get(fastRef) ??
      ordered.find((ema) => ema.id === fastRef)?.id ??
      ordered[0]?.id;
    slowEmaId =
      idByKey.get(slowRef) ??
      ordered.find((ema) => ema.id === slowRef)?.id ??
      ordered.find((ema) => ema.id !== fastEmaId)?.id;
  }

  const direction: Direction =
    signalSpec.type === "ema_crossover" ? signalSpec.direction : "both";
  const confirmation: Confirmation =
    signalSpec.type === "ema_crossover" ? signalSpec.confirmation : "close";

  const signal = signalSpec?.type
    ? [
        createSignalComponent(signalSpec.type as SignalCatalogType, {
          id: "signal_primary",
          fastEmaId,
          slowEmaId,
          direction,
          confirmation,
        }),
      ]
    : [];

  const markets = createMarketsComponent(params.execution?.sessions ?? DEFAULT_MARKET_SESSIONS);

  return reconcileCrossoverEmaSelection(
    ensureMarkets(
      ensurePrimaryTimeframe(
        sortComponents([primary, ...additional, markets, ...ordered, ...signal]),
      ),
    ),
  );
}
