import { api, type ResearchSettings } from "../../../../api/client";
import {
  DEFAULT_DAILY_REPORT_MARKET_ID,
  DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
  DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS,
  DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS,
} from "../../../settings/researchMarkets";
import type { AiStrategyParams } from "./defaults";

export type ReportKind = "daily_report" | "weekly_brief" | "weekly_debrief";

export const REPORT_KIND_LABELS: Record<ReportKind, string> = {
  daily_report: "Daily report",
  weekly_brief: "Weekly brief",
  weekly_debrief: "Weekly debrief",
};

/** Strategy guidance toggles that need a matching Settings → Reports schedule. */
export function missingEnabledReportKinds(
  params: Pick<AiStrategyParams, "useDailyReport" | "useWeeklyBrief" | "useWeeklyDebrief">,
  settings: Pick<
    ResearchSettings,
    "daily_report_enabled" | "weekly_brief_enabled" | "weekly_debrief_enabled"
  > | null,
): ReportKind[] {
  if (!settings) return [];
  const missing: ReportKind[] = [];
  if (params.useDailyReport && !settings.daily_report_enabled) {
    missing.push("daily_report");
  }
  if (params.useWeeklyBrief && !settings.weekly_brief_enabled) {
    missing.push("weekly_brief");
  }
  if (params.useWeeklyDebrief && !settings.weekly_debrief_enabled) {
    missing.push("weekly_debrief");
  }
  return missing;
}

/**
 * Turn on the requested report schedules using default market/offset values.
 * Preserves existing contributor/synthesis/model selections so we do not wipe Reports settings.
 */
export async function enableReportKindsWithDefaults(
  kinds: ReportKind[],
  current: ResearchSettings,
): Promise<ResearchSettings> {
  const unique = [...new Set(kinds)];
  if (unique.length === 0) return current;

  const needDaily = unique.includes("daily_report");
  const needBrief = unique.includes("weekly_brief");
  const needDebrief = unique.includes("weekly_debrief");
  let latest = current;

  if (needDaily) {
    latest = await api.saveResearchSettings({
      contributor_models: current.contributor_models,
      synthesis_model_id: current.synthesis_model_id,
      synthesis_model_name: current.synthesis_model_name,
      synthesis_reasoning_effort: current.synthesis_reasoning_effort,
      daily_report_enabled: true,
      daily_report_market_id: DEFAULT_DAILY_REPORT_MARKET_ID,
      daily_report_market_offset_hours: DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
    });
  }

  if (needBrief || needDebrief) {
    latest = await api.saveWeeklyResearchSettings({
      weekly_brief_enabled: needBrief ? true : latest.weekly_brief_enabled,
      weekly_brief_model_id: latest.weekly_brief_model_id,
      weekly_brief_model_name: latest.weekly_brief_model_name,
      weekly_brief_reasoning_effort: latest.weekly_brief_reasoning_effort,
      weekly_brief_market_id: needBrief
        ? DEFAULT_DAILY_REPORT_MARKET_ID
        : latest.weekly_brief_market_id,
      weekly_brief_market_offset_hours: needBrief
        ? DEFAULT_WEEKLY_BRIEF_MARKET_OFFSET_HOURS
        : latest.weekly_brief_market_offset_hours,
      weekly_debrief_enabled: needDebrief ? true : latest.weekly_debrief_enabled,
      weekly_debrief_model_id: latest.weekly_debrief_model_id,
      weekly_debrief_model_name: latest.weekly_debrief_model_name,
      weekly_debrief_reasoning_effort: latest.weekly_debrief_reasoning_effort,
      weekly_debrief_market_id: needDebrief
        ? DEFAULT_DAILY_REPORT_MARKET_ID
        : latest.weekly_debrief_market_id,
      weekly_debrief_market_offset_hours: needDebrief
        ? DEFAULT_WEEKLY_DEBRIEF_MARKET_OFFSET_HOURS
        : latest.weekly_debrief_market_offset_hours,
    });
  }

  return latest;
}
