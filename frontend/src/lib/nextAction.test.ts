import { describe, expect, it } from "vitest";
import {
  resolveMarketStatusBadge,
  resolveNextActionTooltipExplainer,
  type NextActionState,
} from "./nextAction";

function nextAction(overrides: Partial<NextActionState>): NextActionState {
  return {
    kind: "none",
    label: "No upcoming action",
    targetAt: Date.now(),
    windowStartAt: Date.now(),
    remainingMs: 0,
    progress: 0,
    ...overrides,
  };
}

describe("resolveMarketStatusBadge", () => {
  it("returns open for running and waiting", () => {
    expect(resolveMarketStatusBadge("running")).toBe("Market Open");
    expect(resolveMarketStatusBadge("waiting")).toBe("Market Open");
  });

  it("returns closed for sleeping", () => {
    expect(resolveMarketStatusBadge("sleeping")).toBe("Market Closed");
  });

  it("returns null for stopped and error", () => {
    expect(resolveMarketStatusBadge("stopped")).toBeNull();
    expect(resolveMarketStatusBadge("error")).toBeNull();
  });
});

describe("resolveNextActionTooltipExplainer", () => {
  it("describes candle updates with timeframe", () => {
    const text = resolveNextActionTooltipExplainer(
      nextAction({ kind: "candle_update", label: "Next candle (M15)", timeframe: "M15" }),
    );
    expect(text).toContain("15m");
    expect(text).toContain("forex strategies");
  });

  it("describes daily report", () => {
    const text = resolveNextActionTooltipExplainer(
      nextAction({ kind: "daily_report", label: "Daily report" }),
    );
    expect(text).toContain("daily research report");
  });

  it("describes market open with session name", () => {
    const text = resolveNextActionTooltipExplainer(
      nextAction({ kind: "market_open", label: "London open" }),
    );
    expect(text).toContain("London");
  });
});
