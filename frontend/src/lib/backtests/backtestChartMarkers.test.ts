import { describe, expect, it } from "vitest";
import type { BacktestAction } from "../../api/client";
import {
  backtestActionToSelectedMarker,
  backtestActionsToChartMarkers,
} from "./backtestChartMarkers";

function action(partial: Partial<BacktestAction> & Pick<BacktestAction, "kind" | "message">): BacktestAction {
  return {
    id: partial.id ?? 1,
    run_id: "run-1",
    sequence: partial.sequence ?? 1,
    kind: partial.kind,
    message: partial.message,
    bar_time: partial.bar_time ?? "2026-01-20T01:00:00+00:00",
    meta: partial.meta ?? null,
    created_at: "2026-01-20T01:00:00+00:00",
  };
}

describe("backtestActionsToChartMarkers", () => {
  it("defaults to fills only and omits skipped signals", () => {
    const markers = backtestActionsToChartMarkers([
      action({
        sequence: 1,
        kind: "filter_fail",
        message: "Crossover detected, failed ADX filter",
        meta: { direction: "long" },
      }),
      action({
        sequence: 2,
        kind: "signal",
        message: "Crossover detected, blocked by session",
        meta: { direction: "short" },
      }),
      action({
        sequence: 3,
        kind: "signal",
        message: "Crossover detected, confidence 78%, executing trade",
        meta: { direction: "short" },
      }),
      action({
        sequence: 4,
        kind: "entry",
        message: "Entered short @ 157.9",
        meta: { direction: "short", price: 157.9 },
      }),
      action({
        sequence: 5,
        kind: "sl",
        message: "Stop Loss hit",
        meta: { direction: "short", price: 158.1, reason: "stop_loss" },
      }),
    ]);

    expect(markers.map((marker) => marker.role)).toEqual(["entry", "exit"]);
    expect(markers[0].label).toBe("SHORT");
    expect(markers[1].label).toBe("SL");
  });

  it("can include skipped markers when requested", () => {
    const markers = backtestActionsToChartMarkers(
      [
        action({
          sequence: 1,
          kind: "filter_fail",
          message: "Crossover detected, failed ADX filter",
          meta: { direction: "long" },
        }),
      ],
      { includeSkipped: true },
    );
    expect(markers).toHaveLength(1);
    expect(markers[0].role).toBe("skipped");
    expect(markers[0].label).toBe("FILTER");
  });

  it("builds a selected skip marker for step-through highlight", () => {
    const marker = backtestActionToSelectedMarker(
      action({
        sequence: 9,
        kind: "signal",
        message: "Crossover detected, blocked by session",
        meta: { direction: "long" },
      }),
    );
    expect(marker?.role).toBe("skipped");
    expect(marker?.sequence).toBe(9);
  });
});
