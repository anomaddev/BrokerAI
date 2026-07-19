import type { AssetClass } from "../api/client";
import oandaLogo from "../assets/providers/oanda.png";
import { ASSET_CLASS_LABELS, TRADING_ASSET_CLASSES } from "./assetClassStatus";

export type ExchangeId =
  | "oanda"
  | "ibkr"
  | "metatrader5"
  | "binance"
  | "coinbase"
  | "kraken";

export type Exchange = {
  id: ExchangeId;
  name: string;
  description: string;
  category: string;
  assetClasses: AssetClass[];
  available: boolean;
  logo?: string;
};

export const EXCHANGES: Exchange[] = [
  {
    id: "oanda",
    name: "OANDA",
    description: "Forex and CFD trading via REST/streaming API.",
    category: "Forex",
    assetClasses: ["forex", "metals"],
    available: true,
    logo: oandaLogo,
  },
  {
    id: "metatrader5",
    name: "MetaTrader 5",
    description: "Forex and CFD execution through MT5 bridge.",
    category: "Forex",
    assetClasses: ["forex"],
    available: false,
  },
  {
    id: "ibkr",
    name: "Interactive Brokers",
    description: "Multi-asset trading across global markets.",
    category: "Multi-asset",
    assetClasses: ["forex", "metals", "stocks", "crypto", "futures", "options"],
    available: false,
  },
  {
    id: "binance",
    name: "Binance",
    description: "Spot and futures crypto trading.",
    category: "Crypto",
    assetClasses: ["crypto"],
    available: false,
  },
  {
    id: "coinbase",
    name: "Coinbase",
    description: "Crypto spot trading via Advanced Trade API.",
    category: "Crypto",
    assetClasses: ["crypto"],
    available: false,
  },
  {
    id: "kraken",
    name: "Kraken",
    description: "Crypto spot and futures trading.",
    category: "Crypto",
    assetClasses: ["crypto"],
    available: false,
  },
];

/** Primary asset class used for catalog sort/group order. */
export function primaryAssetClass(exchange: Exchange): AssetClass {
  return exchange.assetClasses[0] ?? "forex";
}

function assetClassRank(assetClass: AssetClass): number {
  const index = TRADING_ASSET_CLASSES.indexOf(assetClass);
  return index < 0 ? TRADING_ASSET_CLASSES.length : index;
}

/** Sort by allowed asset type, then availability, then specialized before multi-asset, then name. */
export function compareExchangesByAssetClass(a: Exchange, b: Exchange): number {
  const rankDiff = assetClassRank(primaryAssetClass(a)) - assetClassRank(primaryAssetClass(b));
  if (rankDiff !== 0) return rankDiff;
  if (a.available !== b.available) return a.available ? -1 : 1;
  if (a.assetClasses.length !== b.assetClasses.length) {
    return a.assetClasses.length - b.assetClasses.length;
  }
  return a.name.localeCompare(b.name);
}

export function exchangesSortedByAssetClass(
  exchanges: readonly Exchange[] = EXCHANGES,
): Exchange[] {
  return [...exchanges].sort(compareExchangesByAssetClass);
}

export type ExchangeAssetClassGroup = {
  assetClass: AssetClass;
  label: string;
  exchanges: Exchange[];
};

/** Group exchanges under their primary allowed asset type (catalog order). */
export function groupExchangesByAssetClass(
  exchanges: readonly Exchange[] = EXCHANGES,
): ExchangeAssetClassGroup[] {
  const sorted = exchangesSortedByAssetClass(exchanges);
  const buckets = new Map<AssetClass, Exchange[]>();

  for (const exchange of sorted) {
    const key = primaryAssetClass(exchange);
    const list = buckets.get(key);
    if (list) list.push(exchange);
    else buckets.set(key, [exchange]);
  }

  return TRADING_ASSET_CLASSES.filter((assetClass) => buckets.has(assetClass)).map(
    (assetClass) => ({
      assetClass,
      label: ASSET_CLASS_LABELS[assetClass],
      exchanges: buckets.get(assetClass)!,
    }),
  );
}

export function exchangesForAssetClass(assetClass: AssetClass): Exchange[] {
  return exchangesSortedByAssetClass(
    EXCHANGES.filter(
      (exchange) => exchange.available && exchange.assetClasses.includes(assetClass),
    ),
  );
}

export type ExchangeConnectionSummary = {
  exchange_id: ExchangeId;
  connected: boolean;
};

/** Map API exchange connection responses to connected exchange IDs. */
export function connectedExchangeIds(
  connections: Partial<Record<ExchangeId, ExchangeConnectionSummary>>,
): ExchangeId[] {
  return exchangesSortedByAssetClass(
    EXCHANGES.filter((exchange) => connections[exchange.id]?.connected),
  ).map((exchange) => exchange.id);
}

export function connectedExchangesForAssetClass(
  assetClass: AssetClass,
  connections: Partial<Record<ExchangeId, ExchangeConnectionSummary>>,
): Exchange[] {
  const connected = new Set(connectedExchangeIds(connections));
  return exchangesForAssetClass(assetClass).filter((exchange) => connected.has(exchange.id));
}

export function exchangeName(exchangeId: string | null | undefined): string | null {
  if (!exchangeId) return null;
  return EXCHANGES.find((exchange) => exchange.id === exchangeId)?.name ?? exchangeId;
}

export function getExchange(exchangeId: ExchangeId): Exchange | undefined {
  return EXCHANGES.find((exchange) => exchange.id === exchangeId);
}
