import type { StrategyAnalysisRun, Trade } from "../../api/client";

/** Exit modes that use runtime exit-monitor analysis (mirrors backend). */
export const EXIT_MONITOR_MODES = new Set([
  "reverse_crossover",
  "trailing_stop",
  "trail_ema_slow",
  "trail_atr",
]);

export function tradeRequiresExitMonitor(
  trade: Pick<Trade, "exit_mode">,
): boolean {
  return EXIT_MONITOR_MODES.has(trade.exit_mode);
}

export type ExitAnalysisRow = {
  trade: Trade;
  latestRun: StrategyAnalysisRun | null;
};

/** Join open exit-monitor trades with their latest exit analysis run. */
export function buildExitAnalysisRows(
  openTrades: Trade[],
  exitRuns: StrategyAnalysisRun[],
): ExitAnalysisRow[] {
  const latestRunByTradeId = new Map<string, StrategyAnalysisRun>();

  for (const run of exitRuns) {
    const tradeId = run.trade_id ?? run.execution?.trade_id;
    if (!tradeId) continue;

    const existing = latestRunByTradeId.get(tradeId);
    if (!existing || run.analyzed_at > existing.analyzed_at) {
      latestRunByTradeId.set(tradeId, run);
    }
  }

  return openTrades
    .filter(tradeRequiresExitMonitor)
    .map((trade) => ({
      trade,
      latestRun: latestRunByTradeId.get(trade.id) ?? null,
    }))
    .sort((a, b) => {
      const aTime = a.latestRun?.analyzed_at ?? a.trade.open_time ?? "";
      const bTime = b.latestRun?.analyzed_at ?? b.trade.open_time ?? "";
      return bTime.localeCompare(aTime);
    });
}
