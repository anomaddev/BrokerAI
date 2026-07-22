import type { BacktestAction } from "../../api/client";
import { groupBacktestActions } from "./backtestActionGroups";

export type EventStepKind = "trade" | "action" | "signal" | "exit";

export function matchesEventKind(action: BacktestAction, kind: EventStepKind): boolean {
  if (kind === "action") return true;
  if (kind === "trade") {
    return action.kind === "entry" || action.kind === "open";
  }
  if (kind === "signal") return action.kind === "signal" || action.kind === "filter_fail";
  return action.kind === "exit" || action.kind === "sl" || action.kind === "tp";
}

/**
 * Find the next/previous closed-trade entry index for step-through.
 *
 * Uses reconstructed trade groups (signal → entry → exit). Steps land on the
 * entry sequence of the adjacent trade so the UI can select the whole group.
 */
export function findTradeEventIndex(
  actions: BacktestAction[],
  fromIndex: number,
  direction: 1 | -1,
): number {
  if (actions.length === 0) return -1;
  const { groups } = groupBacktestActions(actions);
  if (groups.length === 0) return -1;

  const fromSeq = actions[fromIndex]?.sequence;
  if (fromSeq == null) return -1;

  const containingIdx = groups.findIndex((group) => group.sequences.includes(fromSeq));

  if (direction > 0) {
    const nextGroup =
      containingIdx >= 0
        ? groups[containingIdx + 1]
        : groups.find((group) => group.entrySequence > fromSeq);
    if (!nextGroup) return -1;
    return actions.findIndex((action) => action.sequence === nextGroup.entrySequence);
  }

  if (containingIdx >= 0) {
    const prevGroup = groups[containingIdx - 1];
    if (!prevGroup) return -1;
    return actions.findIndex((action) => action.sequence === prevGroup.entrySequence);
  }

  for (let index = groups.length - 1; index >= 0; index -= 1) {
    const group = groups[index];
    if (group.exitSequence < fromSeq || group.entrySequence < fromSeq) {
      return actions.findIndex((action) => action.sequence === group.entrySequence);
    }
  }
  return -1;
}

/**
 * Find the next/previous action index for step-through.
 *
 * Actions are chronological (sequence ASC, oldest → newest). ``direction`` ``1``
 * advances forward in time; ``-1`` steps backward.
 *
 * ``trade`` steps between closed trade groups and returns the entry index of
 * the adjacent trade.
 */
export function findEventIndex(
  actions: BacktestAction[],
  fromIndex: number,
  kind: EventStepKind,
  direction: 1 | -1,
): number {
  if (actions.length === 0) return -1;
  if (kind === "trade") {
    return findTradeEventIndex(actions, fromIndex, direction);
  }
  if (kind === "action") {
    const next = fromIndex + direction;
    return next >= 0 && next < actions.length ? next : -1;
  }
  if (direction > 0) {
    return actions.findIndex(
      (action, index) => index > fromIndex && matchesEventKind(action, kind),
    );
  }
  for (let index = fromIndex - 1; index >= 0; index -= 1) {
    if (matchesEventKind(actions[index], kind)) return index;
  }
  return -1;
}
