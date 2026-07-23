import type { Confirmation, Direction, Timeframe } from "../strategyParams";
import type { SignalCatalogType } from "../strategyParams/catalog";
import { roundUpMinCandles } from "../strategyParams/helpers";
import { SESSION_OPTIONS } from "../marketSessionDefs";

export const STRATEGY_TITLE_MAX = 32;
export const EMA_PERIOD_MIN = 2;
export const EMA_PERIOD_MAX = 100;

export const DEFAULT_EMA_COLORS = ["#3b82f6", "#f59e0b", "#22c55e", "#ef4444", "#a855f7"] as const;

/** Default trading markets (session names from SESSION_OPTIONS). */
export const DEFAULT_MARKET_SESSIONS: string[] = ["London", "NY"];

export type TimeframeComponent = {
  id: string;
  type: "timeframe";
  timeframe: Timeframe;
  minCandles: number;
};

export type AdditionalTimeframesComponent = {
  id: string;
  type: "additional_timeframes";
  timeframes: Timeframe[];
};

/** Unique markets card — any combination of the four main liquidity sessions. */
export type MarketsComponent = {
  id: string;
  type: "markets";
  sessions: string[];
};

export type EmaComponent = {
  id: string;
  type: "ema";
  period: number;
  color: string;
};

export type SignalCombineMode = "and" | "or";

/** Maximum number of signal components in the strategy builder. */
export const MAX_SIGNALS = 5;

export type SignalComponent = {
  id: string;
  type: "signal";
  signalType: SignalCatalogType | "";
  /** Applies to every signal type. */
  direction: Direction;
  /** Applies to every signal type. */
  confirmation: Confirmation;
  /**
   * How this signal combines with the previous one (separator AND/OR).
   * Omitted on the first signal.
   */
  combineWithPrevious?: SignalCombineMode;
  /**
   * When true, this signal is chained (parenthesized) with the previous one.
   * When false, the chain breaks and a new group starts.
   * Omitted on the first signal; defaults to true when a join exists.
   */
  linkedWithPrevious?: boolean;
  /** EMA component id used as the fast leg for ema_crossover. */
  fastEmaId?: string;
  /** EMA component id used as the slow leg for ema_crossover. */
  slowEmaId?: string;
};

export type StrategyBuilderComponent =
  | TimeframeComponent
  | AdditionalTimeframesComponent
  | MarketsComponent
  | EmaComponent
  | SignalComponent;

export type ComponentSection = "timeframes" | "markets" | "indicators" | "signals";

export function clampStrategyTitle(value: string): string {
  return value.slice(0, STRATEGY_TITLE_MAX);
}

export function clampEmaPeriod(value: number): number {
  if (!Number.isFinite(value)) return EMA_PERIOD_MIN;
  return Math.min(EMA_PERIOD_MAX, Math.max(EMA_PERIOD_MIN, Math.round(value)));
}

export function emaLabel(period: number): string {
  return `EMA ${clampEmaPeriod(period)}`;
}

export function nextEmaColor(existing: EmaComponent[]): string {
  const used = new Set(existing.map((item) => item.color.toLowerCase()));
  for (const color of DEFAULT_EMA_COLORS) {
    if (!used.has(color.toLowerCase())) return color;
  }
  return DEFAULT_EMA_COLORS[existing.length % DEFAULT_EMA_COLORS.length];
}

export function createId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

export function createPrimaryTimeframe(
  timeframe: Timeframe = "M15",
  minCandles = 200,
): TimeframeComponent {
  return {
    id: "timeframe_primary",
    type: "timeframe",
    timeframe,
    minCandles: roundUpMinCandles(minCandles),
  };
}

export function createAdditionalTimeframes(
  timeframes: Timeframe[] = [],
): AdditionalTimeframesComponent {
  return {
    id: "additional_timeframes",
    type: "additional_timeframes",
    timeframes: [...timeframes],
  };
}

