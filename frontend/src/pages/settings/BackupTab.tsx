import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  BACKUP_TIMELINE_PAGE_SIZE,
  type ConfigBackupRestoreScope,
  type ConfigBackupSummary,
} from "../../api/client";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import BackupHistoryTable from "../../components/settings/backup/BackupHistoryTable";
import BackupImportDialog from "../../components/settings/backup/BackupImportDialog";
import BackupScheduleCard from "../../components/settings/backup/BackupScheduleCard";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import { backupDialogTitle } from "../../lib/backupDisplay";
import { BACKUP_TIMELINE_UPDATED, notifyConfigRestored } from "../../lib/configBackup";
import {
  backupTimelinePageCount,
  buildPinnedBackupTimelineView,
  prependBackupTimeline,
  removeBackupTimelineItem,
} from "../../lib/backupTimeline";

type ConfirmAction = "restore" | "delete";

type ConfirmState = {
  backup: ConfigBackupSummary;
  action: ConfirmAction;
  scope: ConfigBackupRestoreScope;
};

export default function BackupTab() {
  const { settingsTimeOptions } = useGeneralSettings();
  const [allTimeline, setAllTimeline] = useState<ConfigBackupSummary[]>([]);
  const [fullRetention, setFullRetention] = useState(30);
  const [changeRetention, setChangeRetention] = useState(100);
  const [page, setPage] = useState(1);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [createLabel, setCreateLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const timelineRefreshTimerRef = useRef<number | null>(null);

  const total = allTimeline.length;
  const timelineView = useMemo(
    () => buildPinnedBackupTimelineView(allTimeline, page, BACKUP_TIMELINE_PAGE_SIZE),
    [allTimeline, page],
  );
  const { pinnedFullBackup, pageItems, scrollableTotal, totalPages } = timelineView;

  const addTimelineEntries = useCallback(
    (entries: ConfigBackupSummary[]) => {
      if (entries.length === 0) return;
      setAllTimeline((previous) =>
        prependBackupTimeline(previous, entries, fullRetention, changeRetention),
      );
      setPage(1);
    },
    [changeRetention, fullRetention],
  );

  const refreshTimeline = useCallback(async () => {
    try {
      const data = await api.listBackups();
      setAllTimeline(data.timeline.items);
      setFullRetention(data.full_retention);
      setChangeRetention(data.change_retention);
      setPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load backups");
    }
  }, []);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  useEffect(() => {
    (async () => {
      setHistoryLoading(true);
      setError(null);
      try {
        await refreshTimeline();
      } finally {
        setHistoryLoading(false);
      }
    })();
  }, [refreshTimeline]);

  useEffect(() => {
    const handleTimelineUpdated = () => {
      if (timelineRefreshTimerRef.current) {
        window.clearTimeout(timelineRefreshTimerRef.current);
      }
      timelineRefreshTimerRef.current = window.setTimeout(() => {
        timelineRefreshTimerRef.current = null;
        void refreshTimeline();
      }, 400);
    };
    window.addEventListener(BACKUP_TIMELINE_UPDATED, handleTimelineUpdated);
    return () => {
      window.removeEventListener(BACKUP_TIMELINE_UPDATED, handleTimelineUpdated);
      if (timelineRefreshTimerRef.current) {
        window.clearTimeout(timelineRefreshTimerRef.current);
      }
    };
  }, [refreshTimeline]);

  async function handleCreateBackup() {
    setCreating(true);
    setError(null);
    setMessage(null);
    try {
      const backup = await api.createBackup(createLabel.trim() ? { label: createLabel.trim() } : undefined);
      setCreateOpen(false);
      setCreateLabel("");
      setMessage("Backup created.");
      addTimelineEntries([backup]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create backup");
    } finally {
      setCreating(false);
    }
  }

  async function handleExportCurrent() {
    setExporting(true);
    setError(null);
    try {
      const record = await api.exportCurrentBackup();
      const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      anchor.href = url;
      anchor.download = `brokerai-backup-current-${stamp}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to export current configuration");
    } finally {
      setExporting(false);
    }
  }

  async function handleDownload(backup: ConfigBackupSummary) {
    setDownloadingId(backup.id);
    setError(null);
    try {
      const record = await api.getBackup(backup.id);
      const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      const stamp = new Date(backup.created_at).toISOString().slice(0, 19).replace(/[:T]/g, "-");
      anchor.href = url;
      anchor.download = `brokerai-backup-${backup.id.slice(0, 8)}-${stamp}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to download backup");
    } finally {
      setDownloadingId(null);
    }
  }

  function openConfirm(
    backup: ConfigBackupSummary,
    action: ConfirmAction,
    scope: ConfigBackupRestoreScope = "full",
  ) {
    setConfirmTarget({ backup, action, scope });
  }

  function closeConfirm() {
    if (confirmBusy) return;
    setConfirmTarget(null);
  }

  async function handleConfirm() {
    if (!confirmTarget) return;
    setConfirmBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (confirmTarget.action === "restore") {
        const result = await api.restoreBackup(confirmTarget.backup.id, {
          scope: confirmTarget.scope,
        });
        const scopeLabel =
          confirmTarget.scope === "setting" ? "Setting restored" : "Configuration restored";
        setMessage(
          `${scopeLabel}: "${backupDialogTitle(confirmTarget.backup)}". A safety backup was saved${
            result.safety_backup_id ? ` (${result.safety_backup_id.slice(0, 8)}…)` : ""
          }.`,
        );
        if (result.safety_backup) {
          addTimelineEntries([result.safety_backup]);
        }
        notifyConfigRestored();
      } else {
        await api.deleteBackup(confirmTarget.backup.id);
        setMessage("Backup deleted.");
        setAllTimeline((previous) => {
          const next = removeBackupTimelineItem(previous, confirmTarget.backup.id);
          if (next.length === previous.length) return previous;
          const nextTotalPages = backupTimelinePageCount(next.length, BACKUP_TIMELINE_PAGE_SIZE);
          setPage((current) => Math.min(current, nextTotalPages));
          return next;
        });
      }
      closeConfirm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backup action failed");
    } finally {
      setConfirmBusy(false);
    }
  }

  async function handleImport(file: File, label: string, restore: boolean) {
    setImporting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.importBackup(file, {
        label: label || undefined,
        restore,
      });
      setImportOpen(false);
      setMessage(
        result.restored
          ? `Imported and restored "${result.backup.label || result.backup.summary}".`
          : `Imported backup "${result.backup.label || result.backup.summary}".`,
      );
      const additions = [result.backup, ...(result.safety_backup ? [result.safety_backup] : [])];
      addTimelineEntries(additions);
      if (result.restored) notifyConfigRestored();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to import backup");
    } finally {
      setImporting(false);
    }
  }

  return (
    <>
      <div className="settings-panel settings-panel--backup">
        <SettingsPanelHeader
          title="Backup"
          description={
            <>
              History records settings changes and full backups together. Use manual backups before
              risky edits, or schedule them below. Backups include API secrets. Restore replaces
              saved configuration — it does <strong>not</strong> close open trades or rewind trade
              history.
            </>
          }
          action={
            <div className="backup-header-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={exporting}
                onClick={() => void handleExportCurrent()}
              >
                {exporting ? "Exporting…" : "Download current"}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => setImportOpen(true)}>
                Import
              </button>
              <button type="button" className="btn" onClick={() => setCreateOpen(true)}>
                Create
              </button>
            </div>
          }
        />
        <div className="settings-panel-body settings-panel-body--stack">
          {error ? <p className="settings-error">{error}</p> : null}
          {message ? <p className="settings-message">{message}</p> : null}

          <BackupScheduleCard onError={setError} />

          <section className="settings-card research-card backup-section">
            <div className="settings-section-intro">
              <h3 className="research-card-title">History</h3>
              <p className="settings-muted">
                Settings changes and full backups in one timeline.
              </p>
            </div>
            <div className="backup-section__body">
              {historyLoading && allTimeline.length === 0 ? (
                <p className="settings-muted">Loading history…</p>
              ) : (
                <BackupHistoryTable
                  pinnedFullBackup={pinnedFullBackup}
                  timeline={pageItems}
                  timeOptions={settingsTimeOptions}
                  downloadingId={downloadingId}
                  page={page}
                  totalPages={totalPages}
                  total={scrollableTotal}
                  historyTotal={total}
                  onPageChange={setPage}
                  onDownload={(backup) => void handleDownload(backup)}
                  onRestore={(backup, scope) => openConfirm(backup, "restore", scope ?? "full")}
                  onDelete={(backup) => openConfirm(backup, "delete")}
                />
              )}
            </div>
          </section>
        </div>
      </div>

      {createOpen ? (
        <div className="confirm-overlay" role="presentation" onClick={() => !creating && setCreateOpen(false)}>
          <div
            className="confirm-dialog"
            role="dialog"
            aria-labelledby="create-backup-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 id="create-backup-title">Create</h4>
            <p>Save the current configuration as a manual full backup.</p>
            <label className="backup-create-label">
              Label (optional)
              <input
                type="text"
                value={createLabel}
                maxLength={120}
                onChange={(e) => setCreateLabel(e.target.value)}
                placeholder="Before EMA crossover tweak"
              />
            </label>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={creating}
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </button>
              <button type="button" className="btn" disabled={creating} onClick={() => void handleCreateBackup()}>
                {creating ? "Saving…" : "Create"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <BackupImportDialog
        open={importOpen}
        busy={importing}
        onClose={() => setImportOpen(false)}
        onImport={(file, label, restore) => void handleImport(file, label, restore)}
      />

      {confirmTarget ? (
        <div className="confirm-overlay" role="presentation" onClick={closeConfirm}>
          <div
            className={`confirm-dialog${confirmTarget.action === "restore" ? " confirm-dialog--error" : ""}`}
            role="alertdialog"
            aria-labelledby="backup-confirm-title"
            aria-describedby="backup-confirm-message"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 id="backup-confirm-title">
              {confirmTarget.action === "restore"
                ? confirmTarget.scope === "setting"
                  ? `Restore setting from "${backupDialogTitle(confirmTarget.backup)}"?`
                  : `Restore everything to "${backupDialogTitle(confirmTarget.backup)}"?`
                : `Delete "${backupDialogTitle(confirmTarget.backup)}"?`}
            </h4>
            <p id="backup-confirm-message">
              {confirmTarget.action === "restore" ? (
                confirmTarget.scope === "setting" ? (
                  <>
                    This restores only the setting area recorded for this change (
                    {confirmTarget.backup.category || "Settings"}). Other configuration is left
                    unchanged. A safety backup of the current configuration is created automatically
                    before restore.
                  </>
                ) : (
                  <>
                    This replaces general settings, display tweaks, broker and strategy settings,
                    exchange and data connections, research options, AI models, and system update
                    preferences with the snapshot at this point in time. Open positions and trade
                    history are not reverted. A safety backup of the current configuration is created
                    automatically before restore.
                  </>
                )
              ) : (
                <>
                  This entry will be permanently removed. Future settings changes create new history
                  entries automatically.
                </>
              )}
            </p>
            <div className="confirm-actions">
              <button type="button" className="btn btn-secondary" disabled={confirmBusy} onClick={closeConfirm}>
                Cancel
              </button>
              <button
                type="button"
                className={confirmTarget.action === "restore" ? "btn btn-danger" : "btn"}
                disabled={confirmBusy}
                onClick={() => void handleConfirm()}
              >
                {confirmBusy
                  ? confirmTarget.action === "restore"
                    ? "Restoring…"
                    : "Deleting…"
                  : confirmTarget.action === "restore"
                    ? "Restore"
                    : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
