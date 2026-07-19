import { describe, expect, it } from "vitest";
import type { StrategyVersionSnapshot } from "../../api/client";
import {
  isLoadedVersionDirty,
  normalizeVersionSnapshotForBuilder,
} from "./loadVersion";
import { strategyBuilderDirtySnapshot } from "./unsavedChanges";

const sampleSnapshot: StrategyVersionSnapshot = {
  name: "Rollback Target",
  description: "older notes",
  params: {
    schema_version: 1,
    timeframe: "M15",
    additional_timeframes: [],
    indicators: [],
    signal: { type: "ema_crossover", direction: "both", confirmation: "close" },
    filters: [],
    exits: {
      stop_loss: { mode: "atr", atr_multiplier: 1.5 },
      take_profit: { mode: "rr_ratio", risk_reward_ratio: 2 },
    },
    risk: { risk_per_trade_pct: 1 },
    execution: { sessions: ["london"], priority: 50 },
    min_candles: 63,
  },
  instrument_selection: { forex: ["EUR/USD"] },
  enabled: true,
  preset_id: "ema_crossover",
};

describe("normalizeVersionSnapshotForBuilder", () => {
  it("normalizes title, notes, instruments, and enabled for builder hydrate", () => {
    const normalized = normalizeVersionSnapshotForBuilder(sampleSnapshot);
    expect(normalized.title).toBe("Rollback Target");
    expect(normalized.notes).toBe("older notes");
    expect(normalized.instrumentSelection).toEqual({ forex: ["EUR/USD"] });
    expect(normalized.enabled).toBe(true);
    expect(normalized.params.timeframe).toBe("M15");
  });

  it("clamps overlong titles", () => {
    const normalized = normalizeVersionSnapshotForBuilder({
      ...sampleSnapshot,
      name: "X".repeat(40),
    });
    expect(normalized.title.length).toBe(32);
  });
});

describe("isLoadedVersionDirty", () => {
  it("marks a loaded version dirty against the saved baseline", () => {
    const baseline = strategyBuilderDirtySnapshot({
      title: "Current",
      notes: "",
      instrumentSelection: { forex: ["EUR/USD"] },
      components: [],
      params: { timeframe: "M15", overlays: { ema: true } },
    });
    const loaded = strategyBuilderDirtySnapshot({
      title: "Rollback Target",
      notes: "older notes",
      instrumentSelection: { forex: ["EUR/USD"] },
      components: [],
      params: { timeframe: "H1", overlays: { ema: false } },
    });
    expect(isLoadedVersionDirty(loaded, baseline)).toBe(true);
    expect(isLoadedVersionDirty(baseline, baseline)).toBe(false);
  });
});