export function normalizeMarketSessions(sessions: string[] | undefined): string[] {
  const allowed = new Set<string>(SESSION_OPTIONS);
  const seen = new Set<string>();
  const next: string[] = [];
  for (const session of sessions ?? []) {
    if (!allowed.has(session) || seen.has(session)) continue;
    seen.add(session);
    next.push(session);
  }
  // Preserve canonical order from SESSION_OPTIONS.
  return SESSION_OPTIONS.filter((session) => seen.has(session));
}

export function createMarketsComponent(
  sessions: string[] = DEFAULT_MARKET_SESSIONS,
): MarketsComponent {
  return {
    id: "markets_primary",
    type: "markets",
    sessions: normalizeMarketSessions(sessions),
  };
}

export function createEmaComponent(
  period: number,
  color?: string,
  existing: EmaComponent[] = [],
): EmaComponent {
  return {
    id: createId("ema"),
    type: "ema",
    period: clampEmaPeriod(period),
    color: color ?? nextEmaColor(existing),
  };
}

export function createSignalComponent(
  signalType: SignalCatalogType | "" = "",
  options?: {
    id?: string;
    fastEmaId?: string;
    slowEmaId?: string;
    direction?: Direction;
    confirmation?: Confirmation;
    combineWithPrevious?: SignalCombineMode;
    linkedWithPrevious?: boolean;
  },
): SignalComponent {
  return {
    id: options?.id ?? createId("signal"),
    type: "signal",
    signalType,
    direction: options?.direction ?? "both",
    confirmation: options?.confirmation ?? "close",
    combineWithPrevious: options?.combineWithPrevious,
    linkedWithPrevious: options?.linkedWithPrevious,
    fastEmaId: options?.fastEmaId,
    slowEmaId: options?.slowEmaId,
  };
}

export function sectionForComponent(component: StrategyBuilderComponent): ComponentSection {
  if (component.type === "markets") return "markets";
  if (component.type === "ema") return "indicators";
  if (component.type === "signal") return "signals";
  return "timeframes";
}

/**
 * Group by section while preserving relative order within each group.
 * EMAs keep insertion order (never re-sort by period) so period edits stay bound to id.
 */
export function sortComponents(components: StrategyBuilderComponent[]): StrategyBuilderComponent[] {
  const primary = components.filter((c) => c.type === "timeframe");
  const additional = components.filter((c) => c.type === "additional_timeframes");
  const markets = components.filter((c) => c.type === "markets");
  const emas = components.filter((c): c is EmaComponent => c.type === "ema");
  const signals = components.filter((c) => c.type === "signal");
  return [...primary, ...additional, ...markets, ...emas, ...signals];
}

/** Update a single EMA's period by stable component id. */
export function updateEmaPeriod(
  components: StrategyBuilderComponent[],
  emaId: string,
  period: number,
): StrategyBuilderComponent[] {
  return updateComponent(components, emaId, { period: clampEmaPeriod(period) });
}

/** Update a single EMA's color by stable component id. */
export function updateEmaColor(
  components: StrategyBuilderComponent[],
  emaId: string,
  color: string,
): StrategyBuilderComponent[] {
  return updateComponent(components, emaId, { color });
}

export function hasPrimaryTimeframe(components: StrategyBuilderComponent[]): boolean {
  return components.some((c) => c.type === "timeframe");
}

export function hasAdditionalTimeframes(components: StrategyBuilderComponent[]): boolean {
  return components.some((c) => c.type === "additional_timeframes");
}

export function hasMarkets(components: StrategyBuilderComponent[]): boolean {
  return components.some((c) => c.type === "markets");
}

export function hasSignal(components: StrategyBuilderComponent[]): boolean {
  return components.some((c) => c.type === "signal");
}

export function getPrimaryTimeframe(
  components: StrategyBuilderComponent[],
): TimeframeComponent | undefined {
  return components.find((c): c is TimeframeComponent => c.type === "timeframe");
}

