import { describe, expect, it } from "vitest";
import { expectedLatestClosedBar } from "./marketCalendar";

describe("expectedLatestClosedBar", () => {
  it("returns the previous M15 bar open during an active session", () => {
    const asOf = new Date("2026-01-07T15:30:00.000Z");
    const latest = expectedLatestClosedBar("M15", asOf);

    expect(latest).not.toBeNull();
    expect(latest!.getTime()).toBeLessThan(asOf.getTime());
    expect(latest!.toISOString()).toBe("2026-01-07T15:15:00.000Z");
  });
});
