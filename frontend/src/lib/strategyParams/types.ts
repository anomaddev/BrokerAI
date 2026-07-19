export const SCHEMA_VERSION = 1 as const;

export const TIMEFRAMES = [
  "M1",
  "M2",
  "M3",
  "M4",
  "M5",
  "M10",
  "M15",
  "M30",
  "H1",
  "H2",
  "H3",
  "H4",
  "H6",
  "H8",
  "H12",
  "D1",
  "W1",
  "MN",
] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];

export const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  M1: "1m",
  M2: "2m",
  M3: "3m",
  M4: "4m",
  M5: "5m",
  M10: "10m",
  M15: "15m",
  M30: "30m",
  H1: "1H",
  H2: "2H",
  H3: "3H",
  H4: "4H",
  H6: "6H",
  H8: "8H",
  H12: "12H",
  D1: "1D",
  W1: "1W",
  MN: "1M",
};

export const TIMEFRAME_OPTIONS = TIMEFRAMES.map((value) => ({
  value,
  label: TIMEFRAME_LABELS[value],
}));

export const DIRECTIONS = ["long", "short", "both"] as const;
export type Direction = (typeof DIRECTIONS)[number];

export const CONFIRMATIONS = ["close", "pullback", "aggressive"] as const;
export type Confirmation = (typeof CONFIRMATIONS)[number];

export const PRICE_SOURCES = ["close", "open", "high", "low", "hl2", "hlc3", "ohlc4"] as const;
export type PriceSource = (typeof PRICE_SOURCES)[number];

export const STOP_LOSS_MODES = ["fixed_pips", "atr_based", "structure"] as const;
export type StopLossMode = (typeof STOP_LOSS_MODES)[number];

export const TAKE_PROFIT_MODES = [
  "fixed_pips",
  "rr_ratio",
  "atr_based",
  "reverse_crossover",
  "trailing_stop",
] as const;
export type TakeProfitMode = (typeof TAKE_PROFIT_MODES)[number];

export const TRAIL_MODES = ["ema_slow", "atr"] as const;
export type TrailMode = (typeof TRAIL_MODES)[number];

export const FILTER_COMPARE = ["gte", "lte", "gt", "lt", "eq"] as const;
export type FilterCompare = (typeof FILTER_COMPARE)[number];

export type EmaIndicatorSpec = {
  type: "ema";
  period: number;
  source?: PriceSource;
  /** Chart display color (UI-only; ignored by signal engine). */
  color?: string;
};

export type SmaIndicatorSpec = {
  type: "sma";
  period: number;
  source?: PriceSource;
};

export type RsiIndicatorSpec = {
  type: "rsi";
  period: number;
  source?: PriceSource;
  overbought?: number;
  oversold?: number;
};

export type IndicatorSpec = EmaIndicatorSpec | SmaIndicatorSpec | RsiIndicatorSpec;

export type AdxFilterSpec = {
  id: string;
  type: "adx";
  enabled: boolean;
  period: number;
  threshold: number;
  compare?: FilterCompare;
};

export type AtrFilterSpec = {
  id: string;
  type: "atr";
  enabled: boolean;
  period: number;
  min_value?: number;
  max_value?: number;
};

export type RsiFilterSpec = {
  id: string;
  type: "rsi";
  enabled: boolean;
  period: number;
  min_value?: number;
  max_value?: number;
};

export type CustomFilterSpec = {
  id: string;
  type: "custom";
  enabled: boolean;
  expression: string;
};

export type FilterSpec = AdxFilterSpec | AtrFilterSpec | RsiFilterSpec | CustomFilterSpec;

export type MonthlyHighSignalSpec = {
  type: "monthly_high";
};

export type MonthlyLowSignalSpec = {
  type: "monthly_low";
};

export type EmaCrossoverApproachingSpec = {
  enabled: boolean;
  max_gap_atr: number;
  min_narrow_bars: number;
};

export type EmaCrossoverSignalSpec = {
  type: "ema_crossover";
  fast_ref: string;
  slow_ref: string;
  direction: Direction;
  confirmation: Confirmation;
  /** Optional approaching-crossover assist; defaults applied server-side when omitted. */
  approaching?: EmaCrossoverApproachingSpec;
};

export type SignalSpec = EmaCrossoverSignalSpec | MonthlyHighSignalSpec | MonthlyLowSignalSpec;

export type StopLossSpec = {
  /** When false, no stop-loss order is placed. Defaults to true when omitted. */
  enabled?: boolean;
  mode: StopLossMode;
  atr_multiplier?: number;
  fixed_pips?: number;
  structure_lookback?: number;
};

export type TakeProfitSpec = {
  /** When false, no take-profit / trailing exit is used. Defaults to true when omitted. */
  enabled?: boolean;
  mode: TakeProfitMode;
  risk_reward_ratio?: number;
  fixed_pips?: number;
  atr_multiplier?: number;
  trail_mode?: TrailMode;
  trail_atr_multiplier?: number;
  trail_ema_ref?: string;
};

export type ExitsSpec = {
  stop_loss: StopLossSpec;
  take_profit: TakeProfitSpec;
};

export type RiskSpec = {
  risk_per_trade_pct: number;
  max_trades_per_day: number;
};

export type ExecutionSpec = {
  sessions: string[];
  min_confidence: number;
  override_all_strategies?: boolean;
  priority?: number;
};

export type StrategyParamsV1 = {
  schema_version: typeof SCHEMA_VERSION;
  timeframe: Timeframe;
  min_candles?: number;
  /** Extra candle timeframes to fetch (UI/component model; optional). */
  additional_timeframes?: Timeframe[];
  indicators: Record<string, IndicatorSpec>;
  signal: SignalSpec;
  filters: FilterSpec[];
  exits: ExitsSpec;
  risk: RiskSpec;
  execution: ExecutionSpec;
};

export type StrategyPresetMeta = {
  id: string;
  name: string;
  description: string;
  asset_classes: string[];
  route: string;
  signal_type: string;
  locked?: boolean;
  default_params: StrategyParamsV1;
  param_schema: Record<string, unknown>;
};