export function getAdditionalTimeframes(
  components: StrategyBuilderComponent[],
): AdditionalTimeframesComponent | undefined {
  return components.find((c): c is AdditionalTimeframesComponent => c.type === "additional_timeframes");
}

export function getMarketsComponent(
  components: StrategyBuilderComponent[],
): MarketsComponent | undefined {
  return components.find((c): c is MarketsComponent => c.type === "markets");
}

export function getEmaComponents(components: StrategyBuilderComponent[]): EmaComponent[] {
  return components.filter((c): c is EmaComponent => c.type === "ema");
}

export function getSignalComponents(
  components: StrategyBuilderComponent[],
): SignalComponent[] {
  return components.filter((c): c is SignalComponent => c.type === "signal");
}

/** First signal component (primary for V1 params sync). */
export function getSignalComponent(
  components: StrategyBuilderComponent[],
): SignalComponent | undefined {
  return getSignalComponents(components)[0];
}

export function isEmaPeriodTaken(
  components: StrategyBuilderComponent[],
  period: number,
  excludeId?: string,
): boolean {
  const clamped = clampEmaPeriod(period);
  return getEmaComponents(components).some(
    (ema) => ema.period === clamped && ema.id !== excludeId,
  );
}

export function hasDuplicateEmaPeriods(components: StrategyBuilderComponent[]): boolean {
  const periods = getEmaComponents(components).map((ema) => ema.period);
  return new Set(periods).size !== periods.length;
}

export function nextAvailableEmaPeriod(
  components: StrategyBuilderComponent[],
  preferred = 9,
): number | null {
  const taken = new Set(getEmaComponents(components).map((ema) => ema.period));
  if (!taken.has(clampEmaPeriod(preferred))) return clampEmaPeriod(preferred);
  for (const candidate of [9, 21, 12, 26, 50, 100]) {
    if (!taken.has(candidate)) return candidate;
  }
  for (let period = EMA_PERIOD_MIN; period <= EMA_PERIOD_MAX; period += 1) {
    if (!taken.has(period)) return period;
  }
  return null;
}

export function ensurePrimaryTimeframe(
  components: StrategyBuilderComponent[],
  timeframe: Timeframe = "M15",
  minCandles = 200,
): StrategyBuilderComponent[] {
  if (hasPrimaryTimeframe(components)) return sortComponents(components);
  return sortComponents([createPrimaryTimeframe(timeframe, minCandles), ...components]);
}

export function ensureMarkets(
  components: StrategyBuilderComponent[],
  sessions: string[] = DEFAULT_MARKET_SESSIONS,
): StrategyBuilderComponent[] {
  if (hasMarkets(components)) return sortComponents(components);
  return sortComponents([...components, createMarketsComponent(sessions)]);
}

export function addAdditionalTimeframes(
  components: StrategyBuilderComponent[],
): StrategyBuilderComponent[] {
  if (hasAdditionalTimeframes(components)) return sortComponents(components);
  return sortComponents([...components, createAdditionalTimeframes()]);
}

export function addEmaComponent(
  components: StrategyBuilderComponent[],
  period?: number,
): StrategyBuilderComponent[] {
  const nextPeriod = nextAvailableEmaPeriod(components, period ?? 9);
  if (nextPeriod == null) return sortComponents(components);
  const existing = getEmaComponents(components);
  let next = sortComponents([...components, createEmaComponent(nextPeriod, undefined, existing)]);
  return reconcileCrossoverEmaSelection(next);
}

export function canAddSignal(components: StrategyBuilderComponent[]): boolean {
  return getSignalComponents(components).length < MAX_SIGNALS;
}

export function addSignalComponent(
  components: StrategyBuilderComponent[],
  signalType: SignalCatalogType | "" = "",
): StrategyBuilderComponent[] {
  const existing = getSignalComponents(components);
  if (existing.length >= MAX_SIGNALS) return sortComponents(components);

  const isFirst = existing.length === 0;
  const signal = createSignalComponent(signalType, {
    // Keep a stable primary id for the first signal (V1 params / templates).
    id: isFirst ? "signal_primary" : undefined,
    // Joins live on the incoming (non-primary) signal.
    combineWithPrevious: isFirst ? undefined : "and",
    linkedWithPrevious: isFirst ? undefined : true,
  });
  return reconcileCrossoverEmaSelection(
    normalizeSignalJoins(sortComponents([...components, signal])),
  );
}

