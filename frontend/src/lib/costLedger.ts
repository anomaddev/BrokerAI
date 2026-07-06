import type { CostLedgerEntry } from "../api/client";

const CATEGORY_LABELS: Record<string, string> = {
  llm: "LLM",
  data_api: "Data API",
  hosting: "Hosting",
};

export function costCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatCostUsd(amount: number | null | undefined): string {
  if (amount == null || Number.isNaN(amount)) {
    return "—";
  }
  const abs = Math.abs(amount);
  if (abs === 0) return "$0.00";
  if (abs < 0.01) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 6,
    }).format(amount);
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(amount);
}

export function costEntryDetail(entry: CostLedgerEntry): string | null {
  const meta = entry.metadata ?? {};
  const parts: string[] = [];

  const model = meta.model_name;
  if (typeof model === "string" && model.trim()) {
    parts.push(model.trim());
  }

  const input = meta.input_tokens;
  const output = meta.output_tokens;
  if (typeof input === "number" || typeof output === "number") {
    const inTok = typeof input === "number" ? input : 0;
    const outTok = typeof output === "number" ? output : 0;
    parts.push(`${inTok.toLocaleString()} in / ${outTok.toLocaleString()} out`);
  }

  if (meta.estimated === true) {
    parts.push("estimated");
  }

  if (meta.billable === false) {
    parts.push("non-billable");
  }

  return parts.length > 0 ? parts.join(" · ") : null;
}

export function sourceLabel(source: string | null | undefined): string {
  if (!source) return "—";
  const labels: Record<string, string> = {
    daily_report: "Daily report",
    weekly_report: "Weekly report",
    connection_test: "Connection test",
  };
  return labels[source] ?? source.replace(/_/g, " ");
}

export type CostSummaryPeriod = "today" | "7d" | "30d" | "all";

export function summaryPeriodRange(period: CostSummaryPeriod): { since?: string; until?: string } {
  if (period === "all") {
    return {};
  }

  const now = new Date();
  const until = now.toISOString();
  const start = new Date(now);

  if (period === "today") {
    start.setUTCHours(0, 0, 0, 0);
  } else if (period === "7d") {
    start.setUTCDate(start.getUTCDate() - 7);
  } else if (period === "30d") {
    start.setUTCDate(start.getUTCDate() - 30);
  }

  return { since: start.toISOString(), until };
}

export const SUMMARY_PERIOD_OPTIONS: { id: CostSummaryPeriod; label: string }[] = [
  { id: "today", label: "Today" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "all", label: "All time" },
];
