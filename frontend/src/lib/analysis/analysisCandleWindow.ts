import type { StrategyAnalysisRun } from "../../api/client";
import { isKnownTimeframe, type Timeframe } from "../candleSchedule";
import type { ChartFocusWindow } from "../chart/chartFocusWindow";

function parseInstant(value: string | null | undefined): number | null {
  if (!value?.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Resolve analysis run timeframe with a safe default. */
export function analysisChartTimeframe(raw: string | null | undefined): Timeframe {
  if (raw && isKnownTimeframe(raw)) return raw;
  return "M15";
}

/**
 * Build the analysis chart window centered on the analyzed candle.
 *
 * ``displaySince`` / ``displayUntil`` bound the visible chart. ``since`` / ``until``
 * include extra warmup history returned by the API for indicator computation.
 */
export function buildAnalysisCandleWindow(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at">,
  bounds?: {
    since?: string | null;
    until?: string | null;
    displaySince?: string | null;
    displayUntil?: string | null;
  } | null,
): ChartFocusWindow | null {
  const anchorMs =
    parseInstant(run.candle_time) ?? parseInstant(run.analyzed_at);
  if (anchorMs == null) return null;

  const displaySinceMs = parseInstant(bounds?.displaySince);
  const displayUntilMs = parseInstant(bounds?.displayUntil);
  const sinceMs = parseInstant(bounds?.since);
  const untilMs = parseInstant(bounds?.until);

  if (
    displaySinceMs == null ||
    displayUntilMs == null ||
    sinceMs == null ||
    untilMs == null
  ) {
    return null;
  }

  return {
    since: new Date(sinceMs).toISOString(),
    until: new Date(untilMs).toISOString(),
    displaySince: new Date(displaySinceMs).toISOString(),
    displayUntil: new Date(displayUntilMs).toISOString(),
    visibleFromTime: Math.floor(displaySinceMs / 1000),
    visibleToTime: Math.floor(displayUntilMs / 1000),
  };
}
