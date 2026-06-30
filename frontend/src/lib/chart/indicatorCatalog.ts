import type { IndicatorSpec, PriceSource } from "../strategyParams";

export const INDICATOR_CATALOG_TYPES = ["ema", "sma", "rsi", "adx"] as const;
export type IndicatorCatalogType = (typeof INDICATOR_CATALOG_TYPES)[number];

export type AdxOverlaySpec = {
  type: "adx";
  period: number;
};

export type OverlayIndicatorSpec = IndicatorSpec | AdxOverlaySpec;

export type IndicatorCatalogEntry = {
  type: IndicatorCatalogType;
  label: string;
  description: string;
  defaultSpec: OverlayIndicatorSpec;
  defaultColor: string;
};

export const INDICATOR_COLORS = [
  "#3b82f6",
  "#f59e0b",
  "#22c55e",
  "#a78bfa",
  "#ec4899",
  "#14b8a6",
];

export const INDICATOR_CATALOG: IndicatorCatalogEntry[] = [
  {
    type: "ema",
    label: "EMA",
    description: "Exponential moving average on price.",
    defaultSpec: { type: "ema", period: 9, source: "close" },
    defaultColor: INDICATOR_COLORS[0],
  },
  {
    type: "sma",
    label: "SMA",
    description: "Simple moving average on price.",
    defaultSpec: { type: "sma", period: 20, source: "close" },
    defaultColor: INDICATOR_COLORS[1],
  },
  {
    type: "rsi",
    label: "RSI",
    description: "Relative strength index oscillator.",
    defaultSpec: { type: "rsi", period: 14, source: "close" },
    defaultColor: INDICATOR_COLORS[5],
  },
  {
    type: "adx",
    label: "ADX",
    description: "Average directional index trend strength.",
    defaultSpec: { type: "adx", period: 14 },
    defaultColor: INDICATOR_COLORS[3],
  },
];

export function findIndicatorCatalogEntry(type: IndicatorCatalogType): IndicatorCatalogEntry {
  const entry = INDICATOR_CATALOG.find((item) => item.type === type);
  if (!entry) throw new Error(`Unknown indicator type: ${type}`);
  return entry;
}

export function overlayIndicatorLabel(
  spec: OverlayIndicatorSpec,
  ref?: string,
): string {
  switch (spec.type) {
    case "ema":
      return `EMA ${spec.period}`;
    case "sma":
      return `SMA ${spec.period}`;
    case "rsi":
      return `RSI ${spec.period}`;
    case "adx":
      return `ADX ${spec.period}`;
    default:
      return ref ?? "Indicator";
  }
}

export function overlayIndicatorPane(
  spec: OverlayIndicatorSpec,
): "price" | "rsi" | "adx" {
  switch (spec.type) {
    case "rsi":
      return "rsi";
    case "adx":
      return "adx";
    default:
      return "price";
  }
}

export function isAdxSpec(spec: OverlayIndicatorSpec): spec is AdxOverlaySpec {
  return spec.type === "adx";
}

export function priceSourceOptions(): { value: PriceSource; label: string }[] {
  return [
    { value: "close", label: "Close" },
    { value: "open", label: "Open" },
    { value: "high", label: "High" },
    { value: "low", label: "Low" },
    { value: "hl2", label: "HL2" },
    { value: "hlc3", label: "HLC3" },
    { value: "ohlc4", label: "OHLC4" },
  ];
}
