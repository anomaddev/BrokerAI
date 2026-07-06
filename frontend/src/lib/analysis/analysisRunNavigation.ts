import type { StrategyAnalysisRun } from "../../api/client";
import {
  DEFAULT_ANALYSIS_SORT_COLUMN,
  DEFAULT_ANALYSIS_SORT_DIRECTION,
  sortAnalysisRunsForTable,
  type AnalysisSortColumn,
  type AnalysisSortDirection,
} from "../strategyAnalysis";

export const ANALYSIS_RUN_NAV_LIMIT = 200;

/** Passed via router state when opening a run from the analysis table. */
export type AnalysisRunNavigationState = {
  runIds: string[];
};

export function buildAnalysisRunNavIds(
  runs: StrategyAnalysisRun[],
  options?: {
    sortColumn?: AnalysisSortColumn;
    sortDirection?: AnalysisSortDirection;
  },
): string[] {
  const sorted = sortAnalysisRunsForTable(runs, {
    sortColumn: options?.sortColumn ?? DEFAULT_ANALYSIS_SORT_COLUMN,
    sortDirection: options?.sortDirection ?? DEFAULT_ANALYSIS_SORT_DIRECTION,
  });
  return sorted.map((run) => run.id);
}

export function resolveAnalysisRunNeighbors(
  runIds: string[],
  runId: string,
): { previousId: string | null; nextId: string | null; index: number; total: number } {
  const index = runIds.indexOf(runId);
  if (index < 0) {
    return { previousId: null, nextId: null, index: -1, total: runIds.length };
  }
  return {
    previousId: index > 0 ? runIds[index - 1]! : null,
    nextId: index < runIds.length - 1 ? runIds[index + 1]! : null,
    index,
    total: runIds.length,
  };
}
