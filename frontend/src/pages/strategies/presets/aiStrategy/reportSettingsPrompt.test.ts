import { describe, expect, it } from "vitest";
import { missingEnabledReportKinds } from "./reportSettingsPrompt";

describe("missingEnabledReportKinds", () => {
  it("returns empty when settings are null", () => {
    expect(
      missingEnabledReportKinds(
        { useDailyReport: true, useWeeklyBrief: true, useWeeklyDebrief: true },
        null,
      ),
    ).toEqual([]);
  });

  it("lists only strategy-enabled reports that are off in settings", () => {
    expect(
      missingEnabledReportKinds(
        { useDailyReport: true, useWeeklyBrief: false, useWeeklyDebrief: true },
        {
          daily_report_enabled: false,
          weekly_brief_enabled: false,
          weekly_debrief_enabled: true,
        },
      ),
    ).toEqual(["daily_report"]);
  });

  it("returns all three when strategy uses them and settings are off", () => {
    expect(
      missingEnabledReportKinds(
        { useDailyReport: true, useWeeklyBrief: true, useWeeklyDebrief: true },
        {
          daily_report_enabled: false,
          weekly_brief_enabled: false,
          weekly_debrief_enabled: false,
        },
      ),
    ).toEqual(["daily_report", "weekly_brief", "weekly_debrief"]);
  });
});
