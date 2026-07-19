import { describe, expect, it } from "vitest";
import { backtestStatusLabel, normalizeBacktestStatus } from "./backtestStatus";

describe("backtestStatus", () => {
  it("normalizes unknown values to not_run", () => {
    expect(normalizeBacktestStatus(undefined)).toBe("not_run");
    expect(normalizeBacktestStatus(null)).toBe("not_run");
  });

  it("labels known statuses", () => {
    expect(backtestStatusLabel("not_run")).toBe("Not run");
    expect(backtestStatusLabel("queued")).toBe("Queued");
    expect(backtestStatusLabel("running")).toBe("Running");
    expect(backtestStatusLabel("completed")).toBe("Completed");
    expect(backtestStatusLabel("failed")).toBe("Failed");
  });
});