/** Update the AND/OR and/or chain link on the separator before `signalId`. */
export function updateSignalJoin(
  components: StrategyBuilderComponent[],
  signalId: string,
  patch: {
    combineWithPrevious?: SignalCombineMode;
    linkedWithPrevious?: boolean;
  },
): StrategyBuilderComponent[] {
  const signals = getSignalComponents(components);
  if (signals[0]?.id === signalId) return sortComponents(components);
  if (!signals.some((signal) => signal.id === signalId)) return sortComponents(components);
  return normalizeSignalJoins(updateComponent(components, signalId, patch));
}

/**
 * Group consecutive signals linked by `linkedWithPrevious`.
 * A broken chain starts a new group (parenthesis boundary).
 */
export function groupLinkedSignals(signals: SignalComponent[]): SignalComponent[][] {
  if (signals.length === 0) return [];
  const groups: SignalComponent[][] = [[signals[0]]];
  for (let index = 1; index < signals.length; index += 1) {
    const signal = signals[index];
    if (signal.linkedWithPrevious === false) {
      groups.push([signal]);
    } else {
      groups[groups.length - 1].push(signal);
    }
  }
  return groups;
}

/**
 * Format signal logic with parenthesis groups from chain links.
 * Example: S1 + S2 - S3 → "(S1 AND S2) AND S3" (operators from each join).
 */
export function formatSignalLogicExpression(
  signals: SignalComponent[],
  labelFor: (signal: SignalComponent, index: number) => string = (_signal, index) =>
    `S${index + 1}`,
): string {
  if (signals.length === 0) return "";
  const groups = groupLinkedSignals(signals);
  let cursor = 0;
  const groupExprs = groups.map((group) => {
    const labels = group.map((signal) => {
      const label = labelFor(signal, cursor);
      cursor += 1;
      return label;
    });
    let inner = labels[0] ?? "";
    for (let index = 1; index < group.length; index += 1) {
      const op = (group[index].combineWithPrevious ?? "and").toUpperCase();
      inner += ` ${op} ${labels[index]}`;
    }
    return group.length > 1 ? `(${inner})` : inner;
  });

  let expression = groupExprs[0] ?? "";
  for (let groupIndex = 1; groupIndex < groups.length; groupIndex += 1) {
    const op = (groups[groupIndex][0]?.combineWithPrevious ?? "and").toUpperCase();
    expression += ` ${op} ${groupExprs[groupIndex]}`;
  }
  return expression;
}

/** Clear join fields on the first signal; ensure defaults on the rest. */
export function normalizeSignalJoins(
  components: StrategyBuilderComponent[],
): StrategyBuilderComponent[] {
  const signals = getSignalComponents(components);
  if (signals.length === 0) return components;
  const primaryId = signals[0].id;
  return components.map((component) => {
    if (component.type !== "signal") return component;
    if (component.id === primaryId) {
      return {
        ...component,
        combineWithPrevious: undefined,
        linkedWithPrevious: undefined,
      };
    }
    return {
      ...component,
      combineWithPrevious: component.combineWithPrevious ?? "and",
      linkedWithPrevious: component.linkedWithPrevious ?? true,
    };
  });
}

export function removeComponent(
  components: StrategyBuilderComponent[],
  id: string,
): StrategyBuilderComponent[] {
  const filtered = components.filter((component) => {
    if (component.id !== id) return true;
    // Primary timeframe and markets cannot be removed.
    return component.type === "timeframe" || component.type === "markets";
  });
  return reconcileCrossoverEmaSelection(normalizeSignalJoins(sortComponents(filtered)));
}

