import type { ConfigBackupSummary } from "../api/client";
import { isFullBackupRow } from "./backupDisplay";

export function findLatestFullBackup(items: ConfigBackupSummary[]): ConfigBackupSummary | null {
  let latest: ConfigBackupSummary | null = null;
  let latestTime = Number.NEGATIVE_INFINITY;

  for (const item of items) {
    if (!isFullBackupRow(item)) continue;
    const time = new Date(item.created_at).getTime();
    if (Number.isNaN(time)) continue;
    if (time > latestTime) {
      latestTime = time;
      latest = item;
    }
  }

  return latest;
}

export function timelineWithoutItem(
  items: ConfigBackupSummary[],
  backupId: string | null | undefined,
): ConfigBackupSummary[] {
  if (!backupId) return items;
  return items.filter((item) => item.id !== backupId);
}

export function buildPinnedBackupTimelineView(
  items: ConfigBackupSummary[],
  page: number,
  pageSize: number,
): {
  pinnedFullBackup: ConfigBackupSummary | null;
  pageItems: ConfigBackupSummary[];
  scrollableTotal: number;
  totalPages: number;
} {
  const pinnedFullBackup = findLatestFullBackup(items);
  const scrollableItems = timelineWithoutItem(items, pinnedFullBackup?.id);
  const scrollableTotal = scrollableItems.length;
  const totalPages = backupTimelinePageCount(scrollableTotal, pageSize);

  return {
    pinnedFullBackup,
    pageItems: paginateBackupTimeline(scrollableItems, page, pageSize),
    scrollableTotal,
    totalPages,
  };
}

export function pruneBackupTimeline(
  items: ConfigBackupSummary[],
  fullRetention: number,
  changeRetention: number,
): ConfigBackupSummary[] {
  let fullKept = 0;
  let changeKept = 0;

  return items.filter((item) => {
    if (isFullBackupRow(item)) {
      fullKept += 1;
      return fullKept <= fullRetention;
    }
    changeKept += 1;
    return changeKept <= changeRetention;
  });
}

export function prependBackupTimeline(
  items: ConfigBackupSummary[],
  additions: ConfigBackupSummary[],
  fullRetention: number,
  changeRetention: number,
): ConfigBackupSummary[] {
  return pruneBackupTimeline([...additions, ...items], fullRetention, changeRetention);
}

export function removeBackupTimelineItem(
  items: ConfigBackupSummary[],
  backupId: string,
): ConfigBackupSummary[] {
  return items.filter((item) => item.id !== backupId);
}

export function paginateBackupTimeline(
  items: ConfigBackupSummary[],
  page: number,
  pageSize: number,
): ConfigBackupSummary[] {
  const start = (page - 1) * pageSize;
  return items.slice(start, start + pageSize);
}

export function backupTimelinePageCount(total: number, pageSize: number): number {
  if (total <= 0) return 1;
  return Math.max(1, Math.ceil(total / pageSize));
}
