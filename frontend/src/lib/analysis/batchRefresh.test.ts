import { describe, expect, it } from "vitest";
import type { BotActivityEvent } from "../../api/client";
import {
  findLatestBatchEvent,
  isPipelineBatchPending,
  shouldRefreshForBatchEvent,
} from "./batchRefresh";

function event(
  id: string,
  action_type: string,
  occurred_at: string,
): BotActivityEvent {
  return {
    id,
    action_type,
    title: action_type,
    detail: null,
    source: "test",
    metadata: {},
    occurred_at,
  };
}

describe("batchRefresh", () => {
  it("finds the newest batch-complete event", () => {
    const events = [
      event("1", "pipeline_batch_completed", "2026-07-06T12:00:00Z"),
      event("2", "pipeline_analyze_started", "2026-07-06T12:00:05Z"),
      event("3", "pipeline_batch_completed", "2026-07-06T12:01:00Z"),
    ];

    expect(findLatestBatchEvent(events)?.id).toBe("1");
  });

  it("detects pending analysis after the acknowledged batch", () => {
    const events = [
      event("batch-2", "pipeline_batch_completed", "2026-07-06T12:00:00Z"),
      event("analyze-2", "pipeline_analyze_started", "2026-07-06T12:00:10Z"),
    ];

    expect(isPipelineBatchPending(events, "batch-2")).toBe(true);

    const idleEvents = [
      event("batch-2", "pipeline_batch_completed", "2026-07-06T12:00:00Z"),
    ];
    expect(isPipelineBatchPending(idleEvents, null)).toBe(false);
  });

  it("refreshes when a new batch event appears", () => {
    const latest = event("batch-3", "pipeline_batch_completed", "2026-07-06T12:05:00Z");

    expect(shouldRefreshForBatchEvent(latest, "batch-2")).toBe(true);
    expect(shouldRefreshForBatchEvent(latest, "batch-3")).toBe(false);
    expect(shouldRefreshForBatchEvent(null, "batch-3")).toBe(false);
  });
});
