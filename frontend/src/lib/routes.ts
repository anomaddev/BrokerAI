/** Canonical app routes — keep sidebar, router, and deep links aligned. */

export const ROUTES = {
  dashboard: "/",
  research: {
    reports: "/research/reports",
    reportView: (filename: string) => `/research/reports/r/${filename}`,
    strategies: "/research/strategies",
    strategyNew: (presetId: string) => `/research/strategies/new/${presetId}`,
    strategyEdit: (id: string) => `/research/strategies/${encodeURIComponent(id)}/edit`,
    analysis: "/research/analysis",
    analysisCandle: (candleKey: string) =>
      `/research/analysis/candle/${encodeURIComponent(candleKey)}`,
    analysisRun: (runId: string) =>
      `/research/analysis/run/${encodeURIComponent(runId)}`,
    backtest: "/research/backtest",
    backtestRun: (runId: string) => `/research/backtest/${encodeURIComponent(runId)}`,
  },
  trading: {
    forex: "/trading/forex",
    explore: "/trading/explore",
  },
  activity: "/activity",
  costLedger: "/cost-ledger",
  settings: "/settings",
} as const;
