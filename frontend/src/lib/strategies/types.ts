import type { AssetClass } from "../../api/client";
import type { LucideIcon } from "lucide-react";

export type StrategyTemplatePill = {
  label: string;
  assetClass: AssetClass;
};

export type StrategyPreset = {
  id: string;
  label: string;
  description: string;
  assetClasses: AssetClass[];
  enabledPills: StrategyTemplatePill[];
  route: string;
  icon: LucideIcon;
  tags?: string[];
};
