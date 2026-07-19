import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  STRATEGY_VERSIONS_PAGE_SIZE,
  type StrategyVersionSummary,
} from "../../api/client";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import { formatAppClockTime, type TimeFormatOptions } from "../../lib/formatTime";
import { groupStrategyVersionsByDay } from "../../lib/strategyBuilder/versionHistoryGroups";
import ReplaceStrategyEditsDialog from "./ReplaceStrategyEditsDialog";
import StrategyOverlay from "./StrategyOverlay";

function VersionHistoryDayRows({
  label,
  versions,
  currentVersion,
  loadingVersionId,
  timeOptions,
  onLoad,
}: {
  label: string;
  versions: StrategyVersionSummary[];
  currentVersion: number | null;
  loadingVersionId: string | null;
  timeOptions: TimeFormatOptions;
  onLoad: (versionId: string) => void;
}) {
  return (
    <Fragment>
      <tr className="strategy-version-history-day-row">
        <td colSpan={4} className="strategy-version-history-day-label">
          {label}
        </td>
      </tr>
      {versions.map((version) => {
        const isCurrent = currentVersion != null && version.version === currentVersion;
        return (
          <tr
            key={version.id}
            className={isCurrent ? "strategy-version-history-row--current" : undefined}
          >
            <td className="strategy-version-history-table__created">
              {version.created_at
                ? formatAppClockTime(version.created_at, timeOptions)
                : "—"}
            </td>
            <td className="strategy-version-history-table__change">
              <div className="strategy-version-history-change-row">
                <span className="strategy-version-history-change-text">
                  {version.change_label || "Strategy updated"}
                </span>
                {isCurrent ? (
                  <span className="strategy-version-history-current-badge">Current</span>
                ) : null}
              </div>
            </td>
            <td className="strategy-version-history-table__version">v{version.version}</td>
            <td className="strategy-version-history-table__actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={isCurrent || loadingVersionId === version.id}
                title={isCurrent ? "This is the currently saved version" : undefined}
                onClick={() => onLoad(version.id)}
              >
                {loadingVersionId === version.id ? "…" : "Load"}
              </button>
            </td>
          </tr>
        );
      })}
    </Fragment>
  );
}

type StrategyVersionHistoryOverlayProps = {
  strategyId: string;
  isDirty: boolean;
  onClose: () => void;
  onLoadVersion: (versionId: string) => Promise<void>;
};

export default function StrategyVersionHistoryOverlay({
  strategyId,
  isDirty,
  onClose,
  onLoadVersion,
}: StrategyVersionHistoryOverlayProps) {
  const { timeOptions } = useGeneralSettings();
  const [versions, setVersions] = useState<StrategyVersionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingVersionId, setLoadingVersionId] = useState<string | null>(null);
  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);

  const loadPage = useCallback(
    async (nextPage: number) => {
      setLoading(true);
      setError(null);
      try {
        const response = await api.listStrategyVersions(strategyId, {
          limit: STRATEGY_VERSIONS_PAGE_SIZE,
          offset: nextPage * STRATEGY_VERSIONS_PAGE_SIZE,
        });
        setVersions(response.versions);
        setTotal(response.total);
        setPage(nextPage);
        // Newest-first: the tip of history is the currently saved strategy.
        if (nextPage === 0) {
          setCurrentVersion(response.versions[0]?.version ?? null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load version history");
      } finally {
        setLoading(false);
      }
    },
    [strategyId],
  );

  useEffect(() => {
    void loadPage(0);
  }, [loadPage]);

  async function applyVersion(versionId: string) {
    setLoadingVersionId(versionId);
    setError(null);
    try {
      await onLoadVersion(versionId);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load version");
    } finally {
      setLoadingVersionId(null);
      setPendingVersionId(null);
    }
  }

  function handleLoadClick(versionId: string) {
    if (isDirty) {
      setPendingVersionId(versionId);
      return;
    }
    void applyVersion(versionId);
  }

  const totalPages = Math.max(1, Math.ceil(total / STRATEGY_VERSIONS_PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : page * STRATEGY_VERSIONS_PAGE_SIZE + 1;
  const rangeEnd = Math.min((page + 1) * STRATEGY_VERSIONS_PAGE_SIZE, total);
  const dayGroups = useMemo(
    () => groupStrategyVersionsByDay(versions, timeOptions),
    [versions, timeOptions],
  );

  return (
    <>
      <StrategyOverlay onClose={onClose} extraWide titleId="strategy-version-history-title">
        <div className="model-overlay-body strategy-version-history">
          <p className="strategy-review-eyebrow">Version history</p>
          <h4 className="model-overlay-title" id="strategy-version-history-title">
            Previous saves
          </h4>
          <p className="strategy-review-subtitle">
            Load a version into the builder as a draft, then Save to keep it.
          </p>

          {error ? <p className="settings-error model-overlay-feedback">{error}</p> : null}

          {loading ? (
            <p className="settings-muted">Loading history…</p>
          ) : total === 0 ? (
            <p className="settings-muted">No previous versions yet.</p>
          ) : (
            <>
              <div className="strategy-version-history-table-wrap">
                <table className="strategy-version-history-table">
                  <colgroup>
                    <col className="strategy-version-history-col--created" />
                    <col className="strategy-version-history-col--change" />
                    <col className="strategy-version-history-col--version" />
                    <col className="strategy-version-history-col--actions" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">Time</th>
                      <th scope="col">Change</th>
                      <th scope="col">Version</th>
                      <th scope="col" className="strategy-version-history-table__actions">
                        <span className="visually-hidden">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {dayGroups.map((group) => (
                      <VersionHistoryDayRows
                        key={group.key}
                        label={group.label}
                        versions={group.versions}
                        currentVersion={currentVersion}
                        loadingVersionId={loadingVersionId}
                        timeOptions={timeOptions}
                        onLoad={handleLoadClick}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              {total > STRATEGY_VERSIONS_PAGE_SIZE ? (
                <div className="strategy-version-history-pager">
                  <span className="settings-muted">
                    Showing {rangeStart}–{rangeEnd} of {total}
                  </span>
                  <div className="strategy-version-history-pager-actions">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page <= 0 || loading}
                      onClick={() => void loadPage(page - 1)}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page + 1 >= totalPages || loading}
                      onClick={() => void loadPage(page + 1)}
                    >
                      Next
                    </button>
                  </div>
                </div>
              ) : (
                <p className="settings-muted strategy-version-history-count">
                  {total === 1 ? "1 saved version" : `${total} saved versions`}
                </p>
              )}
            </>
          )}
        </div>
        <div className="model-overlay-footer">
          <div className="confirm-actions model-overlay-actions">
            <div className="model-overlay-actions-primary">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        </div>
      </StrategyOverlay>

      <ReplaceStrategyEditsDialog
        open={Boolean(pendingVersionId)}
        onCancel={() => setPendingVersionId(null)}
        onConfirm={() => {
          if (pendingVersionId) void applyVersion(pendingVersionId);
        }}
      />
    </>
  );
}
