import type { StopLossMode, TakeProfitMode, TrailMode } from "./types";

export type ExitModeOption<T extends string> = {
  value: T;
  label: string;
  description: string;
  /** When set, option is only shown for that signal type and listed first. */
  signalSpecific?: "ema_crossover";
  badge?: string;
};

/** Stop-loss modes with UI copy. Order is display order. */
export const STOP_LOSS_MODE_OPTIONS: ExitModeOption<StopLossMode>[] = [
  {
    value: "fixed_pips",
    label: "Fixed pips",
    description: "Place the stop a fixed number of pips from the entry price.",
  },
  {
    value: "atr_based",
    label: "ATR-based",
    description:
      "Size the stop as a multiple of Average True Range so distance adapts to current volatility.",
  },
  {
    value: "structure",
    label: "Structure",
    description:
      "Place the stop beyond a recent swing high or low over the lookback window.",
  },
];

/**
 * Take-profit modes with UI copy.
 * Signal-specific options are listed first so helpers can keep them at the top.
 */
export const TAKE_PROFIT_MODE_OPTIONS: ExitModeOption<TakeProfitMode>[] = [
  {
    value: "reverse_crossover",
    label: "Reverse crossover",
    description:
      "Exit when the EMA crossover flips against the open position — closes on the opposite signal.",
    signalSpecific: "ema_crossover",
    badge: "EMA signal",
  },
  {
    value: "fixed_pips",
    label: "Fixed pips",
    description: "Take profit a fixed number of pips from the entry price.",
  },
  {
    value: "rr_ratio",
    label: "R:R ratio",
    description:
      "Set take profit as a multiple of the stop-loss distance (risk/reward).",
  },
  {
    value: "atr_based",
    label: "ATR-based",
    description: "Size take profit as a multiple of Average True Range.",
  },
  {
    value: "trailing_stop",
    label: "Trailing stop",
    description:
      "Trail the exit as price moves in your favor using ATR distance or the slow EMA.",
  },
];

/** Trailing-stop subtypes. Signal-specific options stay first. */
export const TRAIL_MODE_OPTIONS: ExitModeOption<TrailMode>[] = [
  {
    value: "ema_slow",
    label: "Trail EMA Slow",
    description: "Trail the stop along the slow EMA from the crossover signal.",
    signalSpecific: "ema_crossover",
    badge: "EMA signal",
  },
  {
    value: "atr",
    label: "ATR trailing stop",
    description: "Trail a stop a multiple of ATR behind the favorable extreme.",
  },
];

export function stopLossModeOptions(): ExitModeOption<StopLossMode>[] {
  return STOP_LOSS_MODE_OPTIONS;
}

/** Available TP modes; signal-specific options are kept at the top. */
export function takeProfitModeOptions(emaSignalActive: boolean): ExitModeOption<TakeProfitMode>[] {
  return TAKE_PROFIT_MODE_OPTIONS.filter(
    (option) => !option.signalSpecific || (option.signalSpecific === "ema_crossover" && emaSignalActive),
  );
}

/** Available trail modes; signal-specific options are kept at the top. */
export function trailModeOptions(emaSignalActive: boolean): ExitModeOption<TrailMode>[] {
  return TRAIL_MODE_OPTIONS.filter(
    (option) => !option.signalSpecific || (option.signalSpecific === "ema_crossover" && emaSignalActive),
  );
}

export const SIGNAL_CATALOG_SECTIONS = [
  {
    id: "limits",
    label: "Limits",
    signals: [
      {
        type: "monthly_high" as const,
        label: "Monthly High",
        description: "Enter when price breaks the current monthly high.",
      },
      {
        type: "monthly_low" as const,
        label: "Monthly Low",
        description: "Enter when price breaks the current monthly low.",
      },
    ],
  },
  {
    id: "events",
    label: "Events",
    signals: [
      {
        type: "ema_crossover" as const,
        label: "EMA Crossover",
        description: "Fast/slow EMA crossover entry signal.",
      },
    ],
  },
] as const;

export const SIGNAL_CATALOG = SIGNAL_CATALOG_SECTIONS.flatMap((section) => [...section.signals]);

export const FILTER_CATALOG = [
  {
    type: "adx" as const,
    id: "adx",
    label: "ADX filter",
    description:
      "Average Directional Index measures trend strength. Entries are allowed only when ADX is at or above the threshold, so the strategy prefers trending markets over chop.",
  },
  {
    type: "atr" as const,
    id: "atr",
    label: "ATR filter",
    description:
      "Average True Range measures volatility. Entries are allowed only when ATR is at or above the minimum, so the strategy skips unusually quiet markets.",
  },
];

export const INDICATOR_CATALOG = [
  {
    type: "ema" as const,
    label: "EMA",
    description:
      "Exponential Moving Average smooths price with more weight on recent candles. Shorter periods react faster; longer periods track the broader trend. Used for overlays and signals like EMA crossover.",
  },
] as const;

export type SignalCatalogType = (typeof SIGNAL_CATALOG)[number]["type"];
export type FilterCatalogType = (typeof FILTER_CATALOG)[number]["type"];
export type IndicatorCatalogType = (typeof INDICATOR_CATALOG)[number]["type"];

export function findSignalCatalogEntry(type: SignalCatalogType) {
  return SIGNAL_CATALOG.find((item) => item.type === type);
}

export function findFilterCatalogEntry(type: FilterCatalogType) {
  return FILTER_CATALOG.find((item) => item.type === type);
}

export function findIndicatorCatalogEntry(type: IndicatorCatalogType) {
  return INDICATOR_CATALOG.find((item) => item.type === type);
}
