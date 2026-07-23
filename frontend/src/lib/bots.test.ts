import { describe, expect, it } from "vitest";
import {
  computeOverallStatus,
  formatBotErrorsForClipboard,
  formatOverallErrorSummary,
  listBotErrors,
  resolveOverallStatusTooltip,
} from "./bots";
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

  it("is error when any bot is in error", () => {
    expect(
      computeOverallStatus({
        ...base,
        orchestratorRunning: true,
        anyAssetClassEnabled: true,
        bots: [{ name: "secretary", state: "error", last_error: "boom" }],
      }),
    ).toBe("error");
  });
});

describe("formatOverallErrorSummary", () => {
  it("includes bot name and last_error", () => {
    expect(
      formatOverallErrorSummary([
        { name: "secretary", state: "error", last_error: "OANDA timeout" },
      ]),
    ).toBe("Secretary: OANDA timeout");
  });

  it("notes additional errored bots", () => {
    expect(
      formatOverallErrorSummary([
        { name: "secretary", state: "error", last_error: "OANDA timeout" },
        { name: "broker", state: "error", last_error: "sync failed" },
      ]),
    ).toBe("Secretary: OANDA timeout (+1 more)");
  });

  it("falls back when last_error is missing", () => {
    expect(formatOverallErrorSummary([{ name: "researcher", state: "error" }])).toBe(
      "Researcher reported an error.",
    );
  });
});

describe("formatBotErrorsForClipboard", () => {
  it("joins all bot errors on separate lines", () => {
    expect(
      formatBotErrorsForClipboard([
        { name: "secretary", state: "error", last_error: "OANDA timeout" },
        { name: "broker", state: "error", last_error: "sync failed" },
      ]),
    ).toBe("Secretary: OANDA timeout\nBroker: sync failed");
  });
});

describe("listBotErrors / resolveOverallStatusTooltip", () => {
  it("lists only bots in error state", () => {
    expect(
      listBotErrors([
        { name: "secretary", state: "error", last_error: "pipeline stalled" },
        { name: "broker", state: "running" },
      ]),
    ).toEqual([{ name: "Secretary", message: "pipeline stalled" }]);
  });

  it("surfaces concrete errors first in the tooltip", () => {
    const tip = resolveOverallStatusTooltip({
      status: "error",
      bots: [
        { name: "secretary", state: "error", last_error: "pipeline stalled" },
        { name: "broker", state: "running" },
      ],
    });
    expect(tip.lines[0]).toBe("Secretary: pipeline stalled");
    expect(tip.lines).toContain("Secretary: Error");
    expect(tip.lines).toContain("Broker: Running");
  });
});
