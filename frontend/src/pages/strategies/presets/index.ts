import { LineChart } from "lucide-react";
import { ASSET_CLASS_LABELS } from "../../../lib/strategies/instruments";
import type { StrategyPreset } from "./types";

export const STRATEGY_PRESETS: StrategyPreset[] = [
  {
    id: "ema_crossover",
    label: "EMA Crossover",
    description: "9/21 EMA crossover on M15 with ADX + ATR filters for any forex pair.",
    assetClasses: ["forex"],
    enabledPills: [{ label: ASSET_CLASS_LABELS.forex, assetClass: "forex" }],
    route: "/trading/strategies/new/ema-crossover",
    icon: LineChart,
    tags: ["Trend", "Forex"],
  },
];

export function getPresetById(id: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.id === id);
}

export function getPresetByRouteSlug(slug: string): StrategyPreset | undefined {
  return STRATEGY_PRESETS.find((p) => p.route.endsWith(`/${slug}`));
}
