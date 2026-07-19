import type { BotActivityEvent } from "../../api/client";

export const PIPELINE_BATCH_COMPLETED = "pipeline_batch_completed";
export const PIPELINE_ANALYZE_STARTED = "pipeline_analyze_started";

export function findLatestBatchEvent(
  events: BotActivityEvent[],
): BotActivityEvent | null {
  return events.find((event) => event.action_type === PIPELINE_BATCH_COMPLETED) ?? null;
}

/**
 * True when analysis has started but the newest batch-complete event is older.
 *
 * ``acknowledgedBatchId`` is the last batch event id the UI has refreshed for.
 */
export function isPipelineBatchPending(
  events: BotActivityEvent[],
  acknowledgedBatchId: string | null,
): boolean {
  const latestAnalyzeStart = events.find(
    (event) => event.action_type === PIPELINE_ANALYZE_STARTED,
  );
  if (!latestAnalyzeStart) {
    return false;
  }

  const latestBatch = findLatestBatchEvent(events);
  if (!latestBatch) {
    return true;
  }

  if (acknowledgedBatchId && latestBatch.id !== acknowledgedBatchId) {
    return false;
  }

  const analyzeMs = Date.parse(latestAnalyzeStart.occurred_at);
  const batchMs = Date.parse(latestBatch.occurred_at);
  if (Number.isNaN(analyzeMs) || Number.isNaN(batchMs)) {
    return false;
  }

  return analyzeMs > batchMs;
}

/** Whether a new batch-complete event should trigger a data reload. */
export function shouldRefreshForBatchEvent(
  latestBatch: BotActivityEvent | null,
  acknowledgedBatchId: string | null,
): boolean {
  if (!latestBatch) {
    return false;
  }
  return latestBatch.id !== acknowledgedBatchId;
}
