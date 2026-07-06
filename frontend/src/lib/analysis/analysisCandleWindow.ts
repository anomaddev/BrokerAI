import type { StrategyAnalysisRun } from "../../api/client";
import { formatCandleOpenCloseLabel, resolveKnownTimeframe } from "../candleTime";
import { CLOSE_BUFFER_MS, timeframeToMs, type Timeframe } from "../candleSchedule";
import type { ChartFocusWindow } from "../chart/chartFocusWindow";
import { parseAppInstant } from "../formatTime";
import type { TimeFormatOptions } from "../formatTime";

function parseInstant(value: string | null | undefined): number | null {
  if (!value?.trim()) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Bar open time for the candle this run analyzed.
 *
 * OANDA stores bar opens (a 2:00 M15 bar closes at 2:15). Prefer ``candle_time``,
 * but when ``analyzed_at`` sits just after a bar close and ``candle_time`` is one
 * bar behind, use the bar that actually closed at analysis time.
 */
export function analysisCandleOpenTime(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at" | "metadata" | "timeframe">,
): string | null {
  const timeframe = analysisChartTimeframe(run.timeframe);
  const tfMs = timeframeToMs(timeframe);
  const storedOpen = run.candle_time?.trim() || null;
  const analyzed = parseAppInstant(run.analyzed_at);

  if (analyzed) {
    const atMs = analyzed.getTime();
    const msIntoBar = atMs % tfMs;
    if (msIntoBar <= CLOSE_BUFFER_MS + 120_000) {
      const impliedOpenMs = atMs - msIntoBar - tfMs;
      const storedMs = storedOpen ? parseInstant(storedOpen) : null;
      if (storedMs == null || storedMs < impliedOpenMs) {
        return new Date(impliedOpenMs).toISOString();
      }
    }
  }

  if (storedOpen) return storedOpen;

  const crossover = run.metadata?.crossover_time;
  if (crossover != null && String(crossover).trim()) {
    return String(crossover);
  }

  return run.analyzed_at;
}

/** Resolve analysis run timeframe with a safe default. */
export function analysisChartTimeframe(raw: string | null | undefined): Timeframe {
  return resolveKnownTimeframe(raw);
}

/** Format the analyzed candle open and when it closes. */
export function formatAnalysisCandleLabel(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at" | "metadata" | "timeframe">,
  formatOptions: TimeFormatOptions,
): string | null {
  const openIso = analysisCandleOpenTime(run);
  if (!openIso) return null;
  return formatCandleOpenCloseLabel(
    openIso,
    analysisChartTimeframe(run.timeframe),
    formatOptions,
    "short",
  );
}

/**
 * Build the analysis chart window centered on the analyzed candle.
 *
 * ``displaySince`` / ``displayUntil`` bound the visible chart. ``since`` / ``until``
 * include extra warmup history returned by the API for indicator computation.
 */
export function buildAnalysisCandleWindow(
  run: Pick<StrategyAnalysisRun, "candle_time" | "analyzed_at" | "metadata" | "timeframe">,
  bounds?: {
    since?: string | null;
    until?: string | null;
    displaySince?: string | null;
    displayUntil?: string | null;
  } | null,
): ChartFocusWindow | null {
  const anchorMs = parseInstant(analysisCandleOpenTime(run));
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
