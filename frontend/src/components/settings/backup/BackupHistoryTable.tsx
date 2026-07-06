import {
  BACKUP_TIMELINE_PAGE_SIZE,
  type ConfigBackupRestoreScope,
  type ConfigBackupSummary,
} from "../../../api/client";
import { formatAppInstant, type TimeFormatOptions } from "../../../lib/formatTime";
import {
  backupDialogTitle,
  formatCategory,
  formatChange,
  isFullBackupRow,
} from "../../../lib/backupDisplay";
import BackupIconActions from "./BackupIconActions";
import BackupRestoreMenu from "./BackupRestoreMenu";

type Props = {
  pinnedFullBackup?: ConfigBackupSummary | null;
  timeline: ConfigBackupSummary[];
  timeOptions: TimeFormatOptions;
  downloadingId: string | null;
  page: number;
  totalPages: number;
  total: number;
  historyTotal?: number;
  onPageChange: (page: number) => void;
  onDownload: (backup: ConfigBackupSummary) => void;
  onRestore: (backup: ConfigBackupSummary, scope?: ConfigBackupRestoreScope) => void;
  onDelete: (backup: ConfigBackupSummary) => void;
};

export default function BackupHistoryTable({
  pinnedFullBackup = null,
  timeline,
  timeOptions,
  downloadingId,
  page,
  totalPages,
  total,
  historyTotal,
  onPageChange,
  onDownload,
  onRestore,
  onDelete,
}: Props) {
  function formatCreatedAt(value: string): string {
    return formatAppInstant(value, timeOptions, "short");
  }

  const hasPinned = Boolean(pinnedFullBackup);
  const entryCount = historyTotal ?? total + (hasPinned ? 1 : 0);

  if (entryCount === 0) {
    return <p className="settings-muted">No history yet.</p>;
  }

  const rangeStart = total === 0 ? 0 : (page - 1) * BACKUP_TIMELINE_PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(page * BACKUP_TIMELINE_PAGE_SIZE, total);

  function renderRow(backup: ConfigBackupSummary, pinned = false) {
    const fullRow = isFullBackupRow(backup);
    return (
      <tr
        key={backup.id}
        className={[
          fullRow ? "backup-row--full" : undefined,
          pinned ? "backup-row--pinned" : undefined,
        ]
          .filter(Boolean)
          .join(" ")}
        title={fullRow ? backupDialogTitle(backup) : undefined}
      >
        <td className="backup-table__created">{formatCreatedAt(backup.created_at)}</td>
        <td>
          {fullRow ? (
            <span className="backup-list__kind backup-list__kind--full">
              {pinned ? "Latest full backup" : "Full backup"}
            </span>
          ) : (
            <span className="backup-list__kind backup-list__kind--change">Change</span>
          )}
        </td>
        <td>{formatCategory(backup)}</td>
        <td className="backup-table__change">{formatChange(backup)}</td>
        <td className="backup-table__actions">
          {fullRow ? (
            <BackupIconActions
              backup={backup}
              downloading={downloadingId === backup.id}
              onDownload={onDownload}
              onRestore={(item) => onRestore(item, "full")}
              onDelete={onDelete}
            />
          ) : (
            <BackupRestoreMenu backup={backup} onRestore={onRestore} />
          )}
        </td>
      </tr>
    );
  }

  return (
    <div className="backup-history">
      <div className="research-table-wrap backup-table-wrap">
        <table className="research-table backup-table backup-history-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Type</th>
              <th>Category</th>
              <th>Change</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {pinnedFullBackup ? renderRow(pinnedFullBackup, true) : null}
            {timeline.map((backup) => renderRow(backup))}
          </tbody>
        </table>
      </div>

      {hasPinned ? (
        <p className="settings-muted backup-history-pinned-note">
          Latest full backup stays pinned at the top while you browse change history below.
        </p>
      ) : null}

      {totalPages > 1 ? (
        <div className="backup-pagination">
          <p className="settings-muted backup-pagination__summary">
            {total === 0
              ? "No additional history entries."
              : `Showing ${rangeStart}–${rangeEnd} of ${total} history entries`}
          </p>
          <div className="backup-pagination__controls">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
            >
              Previous
            </button>
            <span className="backup-pagination__page">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
