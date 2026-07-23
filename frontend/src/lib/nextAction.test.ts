import { describe, expect, it } from "vitest";
import {
  resolveMarketStatusBadge,
  resolveNextActionTooltipExplainer,
  resolveOverallStatusExplainer,
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

describe("resolveOverallStatusExplainer", () => {
  it("shows the concrete error summary when status is error", () => {
    expect(
      resolveOverallStatusExplainer("error", null, {
        errorSummary: "Secretary: OANDA timeout",
      }),
    ).toBe("Secretary: OANDA timeout");
  });

  it("falls back when error summary is missing", () => {
    expect(resolveOverallStatusExplainer("error", null)).toBe(
      "One or more modules reported an error.",
    );
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

describe("computeNextAction candle preference", () => {
  it("prefers analysis M15 over H4 when both close at the same time", async () => {
    const { computeNextAction } = await import("./nextAction");
    const closeAt = "2026-07-22T12:00:03.000Z";
    const action = computeNextAction({
      status: "running",
      orchestratorRunning: true,
      researchSettings: null,
      marketSessions: [],
      enabledTradingSessions: {
        sydney: false,
        tokyo: false,
        london: true,
        new_york: true,
      },
      marketAvailable: true,
      now: new Date("2026-07-22T11:50:00.000Z"),
      nextCandleFetches: { H4: closeAt, M15: closeAt },
      analysisCandleTimeframes: ["M15"],
    });
    expect(action?.kind).toBe("candle_update");
    expect(action?.timeframe).toBe("M15");
    expect(action?.label).toBe("Next candle (15m)");
  });

  it("prefers shorter TF on ties even without analysis list", async () => {
    const { computeNextAction } = await import("./nextAction");
    const closeAt = "2026-07-22T12:00:03.000Z";
    const action = computeNextAction({
      status: "running",
      orchestratorRunning: true,
      researchSettings: null,
      marketSessions: [],
      enabledTradingSessions: {
        sydney: false,
        tokyo: false,
        london: true,
        new_york: true,
      },
      marketAvailable: true,
      now: new Date("2026-07-22T11:50:00.000Z"),
      nextCandleFetches: { H4: closeAt, M15: closeAt },
    });
    expect(action?.timeframe).toBe("M15");
  });
});
