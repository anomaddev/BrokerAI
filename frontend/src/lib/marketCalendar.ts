import { timeframeToMs, type Timeframe } from "./candleSchedule";
import { isForexOpen } from "./forexSchedule";
import { resolveKnownTimeframe } from "./candleTime";

const EPOCH_MS = Date.UTC(1970, 0, 1);

/** Floor *when* to the UTC open of the bar containing it. Mirrors backend ``align_bar_open``. */
export function alignBarOpen(when: Date, timeframe: string): Date {
  if (timeframe === "MN") {
    return new Date(Date.UTC(when.getUTCFullYear(), when.getUTCMonth(), 1));
  }

  const tfMs = timeframeToMs(resolveKnownTimeframe(timeframe));
  const elapsed = when.getTime() - EPOCH_MS;
  const aligned = EPOCH_MS + Math.floor(elapsed / tfMs) * tfMs;
  return new Date(aligned);
}

function previousBarOpen(barOpen: Date, timeframe: string): Date {
  if (timeframe === "MN") {
    const year = barOpen.getUTCFullYear();
    const month = barOpen.getUTCMonth();
    if (month === 0) {
      return new Date(Date.UTC(year - 1, 11, 1));
    }
    return new Date(Date.UTC(year, month - 1, 1));
  }

  const tfMs = timeframeToMs(resolveKnownTimeframe(timeframe));
  return new Date(barOpen.getTime() - tfMs);
}

/**
 * Open time of the latest fully closed bar before *asOf* (UTC).
 *
 * Walks backward through bar opens, skipping forex-closed periods.
 */
export function expectedLatestClosedBar(
  timeframe: string,
  asOf: Date = new Date(),
): Date | null {
  const currentOpen = alignBarOpen(asOf, timeframe);
  let candidate = previousBarOpen(currentOpen, timeframe);

  for (let index = 0; index < 500; index += 1) {
    if (isForexOpen(candidate)) {
      return candidate;
    }
    candidate = previousBarOpen(candidate, timeframe);
  }

  return null;
}

export function expectedLatestClosedBarForTimeframe(
  timeframe: Timeframe,
  asOf: Date = new Date(),
): Date | null {
  return expectedLatestClosedBar(timeframe, asOf);
}

/** Compare a stored bar-open instant string to an expected bar open (within 1s). */
export function barOpenTimesMatch(
  storedOpen: string | null | undefined,
  expectedOpen: Date | null,
  toleranceMs = 1000,
): boolean {
  if (!storedOpen?.trim() || !expectedOpen) return false;

  const parsed = Date.parse(storedOpen.trim());
  if (!Number.isFinite(parsed)) return false;

  return Math.abs(parsed - expectedOpen.getTime()) < toleranceMs;
}
