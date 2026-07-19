import { describe, expect, it } from "vitest";
import { computeOverallStatus } from "./bots";
import { DEFAULT_FOREX_TRADING_SESSIONS } from "./forexTradingSessions";

describe("computeOverallStatus", () => {
  const base = {
    bots: [{ name: "secretary", state: "running" }],
    marketSessions: [
      {
        id: "london",
        name: "London",
        status: "open" as const,
        hours: "08:00–17:00 UTC",
      },
    ],
    enabledTradingSessions: DEFAULT_FOREX_TRADING_SESSIONS,
    marketAvailable: true,
  };

  it("is stopped when orchestrator is offline", () => {
    expect(
      computeOverallStatus({
        ...base,
        orchestratorRunning: false,
        anyAssetClassEnabled: true,
      }),
    ).toBe("stopped");
  });

  it("is stopped when no asset classes are enabled", () => {
    expect(
      computeOverallStatus({
        ...base,
        orchestratorRunning: true,
        anyAssetClassEnabled: false,
      }),
    ).toBe("stopped");
  });
});
