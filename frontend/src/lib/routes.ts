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
    analysisRun: (runId: string) => `/research/analysis/${encodeURIComponent(runId)}`,
    backtest: "/research/backtest",
  },
  trading: {
    forex: "/trading/forex",
    explore: "/trading/explore",
  },
  activity: "/activity",
  settings: "/settings",
} as const;
