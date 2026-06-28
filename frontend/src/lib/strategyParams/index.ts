export {
  SCHEMA_VERSION,
  TIMEFRAMES,
  TIMEFRAME_LABELS,
  TIMEFRAME_OPTIONS,
  DIRECTIONS,
  CONFIRMATIONS,
  PRICE_SOURCES,
  STOP_LOSS_MODES,
  TAKE_PROFIT_MODES,
  FILTER_COMPARE,
} from "./types";

export type {
  Timeframe,
  Direction,
  Confirmation,
  PriceSource,
  StopLossMode,
  TakeProfitMode,
  TrailMode,
  FilterCompare,
  IndicatorSpec,
  EmaIndicatorSpec,
  SmaIndicatorSpec,
  RsiIndicatorSpec,
  FilterSpec,
  AdxFilterSpec,
  AtrFilterSpec,
  RsiFilterSpec,
  CustomFilterSpec,
  EmaCrossoverSignalSpec,
  MonthlyHighSignalSpec,
  MonthlyLowSignalSpec,
  SignalSpec,
  StopLossSpec,
  TakeProfitSpec,
  ExitsSpec,
  RiskSpec,
  ExecutionSpec,
  StrategyParamsV1,
  StrategyPresetMeta,
} from "./types";

export { SIGNAL_CATALOG, SIGNAL_CATALOG_SECTIONS, FILTER_CATALOG, findSignalCatalogEntry } from "./catalog";
export type { SignalCatalogType, FilterCatalogType } from "./catalog";
export { computeBuilderMinCandles, defaultAdxFilter, defaultAtrFilter } from "./helpers";
