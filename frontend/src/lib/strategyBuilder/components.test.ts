import { describe, expect, it } from "vitest";
import {
  MAX_SIGNALS,
  STRATEGY_TITLE_MAX,
  addAdditionalTimeframes,
  addEmaComponent,
  addSignalComponent,
  canAddSignal,
  clampEmaPeriod,
  clampStrategyTitle,
  createPrimaryTimeframe,
  emaLabel,
  formatSignalLogicExpression,
  getEmaComponents,
  getMarketsComponent,
  getSignalComponent,
  getSignalComponents,
  hasAdditionalTimeframes,
  hasMarkets,
  hasPrimaryTimeframe,
  isEmaPeriodTaken,
  removeComponent,
  seedCustomComponents,
  seedEmaCrossoverComponents,
  updateComponent,
  updateEmaPeriod,
  updateSignalJoin,
} from "./components";
import { getBuildStrategyPresets } from "../../pages/strategies/presets";

describe("strategy builder components", () => {
  it("clamps strategy titles to 32 characters", () => {
    const long = "A".repeat(50);
    expect(clampStrategyTitle(long)).toHaveLength(STRATEGY_TITLE_MAX);
  });

  it("clamps EMA periods to 2–100", () => {
    expect(clampEmaPeriod(1)).toBe(2);
    expect(clampEmaPeriod(101)).toBe(100);
    expect(clampEmaPeriod(21.4)).toBe(21);
  });

  it("titles EMAs by period", () => {
    expect(emaLabel(9)).toBe("EMA 9");
    expect(emaLabel(21)).toBe("EMA 21");
  });

  it("seeds custom with primary timeframe and markets", () => {
    const components = seedCustomComponents();
    expect(hasPrimaryTimeframe(components)).toBe(true);
    expect(hasMarkets(components)).toBe(true);
    expect(hasAdditionalTimeframes(components)).toBe(false);
    expect(getEmaComponents(components)).toHaveLength(0);
    expect(getSignalComponent(components)).toBeUndefined();
    expect(getMarketsComponent(components)?.sessions).toEqual(["London", "NY"]);
  });

  it("seeds EMA crossover with timeframe, markets, two EMAs, and crossover signal", () => {
    const components = seedEmaCrossoverComponents();
    expect(hasPrimaryTimeframe(components)).toBe(true);
    expect(hasMarkets(components)).toBe(true);
    const emas = getEmaComponents(components);
    expect(emas).toHaveLength(2);
    expect(emas[0].period).toBe(9);
    expect(emas[1].period).toBe(21);
    const signal = getSignalComponent(components);
    expect(signal?.signalType).toBe("ema_crossover");
    expect(signal?.fastEmaId).toBe(emas[0].id);
    expect(signal?.slowEmaId).toBe(emas[1].id);
  });

  it("keeps primary timeframe unique and non-removable", () => {
    const primary = createPrimaryTimeframe();
    const withExtra = addAdditionalTimeframes([primary]);
    const afterRemovePrimary = removeComponent(withExtra, primary.id);
    expect(hasPrimaryTimeframe(afterRemovePrimary)).toBe(true);

    const additional = withExtra.find((c) => c.type === "additional_timeframes");
    expect(additional).toBeTruthy();
    const afterRemoveAdditional = removeComponent(withExtra, additional!.id);
    expect(hasAdditionalTimeframes(afterRemoveAdditional)).toBe(false);
  });

  it("allows stepping through duplicate EMA periods and detects conflicts", () => {
    let components = seedCustomComponents();
    components = addEmaComponent(components, 9);
    components = addEmaComponent(components, 9);
    const emas = getEmaComponents(components);
    expect(emas).toHaveLength(2);
    expect(new Set(emas.map((ema) => ema.period)).size).toBe(2);

    components = updateComponent(components, emas[1].id, { period: emas[0].period });
    expect(getEmaComponents(components).find((ema) => ema.id === emas[1].id)?.period).toBe(
      emas[0].period,
    );
    expect(isEmaPeriodTaken(components, emas[0].period, emas[1].id)).toBe(true);
  });

  it("preserves EMA insertion order when periods change", () => {
    let components = seedCustomComponents();
    components = addEmaComponent(components, 21);
    components = addEmaComponent(components, 9);
    const [first, second] = getEmaComponents(components);
    expect([first.period, second.period]).toEqual([21, 9]);

    components = updateEmaPeriod(components, first.id, 9);
    const after = getEmaComponents(components);
    expect(after.map((ema) => ema.id)).toEqual([first.id, second.id]);
    expect(after.map((ema) => ema.period)).toEqual([9, 9]);

    components = updateEmaPeriod(components, first.id, 12);
    const stepped = getEmaComponents(components);
    expect(stepped.map((ema) => ema.id)).toEqual([first.id, second.id]);
    expect(stepped.map((ema) => ema.period)).toEqual([12, 9]);
  });

  it("updates EMA period by id with clamping", () => {
    let components = seedEmaCrossoverComponents();
    const ema = getEmaComponents(components)[0];
    components = updateEmaPeriod(components, ema.id, 150);
    expect(getEmaComponents(components).find((c) => c.id === ema.id)?.period).toBe(100);
  });

  it("swaps crossover fast/slow when EMA periods are reversed", () => {
    let components = seedEmaCrossoverComponents();
    const [fast, slow] = getEmaComponents(components);
    expect(getSignalComponent(components)?.fastEmaId).toBe(fast.id);
    expect(getSignalComponent(components)?.slowEmaId).toBe(slow.id);

    // Make the assigned "fast" EMA longer than "slow".
    components = updateEmaPeriod(components, fast.id, 50);
    const signal = getSignalComponent(components);
    expect(signal?.fastEmaId).toBe(slow.id);
    expect(signal?.slowEmaId).toBe(fast.id);
    expect(getEmaComponents(components).find((ema) => ema.id === signal?.fastEmaId)?.period).toBe(
      21,
    );
    expect(getEmaComponents(components).find((ema) => ema.id === signal?.slowEmaId)?.period).toBe(
      50,
    );
  });

  it("swaps crossover selection when the user picks the longer EMA as fast", () => {
    let components = seedEmaCrossoverComponents();
    const [ema9, ema21] = getEmaComponents(components);
    components = updateComponent(components, getSignalComponent(components)!.id, {
      fastEmaId: ema21.id,
      slowEmaId: ema9.id,
    });
    const signal = getSignalComponent(components);
    expect(signal?.fastEmaId).toBe(ema9.id);
    expect(signal?.slowEmaId).toBe(ema21.id);
  });

  it("adds up to 5 signals with joins on non-primary signals", () => {
    let components = seedCustomComponents();
    components = addEmaComponent(components, 9);
    components = addEmaComponent(components, 21);
    components = addSignalComponent(components, "ema_crossover");
    components = addSignalComponent(components, "monthly_high");
    let signals = getSignalComponents(components);
    expect(signals).toHaveLength(2);
    expect(signals[0]?.id).toBe("signal_primary");
    expect(signals[0]?.combineWithPrevious).toBeUndefined();
    expect(signals[1]?.combineWithPrevious).toBe("and");
    expect(signals[1]?.linkedWithPrevious).toBe(true);

    components = updateSignalJoin(components, signals[1].id, {
      combineWithPrevious: "or",
      linkedWithPrevious: false,
    });
    expect(getSignalComponents(components)[1]?.combineWithPrevious).toBe("or");
    expect(getSignalComponents(components)[1]?.linkedWithPrevious).toBe(false);

    for (let i = 0; i < 3; i += 1) {
      components = addSignalComponent(components, "monthly_low");
    }
    signals = getSignalComponents(components);
    expect(signals).toHaveLength(MAX_SIGNALS);
    expect(canAddSignal(components)).toBe(false);
    const before = components.length;
    components = addSignalComponent(components, "monthly_high");
    expect(getSignalComponents(components)).toHaveLength(MAX_SIGNALS);
    expect(components).toHaveLength(before);

    const emas = getEmaComponents(components);
    expect(getSignalComponent(components)?.fastEmaId).toBe(emas[0].id);
    expect(getSignalComponent(components)?.slowEmaId).toBe(emas[1].id);
  });

  it("formats chained signals with parenthesis groups", () => {
    let components = seedCustomComponents();
    components = addSignalComponent(components, "monthly_high");
    components = addSignalComponent(components, "monthly_low");
    components = addSignalComponent(components, "monthly_high");
    components = addSignalComponent(components, "monthly_low");
    const signals = getSignalComponents(components);

    // S1 + S2 - S3 + S4
    components = updateSignalJoin(components, signals[1].id, { linkedWithPrevious: true });
    components = updateSignalJoin(components, signals[2].id, { linkedWithPrevious: false });
    components = updateSignalJoin(components, signals[3].id, { linkedWithPrevious: true });

    expect(formatSignalLogicExpression(getSignalComponents(components))).toBe(
      "(S1 AND S2) AND (S3 AND S4)",
    );

    components = updateSignalJoin(components, signals[1].id, { combineWithPrevious: "or" });
    components = updateSignalJoin(components, signals[2].id, { combineWithPrevious: "or" });
    expect(formatSignalLogicExpression(getSignalComponents(components))).toBe(
      "(S1 OR S2) OR (S3 AND S4)",
    );
  });
});

describe("build strategy presets", () => {
  it("lists AI Strategy first, then Custom and EMA Crossover", () => {
    const presets = getBuildStrategyPresets();
    expect(presets[0]?.id).toBe("ai_strategy");
    expect(presets.some((p) => p.id === "custom")).toBe(true);
    expect(presets.some((p) => p.id === "ema_crossover")).toBe(true);
    expect(presets.findIndex((p) => p.id === "ai_strategy")).toBeLessThan(
      presets.findIndex((p) => p.id === "custom"),
    );
  });
});
