import type { BacktestAction } from "../../api/client";
import { parseAppInstant } from "../formatTime";

export type BacktestChartMarkerRole = "entry" | "exit" | "skipped" | "signal";

export type BacktestChartMarker = {
  id: string;
  sequence: number;
  time: number;
  price: number | null;
  direction: "long" | "short";
  role: BacktestChartMarkerRole;
  label: string;
  kind: string;
};

function toUnixSeconds(value: string | null | undefined): number | null {
  const date = parseAppInstant(value);
  if (!date) return null;
  return Math.floor(date.getTime() / 1000);
}

function metaNumber(meta: Record<string, unknown> | null | undefined, key: string): number | null {
  const raw = meta?.[key];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function metaDirection(
  meta: Record<string, unknown> | null | undefined,
  message: string,
): "long" | "short" {
  const raw = String(meta?.direction || "").toLowerCase();
  if (raw === "long" || raw === "bullish" || raw === "buy") return "long";
  if (raw === "short" || raw === "bearish" || raw === "sell") return "short";
  const lower = message.toLowerCase();
  if (lower.includes("long") || lower.includes("buy") || lower.includes("bull")) return "long";
  if (lower.includes("short") || lower.includes("sell") || lower.includes("bear")) return "short";
  return "long";
}

export function isExecutedSignal(action: BacktestAction): boolean {
  return action.message.toLowerCase().includes("executing trade");
}

export function isSkippedSignal(action: BacktestAction): boolean {
  if (action.kind === "filter_fail") return true;
  if (action.kind !== "signal") return false;
  return !isExecutedSignal(action);
}

function exitLabel(kind: string, meta: Record<string, unknown> | null | undefined): string {
  if (kind === "sl") return "SL";
  if (kind === "tp") return "TP";
  const reason = String(meta?.reason || "").toLowerCase();
  if (reason.includes("stop")) return "SL";
  if (reason.includes("take") || reason.includes("tp")) return "TP";
  return "EXIT";
}

export type BacktestChartMarkerOptions = {
  /** Include FILTER / SKIP markers. Default false — they overwhelm multi-month charts. */
  includeSkipped?: boolean;
  /** Include executed SIGNAL markers (normally omitted; the entry fill represents the trade). */
  includeExecutedSignals?: boolean;
};

/**
 * Convert backtest action rows into chart markers.
 *
 * Default chart set is fills only (entry / exit / SL / TP). Skipped signals are
 * omitted unless ``includeSkipped`` is true, or the caller filters for a selected
 * skipped action separately.
 */
export function backtestActionsToChartMarkers(
  actions: BacktestAction[],
  options: BacktestChartMarkerOptions = {},
): BacktestChartMarker[] {
  const includeSkipped = Boolean(options.includeSkipped);
  const includeExecutedSignals = Boolean(options.includeExecutedSignals);
  const markers: BacktestChartMarker[] = [];

  for (const action of actions) {
    const time = toUnixSeconds(action.bar_time);
    if (time == null) continue;
    const meta = action.meta ?? null;
    const direction = metaDirection(meta, action.message);
    const price = metaNumber(meta, "price");
    const kind = action.kind.trim().toLowerCase();

    if (kind === "entry" || kind === "open") {
      markers.push({
        id: `entry-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "entry",
        label: direction === "long" ? "LONG" : "SHORT",
        kind,
      });
      continue;
    }

    if (kind === "exit" || kind === "close" || kind === "sl" || kind === "tp") {
      markers.push({
        id: `exit-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "exit",
        label: exitLabel(kind, meta),
        kind,
      });
      continue;
    }

    if (kind === "signal" && isExecutedSignal(action)) {
      if (includeExecutedSignals) {
        markers.push({
          id: `signal-${action.sequence}`,
          sequence: action.sequence,
          time,
          price,
          direction,
          role: "signal",
          label: "SIGNAL",
          kind,
        });
      }
      continue;
    }

    if (includeSkipped && isSkippedSignal(action)) {
      markers.push({
        id: `skip-${action.sequence}`,
        sequence: action.sequence,
        time,
        price,
        direction,
        role: "skipped",
        label: kind === "filter_fail" ? "FILTER" : "SKIP",
        kind,
      });
    }
  }

  return markers;
}

/**
 * Build marker(s) for selected action(s) so step-through / group review can highlight
 * non-fill events (executed signals, skips, filter fails) that are omitted by default.
 */
export function backtestActionToSelectedMarker(
  action: BacktestAction | null | undefined,
): BacktestChartMarker | null {
  if (!action) return null;
  const markers = backtestActionsToChartMarkers([action], {
    includeSkipped: true,
    includeExecutedSignals: true,
  });
  return markers[0] ?? null;
}

/** Merge fill markers with temporary markers for the currently selected sequences. */
export function mergeSelectedActionMarkers(
  fillMarkers: BacktestChartMarker[],
  selectedActions: BacktestAction[],
): BacktestChartMarker[] {
  const bySequence = new Map<number, BacktestChartMarker>();
  for (const marker of fillMarkers) {
    bySequence.set(marker.sequence, marker);
  }
  for (const action of selectedActions) {
    if (bySequence.has(action.sequence)) continue;
    const selected = backtestActionToSelectedMarker(action);
    if (selected) bySequence.set(selected.sequence, selected);
  }
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
}
