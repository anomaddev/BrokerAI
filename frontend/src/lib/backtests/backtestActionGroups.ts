import type { BacktestAction } from "../../api/client";
import { isExecutedSignal } from "./backtestChartMarkers";

const EXIT_KINDS = new Set(["exit", "sl", "tp", "close"]);

export type BacktestActionGroup = {
  id: string;
  kind: "trade";
  actions: BacktestAction[];
  sequences: number[];
  direction: string | null;
  realizedPnl: number | null;
  fromBarTime: string | null;
  toBarTime: string | null;
  entrySequence: number;
  exitSequence: number;
};

export type BacktestActionTimelineItem =
  | { type: "group"; group: BacktestActionGroup }
  | { type: "action"; action: BacktestAction; index: number };

function metaDirection(action: BacktestAction): string | null {
  const raw = action.meta?.direction;
  if (typeof raw === "string" && raw.trim()) return raw.trim().toLowerCase();
  return null;
}

function metaPnl(action: BacktestAction): number | null {
  const raw = action.meta?.realized_pnl;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * Pair executed signal → entry → exit/sl/tp into trade groups.
 *
 * Edge cases:
 * - Orphan exits (no open entry) are skipped as group members (remain standalone).
 * - Open entry with no exit is not grouped (entry stays standalone).
 * - ``filter_fail`` and skipped signals are never grouped.
 * - Only one flat position is assumed (matches the backtest simulator).
 */
export function groupBacktestActions(actions: BacktestAction[]): {
  groups: BacktestActionGroup[];
  groupedSequences: Set<number>;
} {
  const ordered = [...actions].sort((a, b) => a.sequence - b.sequence);
  const groups: BacktestActionGroup[] = [];
  const groupedSequences = new Set<number>();

  let openEntry: BacktestAction | null = null;
  let pendingSignal: BacktestAction | null = null;

  for (const action of ordered) {
    const kind = action.kind.trim().toLowerCase();

    if (kind === "signal" && isExecutedSignal(action)) {
      // Keep the latest executed signal before the next entry.
      if (openEntry == null) pendingSignal = action;
      continue;
    }

    if (kind === "entry" || kind === "open") {
      openEntry = action;
      continue;
    }

    if (EXIT_KINDS.has(kind) && openEntry != null) {
      const members: BacktestAction[] = [];
      if (pendingSignal && pendingSignal.sequence < openEntry.sequence) {
        members.push(pendingSignal);
      }
      members.push(openEntry, action);

      const direction = metaDirection(openEntry) ?? metaDirection(action);
      const fromBarTime =
        members[0]?.bar_time ?? openEntry.bar_time ?? null;
      const toBarTime = action.bar_time ?? null;

      const group: BacktestActionGroup = {
        id: `trade-${openEntry.sequence}`,
        kind: "trade",
        actions: members,
        sequences: members.map((member) => member.sequence),
        direction,
        realizedPnl: metaPnl(action),
        fromBarTime,
        toBarTime,
        entrySequence: openEntry.sequence,
        exitSequence: action.sequence,
      };
      groups.push(group);
      for (const member of members) groupedSequences.add(member.sequence);

      openEntry = null;
      pendingSignal = null;
    }
  }

  return { groups, groupedSequences };
}

export function actionMatchesKindFilter(
  action: BacktestAction,
  kindFilter: ReadonlySet<string>,
): boolean {
  if (kindFilter.size === 0) return true;
  return kindFilter.has(action.kind.trim().toLowerCase());
}

/**
 * Build a chronological timeline of trade groups and standalone actions for the Trades view.
 *
 * Grouped members are only shown inside their group.
 * When ``kindFilter`` is empty, only closed trade groups are returned — standalone
 * filter fails / skips are omitted so multi-year runs stay scannable.
 * When a kind filter is active, groups appear if any member matches, and matching
 * standalone rows are interleaved in sequence order.
 */
export function buildBacktestActionTimeline(
  actions: BacktestAction[],
  kindFilter: ReadonlySet<string> = new Set(),
): BacktestActionTimelineItem[] {
  const { groups, groupedSequences } = groupBacktestActions(actions);
  const groupByFirstSequence = new Map<number, BacktestActionGroup>();
  for (const group of groups) {
    const first = group.sequences[0];
    if (first != null) groupByFirstSequence.set(first, group);
  }

  const timeline: BacktestActionTimelineItem[] = [];
  const emittedGroups = new Set<string>();
  const includeStandalones = kindFilter.size > 0;

  actions.forEach((action, index) => {
    if (groupedSequences.has(action.sequence)) {
      const group = groupByFirstSequence.get(action.sequence);
      if (!group || emittedGroups.has(group.id)) return;
      const visible =
        kindFilter.size === 0 ||
        group.actions.some((member) => actionMatchesKindFilter(member, kindFilter));
      if (!visible) return;
      emittedGroups.add(group.id);
      timeline.push({ type: "group", group });
      return;
    }

    if (!includeStandalones) return;
    if (!actionMatchesKindFilter(action, kindFilter)) return;
    timeline.push({ type: "action", action, index });
  });

  return timeline;
}

/** Resolve actions for a set of sequences (stable order by sequence). */
export function actionsForSequences(
  actions: BacktestAction[],
  sequences: ReadonlyArray<number>,
): BacktestAction[] {
  const wanted = new Set(sequences);
  return actions
    .filter((action) => wanted.has(action.sequence))
    .sort((a, b) => a.sequence - b.sequence);
}