export function updateComponent(
  components: StrategyBuilderComponent[],
  id: string,
  patch: Partial<StrategyBuilderComponent>,
): StrategyBuilderComponent[] {
  const next = components.map((component) => {
    if (component.id !== id) return component;
    if (component.type === "ema" && "period" in patch && typeof patch.period === "number") {
      return {
        ...component,
        ...patch,
        type: "ema" as const,
        period: clampEmaPeriod(patch.period),
      };
    }
    if (component.type === "signal") {
      return {
        ...component,
        ...patch,
        type: "signal" as const,
      } as SignalComponent;
    }
    if (component.type === "markets" && "sessions" in patch && Array.isArray(patch.sessions)) {
      return {
        ...component,
        type: "markets" as const,
        sessions: normalizeMarketSessions(patch.sessions),
      };
    }
    if (
      component.type === "timeframe" &&
      "minCandles" in patch &&
      typeof patch.minCandles === "number"
    ) {
      return {
        ...component,
        ...patch,
        type: "timeframe" as const,
        minCandles: roundUpMinCandles(patch.minCandles),
      };
    }
    return { ...component, ...patch } as StrategyBuilderComponent;
  });
  return reconcileCrossoverEmaSelection(sortComponents(next));
}

/** Keep crossover fast/slow refs valid against current EMA components. */
export function reconcileCrossoverEmaSelection(
  components: StrategyBuilderComponent[],
): StrategyBuilderComponent[] {
  const emas = getEmaComponents(components);
  const emaById = new Map(emas.map((ema) => [ema.id, ema]));
  const emaIds = new Set(emaById.keys());
  let changed = false;

  const next = components.map((component) => {
    if (component.type !== "signal" || component.signalType !== "ema_crossover") {
      return component;
    }

    let fastEmaId =
      component.fastEmaId && emaIds.has(component.fastEmaId) ? component.fastEmaId : undefined;
    let slowEmaId =
      component.slowEmaId && emaIds.has(component.slowEmaId) ? component.slowEmaId : undefined;

    if (!fastEmaId && emas[0]) fastEmaId = emas[0].id;
    if (!slowEmaId && emas.length >= 2) {
      slowEmaId = emas.find((ema) => ema.id !== fastEmaId)?.id;
    } else if (slowEmaId && slowEmaId === fastEmaId) {
      slowEmaId = emas.find((ema) => ema.id !== fastEmaId)?.id;
    }

    // Fast must use the shorter period; swap when the user picks them reversed.
    if (fastEmaId && slowEmaId && fastEmaId !== slowEmaId) {
      const fastPeriod = emaById.get(fastEmaId)?.period;
      const slowPeriod = emaById.get(slowEmaId)?.period;
      if (
        typeof fastPeriod === "number" &&
        typeof slowPeriod === "number" &&
        fastPeriod > slowPeriod
      ) {
        const swappedFast = slowEmaId;
        slowEmaId = fastEmaId;
        fastEmaId = swappedFast;
      }
    }

    if (fastEmaId === component.fastEmaId && slowEmaId === component.slowEmaId) {
      return component;
    }
    changed = true;
    return { ...component, fastEmaId, slowEmaId };
  });

  return sortComponents(changed ? next : components);
}

export function seedCustomComponents(minCandles = 200): StrategyBuilderComponent[] {
  return sortComponents([createPrimaryTimeframe("M15", minCandles), createMarketsComponent()]);
}

export function seedEmaCrossoverComponents(minCandles = 200): StrategyBuilderComponent[] {
  const ema9 = createEmaComponent(9, DEFAULT_EMA_COLORS[0]);
  const ema21 = createEmaComponent(21, DEFAULT_EMA_COLORS[1], [ema9]);
  const signal = createSignalComponent("ema_crossover", {
    id: "signal_primary",
    fastEmaId: ema9.id,
    slowEmaId: ema21.id,
  });
  return sortComponents([
    createPrimaryTimeframe("M15", minCandles),
    createMarketsComponent(),
    ema9,
    ema21,
    signal,
  ]);
}
