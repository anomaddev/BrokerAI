import { describe, expect, it } from "vitest";
import type { Strategy, StrategyAnalysisRun, Trade } from "../../api/client";
import {
  buildCandleTimeSummaries,
  compareCandleKeys,
  runsForCandleKey,
} from "./candleTimeSummaries";

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
  [
    "s2",
    {
      id: "s2",
      name: "Stock Momentum",
      asset_class: "stock",
      asset_class_label: "Stocks",
      description: "",
      enabled: true,
      instruments: ["AAPL"],
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

describe("candleTimeSummaries", () => {
  it("sorts candle keys newest first with unknown last", () => {
    expect(compareCandleKeys("2026-07-06T13:00:00Z", "2026-07-06T12:00:00Z")).toBeLessThan(0);
    expect(compareCandleKeys("unknown", "2026-07-06T12:00:00Z")).toBeGreaterThan(0);
  });

  it("dedupes tags and counts unique strategies per candle", () => {
    const summaries = buildCandleTimeSummaries(
      [
        run({ id: "a", timeframe: "M1", run_type: "live" }),
        run({
          id: "b",
          timeframe: "M5",
          strategy_id: "s2",
          strategy_name: "Stock Momentum",
          pair: "AAPL",
          run_type: "manual",
        }),
        run({
          id: "c",
          candle_time: "2026-07-06T11:00:00Z",
          pair: "GBP/USD",
        }),
      ],
      strategiesById,
      (iso) => iso,
    );

    expect(summaries).toHaveLength(2);
    expect(summaries[0].key).toBe("2026-07-06T12:00:00Z");
    expect(summaries[0].sources).toEqual(["Bot", "User"]);
    expect(summaries[0].timeframes).toEqual(["M1", "M5"]);
    expect(summaries[0].assetClasses).toEqual(["Forex", "Stocks"]);
    expect(summaries[0].strategyCount).toBe(2);
    expect(summaries[0].runCount).toBe(2);
  });

  it("counts exit-monitor trades on matching candle keys", () => {
    const exitRun = run({
      id: "exit-1",
      analysis_purpose: "exit",
      trade_id: "trade-1",
      candle_time: "2026-07-06T12:00:00Z",
    });
    const openTrade: Trade = {
      id: "trade-1",
      pair: "EUR/USD",
      direction: "long",
      status: "open",
      strategy_id: "s1",
      strategy_name: "EMA Cross",
      timeframe: "M15",
      exit_mode: "reverse_crossover",
      open_time: "2026-07-06T10:00:00Z",
      entry_price: 1.1,
      stop_loss: 1.09,
      take_profit: 1.12,
      quantity: 1000,
      broker: "oanda",
      broker_trade_id: null,
      analysis_run_id: null,
      close_time: null,
      close_price: null,
      realized_pnl: null,
      close_reason: null,
      created_at: null,
      updated_at: null,
    };

    const summaries = buildCandleTimeSummaries(
      [run({ id: "entry-1" }), exitRun],
      strategiesById,
      (iso) => iso,
      { openTrades: [openTrade], exitRuns: [exitRun] },
    );

    expect(summaries[0].exitMonitorTradeCount).toBe(1);
  });

  it("filters runs for a candle key", () => {
    const runs = [
      run({ id: "a", candle_time: "2026-07-06T12:00:00Z" }),
      run({ id: "b", candle_time: "2026-07-06T11:00:00Z" }),
    ];
    expect(runsForCandleKey(runs, "2026-07-06T12:00:00Z").map((item) => item.id)).toEqual([
      "a",
    ]);
  });
});
