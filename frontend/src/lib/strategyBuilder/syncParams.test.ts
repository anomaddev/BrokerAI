import { describe, expect, it } from "vitest";
import {
  addAdditionalTimeframes,
  addEmaComponent,
  addSignalComponent,
  getEmaComponents,
  seedCustomComponents,
  seedEmaCrossoverComponents,
  updateComponent,
} from "./components";
import {
  applyComponentsToBuilderFields,
  componentsFromParamsV1,
  indicatorsFromEmaComponents,
  mergeComponentsIntoParamsV1,
} from "./syncParams";
import { SCHEMA_VERSION, type StrategyParamsV1 } from "../strategyParams";

function baseParams(): StrategyParamsV1 {
  return {
    schema_version: SCHEMA_VERSION,
    timeframe: "M15",
    min_candles: 50,
    indicators: {},
    signal: { type: "monthly_high" },
    filters: [],
    exits: {
      stop_loss: { mode: "fixed_pips", fixed_pips: 15 },
      take_profit: { mode: "rr_ratio", risk_reward_ratio: 2 },
    },
    risk: { risk_per_trade_pct: 1, max_trades_per_day: 3 },
    execution: { sessions: ["London"], min_confidence: 50 },
  };
}

describe("syncParams", () => {
  it("maps selected crossover EMAs into signal refs", () => {
    const components = seedEmaCrossoverComponents();
    const fields = applyComponentsToBuilderFields(components);
    expect(fields.fastEma).toBe(9);
    expect(fields.slowEma).toBe(21);
    expect(fields.signalType).toBe("ema_crossover");

    const indicators = indicatorsFromEmaComponents(components);
    const emas = getEmaComponents(components);
    expect(indicators[emas[0].id]?.type).toBe("ema");
    expect(indicators[emas[1].id]?.type).toBe("ema");

    const merged = mergeComponentsIntoParamsV1(baseParams(), components);
    expect(merged.signal.type).toBe("ema_crossover");
    if (merged.signal.type === "ema_crossover") {
      expect(merged.signal.fast_ref).toBe(emas[0].id);
      expect(merged.signal.slow_ref).toBe(emas[1].id);
    }
  });

  it("maps reversed crossover EMAs with shorter period as fast", () => {
    let components = seedEmaCrossoverComponents();
    const emas = getEmaComponents(components);
    // Bypass reconcile by building a stale selection, then reading via sync helpers.
    components = components.map((component) =>
      component.type === "signal" && component.signalType === "ema_crossover"
        ? { ...component, fastEmaId: emas[1].id, slowEmaId: emas[0].id }
        : component,
    );

    const fields = applyComponentsToBuilderFields(components);
    expect(fields.fastEma).toBe(9);
    expect(fields.slowEma).toBe(21);

    const merged = mergeComponentsIntoParamsV1(baseParams(), components);
    expect(merged.signal.type).toBe("ema_crossover");
    if (merged.signal.type === "ema_crossover") {
      expect(merged.signal.fast_ref).toBe(emas[0].id);
      expect(merged.signal.slow_ref).toBe(emas[1].id);
    }
  });

  it("sets trail_ema_ref to the slow EMA component id", () => {
    const components = seedEmaCrossoverComponents();
    const emas = getEmaComponents(components);
    const base = baseParams();
    base.signal = {
      type: "ema_crossover",
      fast_ref: "fast",
      slow_ref: "slow",
      direction: "both",
      confirmation: "close",
    };
    base.exits = {
      stop_loss: { mode: "atr_based", atr_multiplier: 1.5 },
      take_profit: {
        mode: "trailing_stop",
        trail_mode: "ema_slow",
        trail_ema_ref: "slow",
      },
    };

    const merged = mergeComponentsIntoParamsV1(base, components);
    expect(merged.exits.take_profit.trail_ema_ref).toBe(emas[1].id);
    expect(Object.keys(merged.indicators)).toEqual(expect.arrayContaining([emas[0].id, emas[1].id]));
    expect(merged.indicators).not.toHaveProperty("fast");
    expect(merged.indicators).not.toHaveProperty("slow");
  });

  it("round-trips additional timeframes, markets, signal, and EMA colors", () => {
    let components = seedCustomComponents();
    components = addEmaComponent(components, 12);
    components = addAdditionalTimeframes(components);
    const additional = components.find((c) => c.type === "additional_timeframes");
    expect(additional).toBeTruthy();
    components = updateComponent(components, additional!.id, {
      timeframes: ["H1", "H4"],
    });
    const markets = components.find((c) => c.type === "markets");
    expect(markets).toBeTruthy();
    components = updateComponent(components, markets!.id, {
      sessions: ["Asia", "London"],
    });
    components = addSignalComponent(components, "monthly_high");

    const merged = mergeComponentsIntoParamsV1(baseParams(), components);
    expect(merged.additional_timeframes).toEqual(["H1", "H4"]);
    expect(merged.execution.sessions).toEqual(["Asia", "London"]);
    expect(merged.signal.type).toBe("monthly_high");

    const restored = componentsFromParamsV1(merged);
    expect(restored.some((c) => c.type === "additional_timeframes")).toBe(true);
    expect(restored.some((c) => c.type === "markets")).toBe(true);
    expect(restored.find((c) => c.type === "markets")?.sessions).toEqual(["Asia", "London"]);
    expect(restored.some((c) => c.type === "ema" && c.period === 12)).toBe(true);
    expect(restored.some((c) => c.type === "signal" && c.signalType === "monthly_high")).toBe(true);
  });
});
