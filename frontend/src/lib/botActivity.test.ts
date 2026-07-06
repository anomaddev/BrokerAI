import { describe, expect, it } from "vitest";
import type { BotActivityEvent } from "../api/client";
import { normalizeActivityTimeline } from "./botActivity";

function event(
  id: string,
  action_type: string,
  title: string,
  occurred_at: string,
  metadata: Record<string, unknown> = {},
): BotActivityEvent {
  return {
    id,
    action_type,
    title,
    detail: null,
    source: "test",
    metadata,
    occurred_at,
  };
}

describe("normalizeActivityTimeline", () => {
  it("maps broad labels and limits to 5 entries", () => {
    const events = [
      event("1", "candle_closed", "Candle close (15m)", "2026-07-06T12:15:00Z"),
      event("2", "daily_report_completed", "Daily report", "2026-07-06T12:00:00Z"),
      event("3", "pipeline_fetch_started", "Fetching", "2026-07-06T11:59:00Z"),
      event("4", "pipeline_analyze_completed", "Analysis complete: EUR/USD M15", "2026-07-06T11:58:30Z"),
      event("5", "pipeline_analyze_completed", "Analysis complete: GBP/USD M15", "2026-07-06T11:58:45Z"),
      event("6", "weekly_brief_completed", "Weekly brief", "2026-07-06T11:00:00Z"),
      event("7", "market_session_open", "London open", "2026-07-06T08:00:00Z", {
        session_name: "London",
      }),
    ];

    const timeline = normalizeActivityTimeline(events, 5);

    expect(timeline).toHaveLength(5);
    expect(timeline[0].label).toBe("Candle Closed");
    expect(timeline[1].label).toBe("Daily Report Ran");
    expect(timeline[2].label).toBe("Forex Strategies Analyzed");
    expect(timeline[3].label).toBe("Weekly Brief Ran");
    expect(timeline[4].label).toBe("London Opened");
  });

  it("dedupes analyze completions within the same minute", () => {
    const events = [
      event("1", "pipeline_analyze_completed", "Analysis complete: EUR/USD M15", "2026-07-06T11:58:10Z"),
      event("2", "pipeline_analyze_completed", "Analysis complete: GBP/USD M15", "2026-07-06T11:58:50Z"),
      event("3", "candle_closed", "Candle close (15m)", "2026-07-06T12:15:00Z"),
    ];

    const timeline = normalizeActivityTimeline(events, 5);

    expect(timeline).toHaveLength(2);
    expect(timeline.filter((row) => row.label === "Forex Strategies Analyzed")).toHaveLength(1);
  });
});
