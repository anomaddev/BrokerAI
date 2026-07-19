import { Fragment, useEffect, useMemo, useRef, type SyntheticEvent } from "react";
import { useNavigate } from "react-router-dom";
import type { Strategy, StrategyAnalysisRun } from "../../api/client";
import AnalysisRecencyBadge from "./AnalysisRecencyBadge";
import {
  analysisRunRecency,
  buildStaleAnalysisRunIds,
} from "../../lib/analysis/analysisRunRecency";
import {
  entryTableGroupLabel,
  sortRunsForEntryTable,
} from "../../lib/analysis/analysisRunGrouping";
import {
  buildAnalysisRunNavIds,
  type AnalysisRunNavigationState,
} from "../../lib/analysis/analysisRunNavigation";
import { ROUTES } from "../../lib/routes";
import {
  confidencePercent,
  directionClassName,
  directionLabel,
  executionOutcomeClassName,
  executionOutcomeLabel,
  runSourceClassName,
  runSourceLabel,
  signalLabel,
} from "../../lib/strategyAnalysis";
import { TIMEFRAME_LABELS, type Timeframe } from "../../lib/strategyParams";

function timeframeLabel(timeframe: string): string {
  return TIMEFRAME_LABELS[timeframe as Timeframe] ?? timeframe;
}

type CandleAnalysisRunsTableProps = {
  runs: StrategyAnalysisRun[];
  strategies: Strategy[];
  selectedIds: Set<string>;
  onToggleSelected: (runId: string) => void;
  candleKey: string;
  candleKeys: string[];
};

export default function CandleAnalysisRunsTable({
  runs,
  strategies,
  selectedIds,
  onToggleSelected,
  candleKey,
  candleKeys,
}: CandleAnalysisRunsTableProps) {
  const navigate = useNavigate();
  const selectAllRef = useRef<HTMLInputElement>(null);

  const strategiesById = useMemo(
    () => new Map(strategies.map((strategy) => [strategy.id, strategy])),
    [strategies],
  );

  const tableRuns = useMemo(
    () => sortRunsForEntryTable(runs, strategiesById),
    [runs, strategiesById],
  );

  const staleRunIds = useMemo(() => buildStaleAnalysisRunIds(runs), [runs]);

  const runIds = useMemo(() => tableRuns.map((run) => run.id), [tableRuns]);
  const selectedVisibleCount = useMemo(
    () => runIds.filter((id) => selectedIds.has(id)).length,
    [runIds, selectedIds],
  );
  const allRunsSelected = runIds.length > 0 && selectedVisibleCount === runIds.length;
  const someRunsSelected =
    selectedVisibleCount > 0 && selectedVisibleCount < runIds.length;

  useEffect(() => {
    const checkbox = selectAllRef.current;
    if (!checkbox) return;
    checkbox.indeterminate = someRunsSelected;
    checkbox.checked = allRunsSelected;
  }, [allRunsSelected, someRunsSelected]);

  function toggleSelectAllRuns() {
    if (allRunsSelected) {
      for (const id of runIds) {
        if (selectedIds.has(id)) {
          onToggleSelected(id);
        }
      }
      return;
    }
    for (const id of runIds) {
      if (!selectedIds.has(id)) {
        onToggleSelected(id);
      }
    }
  }

  function openRun(run: StrategyAnalysisRun) {
    const navIds = buildAnalysisRunNavIds(tableRuns);
    navigate(ROUTES.research.analysisRun(run.id), {
      state: {
        runIds: navIds,
        candleKey,
        candleKeys,
      } satisfies AnalysisRunNavigationState,
    });
  }

  function stopRowActivation(event: SyntheticEvent) {
    event.stopPropagation();
  }

  if (tableRuns.length === 0) {
    return (
      <p className="settings-muted analysis-panel-status">
        No analysis runs for this candle time.
      </p>
    );
  }

  let previousGroupLabel: string | null = null;

  return (
    <div className="analysis-table-section">
      <div className="research-table-wrap analysis-table-wrap">
        <table className="research-table research-table--clickable analysis-runs-table analysis-entry-table">
          <thead>
            <tr>
              <th className="analysis-runs-table-checkbox-col" scope="col">
                <label className="analysis-runs-table-checkbox-label">
                  <input
                    ref={selectAllRef}
                    type="checkbox"
                    className="ui-checkbox-input"
                    checked={allRunsSelected}
                    onChange={toggleSelectAllRuns}
                    aria-label="Select all analysis runs in this candle"
                  />
                </label>
              </th>
              <th scope="col">Pair</th>
              <th scope="col">Asset</th>
              <th scope="col">Strategy</th>
              <th scope="col">TF</th>
              <th scope="col">Source</th>
              <th scope="col">Direction</th>
              <th scope="col">Signal</th>
              <th scope="col">Conf.</th>
              <th scope="col">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {tableRuns.map((run) => {
              const groupLabel = entryTableGroupLabel(run, strategiesById);
              const showDivider = groupLabel !== previousGroupLabel;
              previousGroupLabel = groupLabel;

              const isSelected = selectedIds.has(run.id);
              const recency = analysisRunRecency(run, staleRunIds);
              const rowClassName = [
                isSelected ? "analysis-runs-table-row--selected" : undefined,
                recency === "current" ? "analysis-runs-table-row--current-bar" : undefined,
                recency === "stale" ? "analysis-runs-table-row--stale-bar" : undefined,
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <Fragment key={run.id}>
                  {showDivider ? (
                    <tr className="analysis-entry-divider-row">
                      <td colSpan={10}>{groupLabel}</td>
                    </tr>
                  ) : null}
                  <tr
                    className={rowClassName || undefined}
                    aria-selected={isSelected}
                    onClick={() => openRun(run)}
                  >
                    <td
                      className="analysis-runs-table-checkbox-col"
                      onClick={stopRowActivation}
                    >
                      <label className="analysis-runs-table-checkbox-label">
                        <input
                          type="checkbox"
                          className="ui-checkbox-input"
                          checked={isSelected}
                          onChange={() => onToggleSelected(run.id)}
                          aria-label={`Select ${run.strategy_name} ${run.pair} analysis run`}
                        />
                      </label>
                    </td>
                    <td>
                      <span className="analysis-pair-cell">
                        <span>{run.pair}</span>
                        {recency !== "historical" ? (
                          <AnalysisRecencyBadge recency={recency} />
                        ) : null}
                      </span>
                    </td>
                    <td className="settings-muted">
                      {strategiesById.get(run.strategy_id)?.asset_class_label ?? "—"}
                    </td>
                    <td>{run.strategy_name}</td>
                    <td className="settings-muted">{timeframeLabel(run.timeframe)}</td>
                    <td>
                      <span className={runSourceClassName(run)}>
                        {runSourceLabel(run)}
                      </span>
                    </td>
                    <td>
                      <span className={directionClassName(run.direction)}>
                        {directionLabel(run.direction)}
                      </span>
                    </td>
                    <td>{signalLabel(run)}</td>
                    <td>{confidencePercent(run.confidence)}</td>
                    <td>
                      <span className={executionOutcomeClassName(run)}>
                        {executionOutcomeLabel(run)}
                      </span>
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
