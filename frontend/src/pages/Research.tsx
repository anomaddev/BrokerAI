import { useCallback, useEffect, useMemo, useState, type SyntheticEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Download, ExternalLink, MailOpen, RefreshCw, Trash2 } from "lucide-react";
import { ROUTES } from "../lib/routes";
import {
  api,
  BACKGROUND_TASK_COMPLETED_EVENT,
  notifyResearchReportsUnreadUpdated,
  RESEARCH_TASK_KINDS,
  type BackgroundTaskCompletedDetail,
  type ResearchReportMeta,
} from "../api/client";
import ResearchSignalsPanel from "../components/ResearchSignalsPanel";
import { useBackgroundTasks } from "../context/BackgroundTasksContext";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { fetchReportMarkdownFromSignedUrl } from "../lib/supabaseClient";

const RESEARCH_KIND_SET = new Set(Object.values(RESEARCH_TASK_KINDS));

const TYPE_LABELS: Record<string, string> = {
  daily: "Daily report",
  daily_model: "Per-model",
  weekly_brief: "Weekly brief",
  weekly_debrief: "Weekly debrief",
};

const TYPE_FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "All types" },
  { value: "daily", label: "Daily report" },
  { value: "daily_model", label: "Per-model" },
  { value: "weekly_brief", label: "Weekly brief" },
  { value: "weekly_debrief", label: "Weekly debrief" },
];

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function typeLabel(report: ResearchReportMeta): string {
  return TYPE_LABELS[report.type] ?? report.type;
}

function modelLabel(report: ResearchReportMeta): string {
  if (report.model_label) return report.model_label;
  if (report.type === "daily_model") {
    const match = report.filename.match(/-daily_(.+)\.md$/);
    if (match) return match[1].replace(/-/g, " ");
  }
  return "—";
}

function fileLabel(report: ResearchReportMeta): string {
  const parts = report.filename.split("/");
  return parts[parts.length - 1];
}

function canRerunReport(report: ResearchReportMeta): boolean {
  return report.type === "daily" && report.date === todayUtc();
}

type DeleteTarget = ResearchReportMeta | null;

