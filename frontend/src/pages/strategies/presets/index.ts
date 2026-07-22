import { Brain, LineChart, SlidersHorizontal } from "lucide-react";
import { ROUTES } from "../../../lib/routes";
import { ALL_ASSET_CLASSES } from "../../../lib/strategies/instruments";
import type { StrategyPreset } from "./types";

export const STRATEGY_PRESETS: StrategyPreset[] = [
  {
    id: "custom",
    label: "Custom",
    description: "Build your own strategy by adding signals, filters, and rules from scratch.",
    assetClasses: [...ALL_ASSET_CLASSES],
    enabledPills: [{ label: "All asset classes", assetClass: "forex" }],
    route: ROUTES.research.strategyNew("custom"),
    icon: SlidersHorizontal,
    tags: ["Flexible"],
    locked: true,
  },
  {
    id: "ema_crossover",
    label: "EMA Crossover",
    description: "9/21 EMA crossover on M15 with ADX + ATR filters for any asset class.",
    assetClasses: [...ALL_ASSET_CLASSES],
    enabledPills: [{ label: "All asset classes", assetClass: "forex" }],
    route: ROUTES.research.strategyNew("ema-crossover"),
    icon: LineChart,
    tags: ["Trend"],
    locked: true,
  },
  {
    id: "ai_strategy",
    label: "AI Strategy",
    description:
      "Model-derived strategy for a single forex pair. Created enabled — runs reports and improve backtests, then learns in shadow until you promote it to live. One AI Strategy per instrument.",
    assetClasses: ["forex"],
    enabledPills: [{ label: "Forex", assetClass: "forex" }],
    route: ROUTES.research.strategyNew("ai-strategy"),
    icon: Brain,
    tags: ["AI"],
    locked: true,
  },
];

/** Presets shown in the Build Strategy overlay (standard strategies only). */
export function getBuildStrategyPresets(): StrategyPreset[] {
  return STRATEGY_PRESETS.filter((p) => p.id !== "ai_strategy");
}

export function getPresetById(id: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.id === id);
}

export function getPresetByRouteSlug(slug: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.route.endsWith(`/${slug}`));
}
