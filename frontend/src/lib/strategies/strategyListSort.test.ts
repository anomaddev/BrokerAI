import { describe, expect, it } from "vitest";
import type { Strategy } from "../../api/client";
import { sortStrategies } from "./strategyListSort";

function makeStrategy(overrides: Partial<Strategy> & { id: string; name: string }): Strategy {
  return {
    asset_class: "forex",
    asset_class_label: "Forex",
    timeframe: "M15",
    description: "",
    enabled: true,
    instruments: [],
    strategy_type: "custom",
    preset_id: "custom",
    route: `/research/strategies/${overrides.id}/edit`,
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
    params_schema_version: 1,
    ...overrides,
  };
}

describe("sortStrategies", () => {
  it("sorts by name ascending by default key", () => {
    const strategies = [
      makeStrategy({ id: "2", name: "Zulu" }),
      makeStrategy({ id: "1", name: "Alpha" }),
    ];
    const sorted = sortStrategies(strategies, "name", "asc");
    expect(sorted.map((s) => s.name)).toEqual(["Alpha", "Zulu"]);
  });

  it("sorts by realized pnl descending", () => {
    const strategies = [
      makeStrategy({
        id: "1",
        name: "A",
        stats: {
          total_trades: 1,
          winning_trades: 1,
          losing_trades: 0,
          win_rate: 1,
          realized_pnl: 10,
          open_positions: 0,
          last_trade_at: null,
        },
      }),
      makeStrategy({
        id: "2",
        name: "B",
        stats: {
          total_trades: 1,
          winning_trades: 0,
          losing_trades: 1,
          win_rate: 0,
          realized_pnl: 50,
          open_positions: 0,
          last_trade_at: null,
        },
      }),
    ];
    const sorted = sortStrategies(strategies, "pnl", "desc");
    expect(sorted.map((s) => s.id)).toEqual(["2", "1"]);
  });

  it("sorts by backtest status label", () => {
    const strategies = [
      makeStrategy({ id: "1", name: "A", backtest_status: "queued" }),
      makeStrategy({ id: "2", name: "B", backtest_status: "completed" }),
      makeStrategy({ id: "3", name: "C", backtest_status: "not_run" }),
    ];
    const sorted = sortStrategies(strategies, "backtest", "asc");
    expect(sorted.map((s) => s.id)).toEqual(["2", "3", "1"]);
  });
});
