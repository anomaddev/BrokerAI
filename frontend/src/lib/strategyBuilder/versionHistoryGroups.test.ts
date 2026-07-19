import { describe, expect, it } from "vitest";
import type { StrategyVersionSummary } from "../../api/client";
import { groupStrategyVersionsByDay } from "./versionHistoryGroups";

const timeOptions = {
  showUtc: false,
  timeZone: "America/New_York",
  timeFormat: "12h" as const,
};

function version(
  id: string,
  createdAt: string,
  versionNumber: number,
): StrategyVersionSummary {
  return {
    id,
    strategy_id: "s1",
    version: versionNumber,
    created_at: createdAt,
    change_label: `Save ${versionNumber}`,
  };
}

describe("groupStrategyVersionsByDay", () => {
  it("groups contiguous versions that share a calendar day", () => {
    const groups = groupStrategyVersionsByDay(
      [
        version("a", "2026-07-18T23:09:00Z", 2), // 19:09 EDT
        version("b", "2026-07-18T22:36:00Z", 1), // 18:36 EDT
        version("c", "2026-07-17T20:00:00Z", 0), // previous day EDT
      ],
      timeOptions,
    );

    expect(groups).toHaveLength(2);
    expect(groups[0]?.versions.map((row) => row.id)).toEqual(["a", "b"]);
    expect(groups[1]?.versions.map((row) => row.id)).toEqual(["c"]);
    expect(groups[0]?.label).toMatch(/Jul 18|Today|Yesterday/);
  });
});
