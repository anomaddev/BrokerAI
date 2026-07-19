import { describe, expect, it } from "vitest";
import type { BacktestRun } from "../../api/client";
import { sortBacktestRuns } from "./backtestRunSort";

function makeRun(
  overrides: Partial<BacktestRun> & { id: string; strategy_name: string },
): BacktestRun {
  return {
    strategy_id: overrides.id,
    asset_class: "forex",
    asset_class_label: "Forex",
    timeframe: "M15",
    instruments: ["EUR/USD"],
    status: "queued",
    created_at: "2026-01-01T00:00:00+00:00",
    started_at: null,
    finished_at: null,
    error: null,
    stats: {
      total_trades: null,
      win_rate: null,
      realized_pnl: null,
      max_drawdown: null,
    },
    params_snapshot: null,
    ...overrides,
  };
}

describe("sortBacktestRuns", () => {
  it("sorts by strategy name ascending", () => {
    const runs = [
      makeRun({ id: "2", strategy_name: "Zulu" }),
      makeRun({ id: "1", strategy_name: "Alpha" }),
    ];
    const sorted = sortBacktestRuns(runs, "strategy", "asc");
    expect(sorted.map((run) => run.strategy_name)).toEqual(["Alpha", "Zulu"]);
  });

  it("sorts by created descending", () => {
    const runs = [
      makeRun({
        id: "1",
        strategy_name: "Older",
        created_at: "2026-01-01T00:00:00+00:00",
      }),
      makeRun({
        id: "2",
        strategy_name: "Newer",
        created_at: "2026-02-01T00:00:00+00:00",
      }),
    ];
    const sorted = sortBacktestRuns(runs, "created", "desc");
    expect(sorted.map((run) => run.strategy_name)).toEqual(["Newer", "Older"]);
  });

  it("sorts by status label", () => {
    const runs = [
      makeRun({ id: "1", strategy_name: "A", status: "queued" }),
      makeRun({ id: "2", strategy_name: "B", status: "completed" }),
      makeRun({ id: "3", strategy_name: "C", status: "failed" }),
    ];
    const sorted = sortBacktestRuns(runs, "status", "asc");
    expect(sorted.map((run) => run.status)).toEqual(["completed", "failed", "queued"]);
  });

  it("pushes null pnl values after numeric ones when ascending", () => {
    const runs = [
      makeRun({
        id: "1",
        strategy_name: "Null",
        stats: {
          total_trades: null,
          win_rate: null,
          realized_pnl: null,
          max_drawdown: null,
        },
      }),
      makeRun({
        id: "2",
        strategy_name: "Gain",
        stats: {
          total_trades: 2,
          win_rate: 0.5,
          realized_pnl: 10,
          max_drawdown: 0.1,
        },
      }),
      makeRun({
        id: "3",
        strategy_name: "Loss",
        stats: {
          total_trades: 2,
          win_rate: 0.25,
          realized_pnl: -5,
          max_drawdown: 0.2,
        },
      }),
    ];
    const sorted = sortBacktestRuns(runs, "pnl", "asc");
    expect(sorted.map((run) => run.strategy_name)).toEqual(["Loss", "Gain", "Null"]);
  });
});
