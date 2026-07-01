import type { Trade } from "../api/client";

export type TradeReasonCategory = "signal" | "import" | "exit" | "manual" | "broker" | "other";

export type TradeReasonDisplay = {
  code: string | null;
  label: string | null;
  short: string | null;
  category: TradeReasonCategory | null;
};

type ReasonDefinition = {
  label: string;
  short: string;
  category: TradeReasonCategory;
};

const REASON_REGISTRY: Record<string, ReasonDefinition> = {
  bullish_cross: { label: "Bullish crossover", short: "Bull cross", category: "signal" },
  bearish_cross: { label: "Bearish crossover", short: "Bear cross", category: "signal" },
  ema_crossover: { label: "EMA crossover", short: "EMA cross", category: "signal" },
  oanda_import: { label: "Imported from OANDA", short: "OANDA import", category: "import" },
  random_trade: { label: "Random Trade", short: "Random Trade", category: "other" },
  reverse_crossover: { label: "Reverse crossover", short: "Rev crossover", category: "exit" },
  trail_ema_slow: { label: "Trail stop (EMA slow)", short: "Trail EMA", category: "exit" },
  trail_atr: { label: "Trail stop (ATR)", short: "Trail ATR", category: "exit" },
  manual_close: { label: "Manual close", short: "Manual", category: "manual" },
  broker_closed: { label: "Closed on OANDA", short: "Broker close", category: "broker" },
};

const CATEGORY_LABELS: Record<TradeReasonCategory, string> = {
  signal: "Signal",
  import: "Import",
  exit: "Exit",
  manual: "Manual",
  broker: "Broker",
  other: "Other",
};

function fallbackShort(label: string, maxLength = 19): string {
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength - 1)}…`;
}

export function resolveTradeReason(code: string | null | undefined): TradeReasonDisplay {
  if (!code?.trim()) {
    return { code: null, label: null, short: null, category: null };
  }
  const normalized = code.trim();
  const info = REASON_REGISTRY[normalized];
  if (info) {
    return { code: normalized, label: info.label, short: info.short, category: info.category };
  }
  const label = normalized.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
  return {
    code: normalized,
    label,
    short: fallbackShort(label),
    category: "other",
  };
}

export function reasonCategoryLabel(category: TradeReasonCategory | null | undefined): string {
  if (!category) return "";
  return CATEGORY_LABELS[category] ?? category;
}

function executionReasonCode(trade: Trade): string | null {
  if (trade.execution_reason?.trim()) return trade.execution_reason.trim();
  const metadata = trade.metadata ?? {};
  const explicit = metadata.execution_reason;
  if (typeof explicit === "string" && explicit.trim()) return explicit.trim();
  const analysis = metadata.analysis;
  if (analysis && typeof analysis === "object") {
    const signal = (analysis as Record<string, unknown>).signal;
    if (typeof signal === "string" && signal.trim() && signal !== "none") return signal.trim();
  }
  if (metadata.source === "oanda_sync") return "oanda_import";
  if (typeof metadata.source === "string" && metadata.source.includes("place_random_oanda_trade")) {
    return "random_trade";
  }
  if (trade.strategy_id === "test-script") return "random_trade";
  return null;
}

function reasonCodeForTrade(trade: Trade): string | null {
  if (trade.status === "closed") {
    return trade.close_reason?.trim() || null;
  }
  return executionReasonCode(trade);
}

export function tradeReasonPresentation(trade: Trade): {
  short: string;
  label: string | null;
  category: TradeReasonCategory | null;
} {
  const fromApi = trade.reason_display;
  if (fromApi?.short) {
    return {
      short: fromApi.short,
      label: fromApi.label,
      category: fromApi.category,
    };
  }

  const resolved = resolveTradeReason(reasonCodeForTrade(trade));
  return {
    short: resolved.short ?? "—",
    label: resolved.label,
    category: resolved.category,
  };
}
