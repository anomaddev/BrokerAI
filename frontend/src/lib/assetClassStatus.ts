import { api, type AssetClass } from "../api/client";

export type AssetClassStatus = {
  assetClass: AssetClass;
  label: string;
  enabled: boolean;
};

export const ASSET_CLASS_LABELS: Record<AssetClass, string> = {
  forex: "Forex",
  metals: "Precious Metals",
  stocks: "Stocks",
  crypto: "Crypto",
  futures: "Futures",
  options: "Options",
};

export const TRADING_ASSET_CLASSES: AssetClass[] = [
  "forex",
  "metals",
  "stocks",
  "options",
  "futures",
  "crypto",
];

/** Load broker enabled flags for every asset class (Settings → Broker tabs). */
export async function loadAssetClassStatuses(): Promise<AssetClassStatus[]> {
  const [forex, metals, stocks, crypto, futures, options] = await Promise.all([
    api.getForexPairs(),
    api.getAssetSettings("metals"),
    api.getAssetSettings("stocks"),
    api.getAssetSettings("crypto"),
    api.getAssetSettings("futures"),
    api.getAssetSettings("options"),
  ]);

  return [
    { assetClass: "forex", label: ASSET_CLASS_LABELS.forex, enabled: forex.enabled },
    { assetClass: "metals", label: ASSET_CLASS_LABELS.metals, enabled: metals.enabled },
    { assetClass: "stocks", label: ASSET_CLASS_LABELS.stocks, enabled: stocks.enabled },
    { assetClass: "options", label: ASSET_CLASS_LABELS.options, enabled: options.enabled },
    { assetClass: "futures", label: ASSET_CLASS_LABELS.futures, enabled: futures.enabled },
    { assetClass: "crypto", label: ASSET_CLASS_LABELS.crypto, enabled: crypto.enabled },
  ];
}

export function assetClassStatusMap(
  statuses: AssetClassStatus[],
): Partial<Record<AssetClass, boolean>> {
  return Object.fromEntries(statuses.map((row) => [row.assetClass, row.enabled]));
}
