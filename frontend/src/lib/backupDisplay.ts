import type { ConfigBackupSource, ConfigBackupSummary } from "../../api/client";

export function formatCategory(backup: ConfigBackupSummary): string {
  return backup.category?.trim() || "Settings";
}

export function formatChange(backup: ConfigBackupSummary): string {
  if (backup.change_label?.trim()) return backup.change_label.trim();
  return backup.summary || "—";
}

export function backupDialogTitle(backup: ConfigBackupSummary): string {
  const change = formatChange(backup);
  const category = formatCategory(backup);
  if (backup.label?.trim()) {
    return `${backup.label.trim()} (${category})`;
  }
  return `${category}: ${change}`;
}

export function isFullBackupRow(backup: ConfigBackupSummary): boolean {
  return backup.kind === "full";
}

export function fullBackupSourceLabel(source?: ConfigBackupSource | null): string {
  switch (source) {
    case "scheduled":
      return "Scheduled";
    case "baseline":
      return "Baseline";
    case "import":
      return "Imported";
    case "manual":
    default:
      return "Manual";
  }
}

export function sortTimelineNewestFirst(items: ConfigBackupSummary[]): ConfigBackupSummary[] {
  return [...items].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}
