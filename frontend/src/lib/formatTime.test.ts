import { describe, expect, it } from "vitest";
import { formatAppInstant, parseAppInstant } from "./formatTime";

describe("parseAppInstant", () => {
  it("treats naive ISO timestamps as UTC", () => {
    const parsed = parseAppInstant("2026-07-06T04:20:36");
    expect(parsed?.toISOString()).toBe("2026-07-06T04:20:36.000Z");
  });

  it("parses explicit Z timestamps", () => {
    const parsed = parseAppInstant("2026-07-06T04:20:36Z");
    expect(parsed?.toISOString()).toBe("2026-07-06T04:20:36.000Z");
  });
});

describe("formatAppInstant settings display", () => {
  it("uses selected timezone and 24-hour format for settings tables", () => {
    const formatted = formatAppInstant(
      "2026-07-06T04:20:36Z",
      {
        showUtc: false,
        timeZone: "America/New_York",
        timeFormat: "24h",
      },
      "short",
    );

    expect(formatted).toContain("2026");
    expect(formatted).toMatch(/00:20/);
    expect(formatted).not.toContain("UTC");
  });
});
