import { describe, expect, it } from "vitest";
import type { BacktestAction } from "../../api/client";
import {
  actionMatchesKindFilter,
  buildBacktestActionTimeline,
  groupBacktestActions,
} from "./backtestActionGroups";

function action(
  partial: Partial<BacktestAction> & Pick<BacktestAction, "kind" | "message" | "sequence">,
): BacktestAction {
  return {
    id: partial.id ?? partial.sequence,
    run_id: "run-1",
    sequence: partial.sequence,
    kind: partial.kind,
    message: partial.message,
    bar_time: partial.bar_time ?? "2026-01-20T01:00:00+00:00",
    meta: partial.meta ?? null,
    created_at: "2026-01-20T01:00:00+00:00",
  };
}

describe("groupBacktestActions", () => {
  it("groups executed signal, entry, and exit", () => {
    const actions = [
      action({
        sequence: 1,
        kind: "signal",
        message: "Crossover detected, confidence 72%, executing trade",
        meta: { direction: "long" },
        bar_time: "2026-01-20T01:00:00+00:00",
      }),
      action({
        sequence: 2,
        kind: "entry",
        message: "Entered long @ 150",
        meta: { direction: "long", price: 150 },
        bar_time: "2026-01-20T01:00:00+00:00",
      }),
      action({
        sequence: 3,
        kind: "exit",
        message: "Reverse crossover, closing position",
        meta: { direction: "long", price: 151, realized_pnl: 12.5 },
        bar_time: "2026-01-20T05:00:00+00:00",
      }),
    ];

    const { groups, groupedSequences } = groupBacktestActions(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].sequences).toEqual([1, 2, 3]);
    expect(groups[0].direction).toBe("long");
    expect(groups[0].realizedPnl).toBe(12.5);
    expect(groupedSequences.has(1)).toBe(true);
    expect(groupedSequences.has(2)).toBe(true);
    expect(groupedSequences.has(3)).toBe(true);
  });

  it("leaves filter_fail and skipped signals standalone", () => {
    const actions = [
      action({
        sequence: 1,
        kind: "filter_fail",
        message: "Crossover detected, failed ADX filter",
      }),
      action({
        sequence: 2,
        kind: "signal",
        message: "Crossover detected, blocked by session",
      }),
      action({
        sequence: 3,
        kind: "signal",
        message: "Crossover detected, confidence 80%, executing trade",
        meta: { direction: "short" },
      }),
      action({
        sequence: 4,
        kind: "entry",
        message: "Entered short",
        meta: { direction: "short", price: 1 },
      }),
      action({
        sequence: 5,
        kind: "tp",
        message: "Take Profit hit",
        meta: { direction: "short", realized_pnl: 3 },
      }),
    ];

    const { groups, groupedSequences } = groupBacktestActions(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].sequences).toEqual([3, 4, 5]);
    expect(groupedSequences.has(1)).toBe(false);
    expect(groupedSequences.has(2)).toBe(false);
  });

  it("skips orphan exits and open entries", () => {
    const actions = [
      action({
        sequence: 1,
        kind: "exit",
        message: "Orphan exit",
        meta: { realized_pnl: 1 },
      }),
      action({
        sequence: 2,
        kind: "entry",
        message: "Open entry",
        meta: { direction: "long", price: 1 },
      }),
    ];

    const { groups, groupedSequences } = groupBacktestActions(actions);
    expect(groups).toHaveLength(0);
    expect(groupedSequences.size).toBe(0);
  });

  it("handles same-bar signal and entry", () => {
    const bar = "2026-03-01T14:00:00+00:00";
    const actions = [
      action({
        sequence: 10,
        kind: "signal",
        message: "Crossover detected, confidence 70%, executing trade",
        bar_time: bar,
        meta: { direction: "long" },
      }),
      action({
        sequence: 11,
        kind: "entry",
        message: "Entered long",
        bar_time: bar,
        meta: { direction: "long", price: 100 },
      }),
      action({
        sequence: 12,
        kind: "sl",
        message: "Stop Loss hit",
        bar_time: "2026-03-01T18:00:00+00:00",
        meta: { direction: "long", realized_pnl: -5 },
      }),
    ];

    const { groups } = groupBacktestActions(actions);
    expect(groups).toHaveLength(1);
    expect(groups[0].fromBarTime).toBe(bar);
    expect(groups[0].toBarTime).toBe("2026-03-01T18:00:00+00:00");
  });
});

describe("buildBacktestActionTimeline", () => {
  it("defaults to trade groups only (hides filter-fail noise)", () => {
    const actions = [
      action({
        sequence: 1,
        kind: "filter_fail",
        message: "Failed filter",
      }),
      action({
        sequence: 2,
        kind: "signal",
        message: "Crossover detected, confidence 70%, executing trade",
        meta: { direction: "long" },
      }),
      action({
        sequence: 3,
        kind: "entry",
        message: "Entered",
        meta: { direction: "long", price: 1 },
      }),
      action({
        sequence: 4,
        kind: "exit",
        message: "Closed",
        meta: { realized_pnl: 2 },
      }),
      action({
        sequence: 5,
        kind: "signal",
        message: "Crossover detected, blocked by session",
      }),
    ];

    const timeline = buildBacktestActionTimeline(actions);
    expect(timeline.map((item) => item.type)).toEqual(["group"]);
    expect(timeline[0]).toMatchObject({ type: "group", group: { id: "trade-3" } });
  });

  it("interleaves matching standalones when a kind filter is active", () => {
    const actions = [
      action({
        sequence: 1,
        kind: "filter_fail",
        message: "Failed",
      }),
      action({
        sequence: 2,
        kind: "signal",
        message: "Crossover detected, confidence 70%, executing trade",
      }),
      action({
        sequence: 3,
        kind: "entry",
        message: "Entered",
        meta: { direction: "long", price: 1 },
      }),
      action({
        sequence: 4,
        kind: "sl",
        message: "Stop",
        meta: { realized_pnl: -1 },
      }),
    ];

    const onlyFails = buildBacktestActionTimeline(actions, new Set(["filter_fail"]));
    expect(onlyFails).toHaveLength(1);
    expect(onlyFails[0]).toMatchObject({ type: "action", action: { kind: "filter_fail" } });

    const exits = buildBacktestActionTimeline(actions, new Set(["sl"]));
    expect(exits).toHaveLength(1);
    expect(exits[0].type).toBe("group");
  });
});

describe("actionMatchesKindFilter", () => {
  it("matches all when filter empty", () => {
    expect(
      actionMatchesKindFilter(
        action({ sequence: 1, kind: "entry", message: "x" }),
        new Set(),
      ),
    ).toBe(true);
  });
});
