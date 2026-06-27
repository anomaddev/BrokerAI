import type { AssetClass } from "../api/client";
import oandaLogo from "../assets/providers/oanda.png";

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
    id: "ibkr",
    name: "Interactive Brokers",
    description: "Multi-asset trading across global markets.",
    category: "Multi-asset",
    assetClasses: ["forex", "metals", "stocks", "crypto", "futures", "options"],
    available: false,
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

export function exchangesForAssetClass(assetClass: AssetClass): Exchange[] {
  return EXCHANGES.filter(
    (exchange) => exchange.available && exchange.assetClasses.includes(assetClass),
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
  return EXCHANGES.filter((exchange) => connections[exchange.id]?.connected).map(
    (exchange) => exchange.id,
  );
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
