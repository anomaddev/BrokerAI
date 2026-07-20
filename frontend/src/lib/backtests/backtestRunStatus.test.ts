import { describe, expect, it } from "vitest";
import { backtestRunStatusLabel, normalizeBacktestRunStatus } from "./backtestRunStatus";

describe("backtestRunStatus", () => {
  it("defaults unknown values to queued", () => {
    expect(normalizeBacktestRunStatus(undefined)).toBe("queued");
    expect(normalizeBacktestRunStatus(null)).toBe("queued");
    expect(normalizeBacktestRunStatus("not_run")).toBe("queued");
  });

  it("preserves known run statuses", () => {
    expect(normalizeBacktestRunStatus("queued")).toBe("queued");
    expect(normalizeBacktestRunStatus("running")).toBe("running");
    expect(normalizeBacktestRunStatus("completed")).toBe("completed");
    expect(normalizeBacktestRunStatus("failed")).toBe("failed");
    expect(normalizeBacktestRunStatus("cancelled")).toBe("cancelled");
  });

  it("returns human-readable labels", () => {
    expect(backtestRunStatusLabel("queued")).toBe("Queued");
    expect(backtestRunStatusLabel("running")).toBe("Running");
    expect(backtestRunStatusLabel("completed")).toBe("Completed");
    expect(backtestRunStatusLabel("failed")).toBe("Failed");
    expect(backtestRunStatusLabel("cancelled")).toBe("Cancelled");
    expect(backtestRunStatusLabel(undefined)).toBe("Queued");
  });
});
