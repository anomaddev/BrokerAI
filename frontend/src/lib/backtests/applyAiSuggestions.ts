/**
 * Patch strategy params from AI feedback suggestions and stash a builder draft.
 */

import type { StrategyParamsV1 } from "../strategyParams";

export type AiFeedbackSuggestion = {
  id: string;
  path: string;
  label?: string;
  from?: unknown;
  to: unknown;
  rationale?: string;
  priority?: number;
  test_alone?: boolean;
};

const DRAFT_PREFIX = "brokerai-backtest-ai-draft:";

export type BacktestAiDraft = {
  runId: string;
  strategyId: string;
  params: StrategyParamsV1;
  appliedSuggestionIds: string[];
  createdAt: string;
};

function setByPath(params: StrategyParamsV1, path: string, value: unknown): void {
  if (path.startsWith("filters.")) {
    const parts = path.split(".");
    if (parts.length < 3) return;
    const filterId = parts[1];
    const field = parts[2];
    const filters = Array.isArray(params.filters) ? [...params.filters] : [];
    let target = filters.find(
      (f) => f && typeof f === "object" && ("id" in f ? f.id === filterId : f.type === filterId),
    ) as Record<string, unknown> | undefined;
    if (!target) {
      if (filterId === "htf_bias") {
        target = { id: "htf_bias", type: "htf_bias", enabled: true, timeframe: "H4" };
      } else if (filterId === "atr") {
        target = { id: "atr", type: "atr", enabled: true, period: 14, min_value: 0.0008, min_value_jpy: 0.05 };
      } else if (filterId === "adx") {
        target = {
          id: "adx",
          type: "adx",
          enabled: true,
          period: 14,
          threshold: 25,
          compare: "gte",
        };
      } else {
        return;
      }
      filters.push(target as (typeof params.filters)[number]);
    }
    (target as Record<string, unknown>)[field] = value;
    params.filters = filters as StrategyParamsV1["filters"];
    return;
  }

  const parts = path.split(".");
  let cur: Record<string, unknown> = params as unknown as Record<string, unknown>;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    const next = cur[key];
    if (!next || typeof next !== "object" || Array.isArray(next)) {
      cur[key] = {};
    }
    cur = cur[key] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]] = value;
}

export function applySuggestionsToParams(
  params: StrategyParamsV1,
  suggestions: AiFeedbackSuggestion[],
  selectedIds?: Set<string>,
): StrategyParamsV1 {
  const result = structuredClone(params);
  for (const suggestion of suggestions) {
    if (selectedIds && !selectedIds.has(suggestion.id)) continue;
    setByPath(result, suggestion.path, suggestion.to);
  }
  return result;
}

export function storeBacktestAiDraft(draft: BacktestAiDraft): void {
  sessionStorage.setItem(`${DRAFT_PREFIX}${draft.runId}`, JSON.stringify(draft));
}

export function loadBacktestAiDraft(runId: string): BacktestAiDraft | null {
  try {
    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${runId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BacktestAiDraft;
    if (!parsed?.params || parsed.runId !== runId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearBacktestAiDraft(runId: string): void {
  sessionStorage.removeItem(`${DRAFT_PREFIX}${runId}`);
}

export function suggestionDisplayValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (value == null) return "—";
  return String(value);
}