export default function Research() {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const { isResearchTaskActive, isTaskKindActive, watchBackgroundTasks } = useBackgroundTasks();
  const [reports, setReports] = useState<ResearchReportMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const [deleting, setDeleting] = useState(false);

  const loadReports = useCallback(async () => {
    const data = await api.listResearchReports();
    setReports(data.reports);
  }, []);

  useEffect(() => {
    loadReports()
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load reports"),
      )
      .finally(() => setLoading(false));
  }, [loadReports]);

  useEffect(() => {
    function onTaskCompleted(event: Event) {
      const detail = (event as CustomEvent<BackgroundTaskCompletedDetail>).detail;
      if (!RESEARCH_KIND_SET.has(detail.kind as (typeof RESEARCH_TASK_KINDS)[keyof typeof RESEARCH_TASK_KINDS])) {
        return;
      }

      void loadReports();
      notifyResearchReportsUnreadUpdated();

      if (detail.status === "success") {
        setActionError(null);
        setActionMessage("Report generated");
        return;
      }

      if (detail.status === "skipped") {
        const skippedReason = detail.result?.skipped_reason;
        setActionMessage(null);
        setActionError(
          typeof skippedReason === "string" ? skippedReason : "Report run skipped",
        );
        return;
      }

      if (detail.status === "failed") {
        setActionMessage(null);
        setActionError(detail.error ?? "Report run failed");
      }
    }

    window.addEventListener(BACKGROUND_TASK_COMPLETED_EVENT, onTaskCompleted);
    return () => window.removeEventListener(BACKGROUND_TASK_COMPLETED_EVENT, onTaskCompleted);
  }, [loadReports]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return reports.filter((report) => {
      if (typeFilter !== "all" && report.type !== typeFilter) return false;
      if (!q) return true;
      const haystack = [
        report.date,
        typeLabel(report),
        modelLabel(report),
        report.filename,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [reports, query, typeFilter]);

  function openReport(report: ResearchReportMeta) {
    navigate(ROUTES.research.reportView(report.filename));
  }

  async function downloadReport(report: ResearchReportMeta) {
    const key = `download:${report.filename}`;
    setBusyKey(key);
    setActionError(null);
    setActionMessage(null);
    try {
      const data = await api.getResearchReport(report.filename);
      let markdown = data.content ?? "";
      if (!markdown && data.signed_url) {
        markdown = await fetchReportMarkdownFromSignedUrl(data.signed_url);
      }
      const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileLabel(report);
      anchor.click();
      URL.revokeObjectURL(url);
      try {
        await api.markResearchReportRead(report.filename);
        notifyResearchReportsUnreadUpdated();
        setReports((current) =>
          current.map((item) =>
            item.filename === report.filename ? { ...item, is_read: true } : item,
          ),
        );
      } catch {
        /* download succeeded */
      }
      setActionMessage(`Downloaded ${fileLabel(report)}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setBusyKey(null);
    }
  }

  async function markAllRead() {
    setActionError(null);
    setActionMessage(null);
    try {
      const filenames = filtered.map((report) => report.filename);
      await api.markAllResearchReportsRead(filenames);
      notifyResearchReportsUnreadUpdated();
      await loadReports();
      setActionMessage("Marked filtered reports as read");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Mark all read failed");
    }
  }

  async function markUnread(report: ResearchReportMeta) {
    const key = `unread:${report.filename}`;
    setBusyKey(key);
    setActionError(null);
    setActionMessage(null);
    try {
      await api.markResearchReportUnread(report.filename);
      notifyResearchReportsUnreadUpdated();
      setReports((current) =>
        current.map((item) =>
          item.filename === report.filename ? { ...item, is_read: false } : item,
        ),
      );
      setActionMessage(`Marked ${fileLabel(report)} unread`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Mark unread failed");
    } finally {
      setBusyKey(null);
    }
  }

  async function rerunReport(report: ResearchReportMeta) {
    const key = `rerun:${report.filename}`;
    setBusyKey(key);
    setActionError(null);
    setActionMessage(null);
    try {
      await api.rerunResearchReport(report.filename);
      watchBackgroundTasks();
      setActionMessage(`Re-running daily report for ${report.date}`);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Re-run failed");
    } finally {
      setBusyKey(null);
    }
  }

  async function runDailyReportNow() {
    setActionError(null);
    setActionMessage(null);
    try {
      await api.runResearchDailyReport(true);
      watchBackgroundTasks();
      setActionMessage("Daily report started");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function runWeeklyBriefNow() {
    setActionError(null);
    setActionMessage(null);
    try {
      await api.runWeeklyBrief(true);
      watchBackgroundTasks();
      setActionMessage("Weekly brief started");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function runWeeklyDebriefNow() {
    setActionError(null);
    setActionMessage(null);
    try {
      await api.runWeeklyDebrief(true);
      watchBackgroundTasks();
      setActionMessage("Weekly debrief started");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setActionError(null);
    setActionMessage(null);
    try {
      await api.deleteResearchReport(deleteTarget.filename);
      setReports((current) => current.filter((item) => item.filename !== deleteTarget.filename));
      notifyResearchReportsUnreadUpdated();
      setActionMessage(`Deleted ${fileLabel(deleteTarget)}`);
      setDeleteTarget(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  function stopRowActivation(event: SyntheticEvent) {
    event.stopPropagation();
  }

  return (
    <div>
      <h1 className="page-title">Research</h1>
      <ResearchSignalsPanel />
      <div className="settings-panel">
        <div className="research-filters research-reports-toolbar">
          <input
            type="search"
            className="research-search"
            placeholder="Search by date, model, type, or filename…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="research-select-wrap">
            <select
              className="research-select"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              aria-label="Filter by report type"
            >
              {TYPE_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="research-reports-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={loading || filtered.every((report) => report.is_read)}
              onClick={() => void markAllRead()}
            >
              Mark all read
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={
                loading ||
                isResearchTaskActive() ||
                isTaskKindActive(RESEARCH_TASK_KINDS.daily)
              }
              onClick={runDailyReportNow}
            >
              {isTaskKindActive(RESEARCH_TASK_KINDS.daily) ? "Running…" : "Run daily report"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={
                loading ||
                isResearchTaskActive() ||
                isTaskKindActive(RESEARCH_TASK_KINDS.weeklyBrief)
              }
              onClick={runWeeklyBriefNow}
            >
              {isTaskKindActive(RESEARCH_TASK_KINDS.weeklyBrief)
                ? "Running…"
                : "Run weekly brief"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={
                loading ||
                isResearchTaskActive() ||
                isTaskKindActive(RESEARCH_TASK_KINDS.weeklyDebrief)
              }
              onClick={runWeeklyDebriefNow}
            >
              {isTaskKindActive(RESEARCH_TASK_KINDS.weeklyDebrief)
                ? "Running…"
                : "Run weekly debrief"}
            </button>
          </div>
        </div>

        {actionMessage && <p className="status-message">{actionMessage}</p>}
        {actionError && <p className="settings-error">{actionError}</p>}

        {loading && <p className="settings-muted">Loading reports…</p>}
        {error && !loading && <p className="settings-error">{error}</p>}
        {!loading && !error && reports.length === 0 && (
          <p className="settings-muted">
            No reports yet. Use <strong>Run daily report</strong> above or the CLI:{" "}
            <code>brokerai research run-daily --force</code>
          </p>
        )}
        {!loading && !error && reports.length > 0 && filtered.length === 0 && (
          <p className="settings-muted">No reports match your filters.</p>
        )}
        {!loading && !error && filtered.length > 0 && (
          <div className="research-table-wrap">
            <table className="research-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Model</th>
                  <th>Generated</th>
                  <th className="research-file-col">File</th>
                  <th className="research-actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((report) => {
                  const busy = busyKey?.endsWith(report.filename) ?? false;
                  const rerunEnabled = canRerunReport(report);
                  return (
                    <tr
                      key={report.filename}
                      className={`research-row${report.is_read ? "" : " research-row--unread"}`}
                      onClick={() => openReport(report)}
                      tabIndex={0}
                      role="button"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openReport(report);
                        }
                      }}
                    >
                      <td>
                        {!report.is_read ? (
                          <span className="research-unread-dot" aria-label="Unread" title="Unread" />
                        ) : null}
                        {report.date}
                      </td>
                      <td>
                        <span className={`research-tag research-tag--${report.type}`}>
                          {typeLabel(report)}
                        </span>
                      </td>
                      <td>{modelLabel(report)}</td>
                      <td className="settings-muted">
                        {report.generated_at ? formatInstant(report.generated_at, "short") : "—"}
                      </td>
                      <td className="research-file" title={report.filename}>
                        {fileLabel(report)}
                      </td>
                      <td className="research-actions-cell" onClick={stopRowActivation}>
                        <div className="research-row-actions">
                          <button
                            type="button"
                            className="research-action-btn"
                            title="Open report"
                            aria-label={`Open ${fileLabel(report)}`}
                            onClick={() => openReport(report)}
                          >
                            <ExternalLink size={15} strokeWidth={1.75} />
                          </button>
                          {report.is_read ? (
                            <button
                              type="button"
                              className="research-action-btn"
                              title="Mark unread"
                              aria-label={`Mark ${fileLabel(report)} unread`}
                              disabled={busy}
                              onClick={() => void markUnread(report)}
                            >
                              <MailOpen size={15} strokeWidth={1.75} />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="research-action-btn"
                            title="Download markdown"
                            aria-label={`Download ${fileLabel(report)}`}
                            disabled={busy}
                            onClick={() => downloadReport(report)}
                          >
                            <Download size={15} strokeWidth={1.75} />
                          </button>
                          {rerunEnabled ? (
                            <button
                              type="button"
                              className="research-action-btn"
                              title="Re-run today's daily report"
                              aria-label={`Re-run ${fileLabel(report)}`}
                              disabled={busy || isResearchTaskActive()}
                              onClick={() => rerunReport(report)}
                            >
                              <RefreshCw size={15} strokeWidth={1.75} />
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className="research-action-btn research-action-btn--danger"
                            title="Delete report"
                            aria-label={`Delete ${fileLabel(report)}`}
                            disabled={busy || deleting}
                            onClick={() => setDeleteTarget(report)}
                          >
                            <Trash2 size={15} strokeWidth={1.75} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {deleteTarget && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => !deleting && setDeleteTarget(null)}
        >
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-labelledby="delete-report-title"
            aria-describedby="delete-report-message"
            onClick={stopRowActivation}
          >
            <h4 id="delete-report-title">Delete report?</h4>
            <p id="delete-report-message">
              This will permanently delete <strong>{fileLabel(deleteTarget)}</strong>.
              {deleteTarget.type === "daily"
                ? " Trading signals will refresh on the next run."
                : null}
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={deleting}
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleting}
                onClick={confirmDelete}
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
