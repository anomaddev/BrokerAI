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
      "Model-derived strategy that learns from research bias and trade outcomes. Starts in a shadow warm-up period before you promote it to live.",
    assetClasses: ["forex"],
    enabledPills: [{ label: "Forex", assetClass: "forex" }],
    route: ROUTES.research.strategyNew("ai-strategy"),
    icon: Brain,
    tags: ["AI"],
    locked: true,
  },
];

/** Presets shown in the Build Strategy overlay (AI Strategy first). */
export function getBuildStrategyPresets(): StrategyPreset[] {
  const ai = STRATEGY_PRESETS.find((p) => p.id === "ai_strategy");
  const rest = STRATEGY_PRESETS.filter((p) => p.id !== "ai_strategy");
  return ai ? [ai, ...rest] : [...STRATEGY_PRESETS];
}

export function getPresetById(id: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.id === id);
}

export function getPresetByRouteSlug(slug: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.route.endsWith(`/${slug}`));
}
