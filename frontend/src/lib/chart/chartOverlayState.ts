import type { Strategy } from "../../api/client";
import type { Direction, IndicatorSpec } from "../strategyParams";
import {
  INDICATOR_COLORS,
  findIndicatorCatalogEntry,
  type AdxOverlaySpec,
  type IndicatorCatalogType,
  type OverlayIndicatorSpec,
} from "./indicatorCatalog";

export type OverlaySource =
  | { kind: "standalone" }
  | { kind: "strategy"; strategyId: string; strategyName: string; ref: string };

export type IndicatorOverlayItem = {
  id: string;
  overlayKind: "indicator";
  source: OverlaySource;
  spec: OverlayIndicatorSpec;
  visible: boolean;
  color: string;
  /** ADX threshold when sourced from strategy filter. */
  adxThreshold?: number;
};

export type SignalsOverlayItem = {
  id: string;
  overlayKind: "signals";
  source: { kind: "strategy"; strategyId: string; strategyName: string };
  fastRef: string;
  slowRef: string;
  direction: Direction;
  minConfidence: number;
  visible: boolean;
};

export type ChartOverlayItem = IndicatorOverlayItem | SignalsOverlayItem;

function newId(): string {
  return crypto.randomUUID();
}

function nextColor(index: number): string {
  return INDICATOR_COLORS[index % INDICATOR_COLORS.length];
}

export function createStandaloneIndicator(type: IndicatorCatalogType): IndicatorOverlayItem {
  const entry = findIndicatorCatalogEntry(type);
  return {
    id: newId(),
    overlayKind: "indicator",
    source: { kind: "standalone" },
    spec: structuredClone(entry.defaultSpec),
    visible: true,
    color: entry.defaultColor,
  };
}

export function decomposeStrategyToLayers(strategy: Strategy): ChartOverlayItem[] {
  const params = strategy.params;
  if (!params) return [];

  const items: ChartOverlayItem[] = [];
  let colorIndex = 0;

  const indicatorEntries = Object.entries(params.indicators ?? {});
  for (const [ref, spec] of indicatorEntries) {
    items.push({
      id: newId(),
      overlayKind: "indicator",
      source: {
        kind: "strategy",
        strategyId: strategy.id,
        strategyName: strategy.name,
        ref,
      },
      spec: structuredClone(spec),
      visible: true,
      color: nextColor(colorIndex++),
    });
  }

  const adxFilter = params.filters.find((filter) => filter.type === "adx" && filter.enabled);
  if (adxFilter?.type === "adx") {
    items.push({
      id: newId(),
      overlayKind: "indicator",
      source: {
        kind: "strategy",
        strategyId: strategy.id,
        strategyName: strategy.name,
        ref: adxFilter.id,
      },
      spec: { type: "adx", period: adxFilter.period },
      visible: true,
      color: nextColor(colorIndex++),
      adxThreshold: adxFilter.threshold,
    });
  }

  if (params.signal.type === "ema_crossover") {
    items.push({
      id: newId(),
      overlayKind: "signals",
      source: {
        kind: "strategy",
        strategyId: strategy.id,
        strategyName: strategy.name,
      },
      fastRef: params.signal.fast_ref,
      slowRef: params.signal.slow_ref,
      direction: params.signal.direction,
      minConfidence: params.execution.min_confidence,
      visible: true,
    });
  }

  return items;
}

export function strategyAlreadyOnChart(items: ChartOverlayItem[], strategyId: string): boolean {
  return items.some(
    (item) =>
      item.source.kind === "strategy" && item.source.strategyId === strategyId,
  );
}

export function updateOverlayItem(
  items: ChartOverlayItem[],
  id: string,
  patch: Partial<IndicatorOverlayItem> | Partial<SignalsOverlayItem>,
): ChartOverlayItem[] {
  return items.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export function removeOverlayItem(items: ChartOverlayItem[], id: string): ChartOverlayItem[] {
  const target = items.find((item) => item.id === id);
  if (!target) return items;

  if (target.source.kind === "strategy") {
    const strategyId = target.source.strategyId;
    return items.filter(
      (item) =>
        item.source.kind !== "strategy" || item.source.strategyId !== strategyId,
    );
  }

  return items.filter((item) => item.id !== id);
}

export function appendOverlayItems(
  items: ChartOverlayItem[],
  next: ChartOverlayItem[],
): ChartOverlayItem[] {
  return [...items, ...next];
}

export function updateIndicatorSpec(
  items: ChartOverlayItem[],
  id: string,
  spec: OverlayIndicatorSpec,
): ChartOverlayItem[] {
  return items.map((item) => {
    if (item.id !== id || item.overlayKind !== "indicator") return item;
    return { ...item, spec };
  });
}

export function isIndicatorOverlay(item: ChartOverlayItem): item is IndicatorOverlayItem {
  return item.overlayKind === "indicator";
}

export function isSignalsOverlay(item: ChartOverlayItem): item is SignalsOverlayItem {
  return item.overlayKind === "signals";
}

export function indicatorSpecFromType(type: IndicatorCatalogType): IndicatorSpec | AdxOverlaySpec {
  return structuredClone(findIndicatorCatalogEntry(type).defaultSpec);
}
