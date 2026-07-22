import { describe, expect, it } from "vitest";
import type { BacktestAction } from "../../api/client";
import { findEventIndex, findTradeEventIndex } from "./backtestActionStep";

function action(
  sequence: number,
  bar_time: string,
  kind: BacktestAction["kind"] = "signal",
  message?: string,
): BacktestAction {
  return {
    id: sequence,
    run_id: "run-1",
    sequence,
    kind,
    message: message ?? `${kind} ${sequence}`,
    bar_time,
    meta: { direction: "long" },
    created_at: bar_time,
  };
}

describe("findEventIndex", () => {
  const actions = [
    action(0, "2026-01-01T00:00:00.000Z", "entry"),
    action(1, "2026-01-01T01:00:00.000Z", "signal"),
    action(2, "2026-01-01T02:00:00.000Z", "exit"),
    action(3, "2026-01-01T03:00:00.000Z", "entry"),
  ];

  it("Next (direction +1) advances to a later bar_time on ASC actions", () => {
    const next = findEventIndex(actions, 0, "action", 1);
    expect(next).toBe(1);
    expect(actions[next]!.bar_time! > actions[0]!.bar_time!).toBe(true);
  });

  it("Previous (direction -1) steps to an earlier bar_time", () => {
    const prev = findEventIndex(actions, 2, "action", -1);
    expect(prev).toBe(1);
    expect(actions[prev]!.bar_time! < actions[2]!.bar_time!).toBe(true);
  });

  it("Next exit skips forward in time to the next exit-kind row", () => {
    const next = findEventIndex(actions, 0, "exit", 1);
    expect(next).toBe(2);
    expect(actions[next]!.kind).toBe("exit");
  });

  it("returns -1 at the chronological ends", () => {
    expect(findEventIndex(actions, 0, "action", -1)).toBe(-1);
    expect(findEventIndex(actions, 3, "action", 1)).toBe(-1);
  });
});

describe("findTradeEventIndex", () => {
  const actions = [
    action(1, "2026-01-01T00:00:00.000Z", "filter_fail"),
    action(
      2,
      "2026-01-01T01:00:00.000Z",
      "signal",
      "Crossover detected, confidence 70%, executing trade",
    ),
    action(3, "2026-01-01T01:00:00.000Z", "entry"),
    action(4, "2026-01-01T02:00:00.000Z", "exit"),
    action(5, "2026-01-01T03:00:00.000Z", "filter_fail"),
    action(
      6,
      "2026-01-01T04:00:00.000Z",
      "signal",
      "Crossover detected, confidence 80%, executing trade",
    ),
    action(7, "2026-01-01T04:00:00.000Z", "entry"),
    action(8, "2026-01-01T05:00:00.000Z", "sl"),
  ];

  it("Next trade advances from one closed trade entry to the next", () => {
    const entryA = actions.findIndex((row) => row.sequence === 3);
    const entryB = actions.findIndex((row) => row.sequence === 7);
    expect(findTradeEventIndex(actions, entryA, 1)).toBe(entryB);
    expect(findEventIndex(actions, entryA, "trade", 1)).toBe(entryB);
  });

  it("Previous trade steps back to the prior closed trade entry", () => {
    const entryA = actions.findIndex((row) => row.sequence === 3);
    const entryB = actions.findIndex((row) => row.sequence === 7);
    expect(findTradeEventIndex(actions, entryB, -1)).toBe(entryA);
  });

  it("Next trade from a filter_fail before any trade lands on the first trade", () => {
    expect(findTradeEventIndex(actions, 0, 1)).toBe(
      actions.findIndex((row) => row.sequence === 3),
    );
  });

  it("returns -1 at the trade ends", () => {
    const firstEntry = actions.findIndex((row) => row.sequence === 3);
    const lastEntry = actions.findIndex((row) => row.sequence === 7);
    expect(findTradeEventIndex(actions, firstEntry, -1)).toBe(-1);
    expect(findTradeEventIndex(actions, lastEntry, 1)).toBe(-1);
  });
});
