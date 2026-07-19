import { describe, expect, it } from "vitest";
import type { Strategy, StrategyAnalysisRun } from "../../api/client";
import {
  buildAnalysisRunGroups,
  buildCandleBatches,
  defaultExpandedGroupKeys,
  entryTableGroupLabel,
  flattenAnalysisRunGroups,
  groupNodeId,
  sortRunsForEntryTable,
} from "./analysisRunGrouping";

function run(overrides: Partial<StrategyAnalysisRun> = {}): StrategyAnalysisRun {
  return {
    id: overrides.id ?? "run-1",
    strategy_id: overrides.strategy_id ?? "s1",
    strategy_name: overrides.strategy_name ?? "EMA Cross",
    pair: overrides.pair ?? "EUR/USD",
    timeframe: overrides.timeframe ?? "M15",
    direction: overrides.direction ?? "long",
    confidence: overrides.confidence ?? 0.7,
    signal_type: overrides.signal_type ?? "ema_crossover",
    min_candles: overrides.min_candles ?? 50,
    metadata: overrides.metadata ?? { signal: "bullish_cross" },
    candle_time: overrides.candle_time ?? "2026-07-06T12:00:00Z",
    analyzed_at: overrides.analyzed_at ?? "2026-07-06T12:00:05Z",
    run_type: overrides.run_type ?? "live",
    analysis_purpose: overrides.analysis_purpose ?? "entry",
    trade_id: overrides.trade_id ?? null,
    execution: overrides.execution ?? null,
  };
}

const strategiesById = new Map<string, Strategy>([
  [
    "s1",
    {
      id: "s1",
      name: "EMA Cross",
      asset_class: "forex",
      asset_class_label: "Forex",
      description: "",
      enabled: true,
      instruments: ["EUR/USD"],
      stats: {
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        win_rate: null,
        realized_pnl: 0,
        open_positions: 0,
        last_trade_at: null,
      },
      created_at: null,
      updated_at: null,
    },
  ],
]);

describe("analysisRunGrouping", () => {
  it("groups runs by candle, asset class, strategy, timeframe, and source", () => {
    const groups = buildAnalysisRunGroups(
      [
        run({ id: "a", pair: "EUR/USD", run_type: "live" }),
        run({
          id: "b",
          pair: "GBP/USD",
          run_type: "manual",
          candle_time: "2026-07-06T12:00:00Z",
        }),
      ],
      strategiesById,
      (iso) => iso,
    );

    expect(groups).toHaveLength(1);
    expect(groups[0].level).toBe("candle");
    expect(groups[0].count).toBe(2);
    expect(groups[0].children[0].level).toBe("asset_class");
    expect(groups[0].children[0].children[0].level).toBe("strategy");

    const flattened = flattenAnalysisRunGroups(groups);
    expect(flattened.map((item) => item.id)).toEqual(["a", "b"]);
  });

  it("defaults expansion to the newest candle batch", () => {
    const groups = buildAnalysisRunGroups(
      [
        run({ id: "new", candle_time: "2026-07-06T13:00:00Z" }),
        run({ id: "old", candle_time: "2026-07-06T12:00:00Z" }),
      ],
      strategiesById,
      (iso) => iso,
    );

    const expanded = defaultExpandedGroupKeys(groups);
    expect(expanded.has(groupNodeId(groups[0]))).toBe(true);
    expect(expanded.has(groupNodeId(groups[1]))).toBe(false);
  });

  it("builds candle batches newest first and sorts rows for the table", () => {
    const batches = buildCandleBatches(
      [
        run({ id: "old", pair: "GBP/USD", candle_time: "2026-07-06T12:00:00Z" }),
        run({ id: "new", pair: "EUR/USD", candle_time: "2026-07-06T13:00:00Z" }),
      ],
      (iso) => iso,
    );

    expect(batches.map((batch) => batch.key)).toEqual([
      "2026-07-06T13:00:00Z",
      "2026-07-06T12:00:00Z",
    ]);

    const sorted = sortRunsForEntryTable(batches[0].runs, strategiesById);
    expect(sorted.map((item) => item.id)).toEqual(["new"]);

    expect(entryTableGroupLabel(sorted[0], strategiesById)).toContain("Forex");
    expect(entryTableGroupLabel(sorted[0], strategiesById)).toContain("EMA Cross");
  });
});
