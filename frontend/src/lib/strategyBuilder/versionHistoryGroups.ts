import type { StrategyVersionSummary } from "../../api/client";
import {
  appCalendarDayKey,
  formatAppDaySection,
  type TimeFormatOptions,
} from "../formatTime";

export type StrategyVersionDayGroup = {
  key: string;
  label: string;
  versions: StrategyVersionSummary[];
};

/** Group versions into contiguous day sections (input should already be newest-first). */
export function groupStrategyVersionsByDay(
  versions: StrategyVersionSummary[],
  timeOptions: TimeFormatOptions,
): StrategyVersionDayGroup[] {
  const groups: StrategyVersionDayGroup[] = [];

  for (const version of versions) {
    const key = appCalendarDayKey(version.created_at, timeOptions) ?? "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.versions.push(version);
      continue;
    }
    groups.push({
      key,
      label: formatAppDaySection(version.created_at, timeOptions),
      versions: [version],
    });
  }

  return groups;
}
