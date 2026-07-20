import type { BacktestAction } from "../../api/client";

export type EventStepKind = "action" | "signal" | "exit";

export function matchesEventKind(action: BacktestAction, kind: EventStepKind): boolean {
  if (kind === "action") return true;
  if (kind === "signal") return action.kind === "signal" || action.kind === "filter_fail";
  return action.kind === "exit" || action.kind === "sl" || action.kind === "tp";
}

/**
 * Find the next/previous action index for step-through.
 *
 * Actions are chronological (sequence ASC, oldest → newest). ``direction`` ``1``
 * advances forward in time; ``-1`` steps backward.
 */
export function findEventIndex(
  actions: BacktestAction[],
  fromIndex: number,
  kind: EventStepKind,
  direction: 1 | -1,
): number {
  if (actions.length === 0) return -1;
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
