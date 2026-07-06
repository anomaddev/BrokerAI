import { isKnownTimeframe, timeframeToMs, type Timeframe } from "./candleSchedule";
import {
  formatAppInstant,
  parseAppInstant,
  type AppInstantStyle,
  type TimeFormatOptions,
} from "./formatTime";

/** OANDA stores bar open instants; a 2:00 M15 bar closes at 2:15. */
export function candleCloseMsFromOpenMs(openMs: number, timeframe: Timeframe): number {
  return openMs + timeframeToMs(timeframe);
}

export function candleCloseFromOpen(
  openValue: string | number | Date,
  timeframe: Timeframe,
): Date | null {
  const open = parseAppInstant(openValue);
  if (!open) return null;
  return new Date(candleCloseMsFromOpenMs(open.getTime(), timeframe));
}

/** e.g. ``Jul 6, 2026, 2:00 AM · closes 2:15 AM EDT`` */
export function formatCandleOpenCloseLabel(
  openValue: string | number | Date,
  timeframe: Timeframe,
  options: TimeFormatOptions,
  style: AppInstantStyle = "short",
): string | null {
  const open = parseAppInstant(openValue);
  const close = candleCloseFromOpen(openValue, timeframe);
  if (!open || !close) {
    return typeof openValue === "string" ? formatAppInstant(openValue, options, style) : null;
  }
  const openLabel = formatAppInstant(open, options, style);
  const closeLabel = formatAppInstant(close, options, style);
  return `${openLabel} · closes ${closeLabel}`;
}

export function resolveKnownTimeframe(
  value: string | null | undefined,
  fallback: Timeframe = "M15",
): Timeframe {
  if (value && isKnownTimeframe(value)) return value;
  return fallback;
}
