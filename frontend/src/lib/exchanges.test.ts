import { describe, expect, it } from "vitest";
import {
  EXCHANGES,
  exchangesSortedByAssetClass,
  groupExchangesByAssetClass,
  primaryAssetClass,
} from "./exchanges";

describe("exchangesSortedByAssetClass", () => {
  it("orders by primary asset class, then specialized before multi-asset", () => {
    const ids = exchangesSortedByAssetClass().map((exchange) => exchange.id);
    expect(ids).toEqual(["oanda", "metatrader5", "ibkr", "binance", "coinbase", "kraken"]);
  });

  it("keeps every catalog exchange", () => {
    expect(exchangesSortedByAssetClass()).toHaveLength(EXCHANGES.length);
  });
});

describe("groupExchangesByAssetClass", () => {
  it("groups under the primary allowed asset type", () => {
    const groups = groupExchangesByAssetClass();
    expect(groups.map((group) => group.assetClass)).toEqual(["forex", "crypto"]);
    expect(groups[0]?.exchanges.map((exchange) => exchange.id)).toEqual([
      "oanda",
      "metatrader5",
      "ibkr",
    ]);
    expect(groups[1]?.exchanges.map((exchange) => exchange.id)).toEqual([
      "binance",
      "coinbase",
      "kraken",
    ]);
  });
});

describe("primaryAssetClass", () => {
  it("uses the first allowed asset class", () => {
    expect(primaryAssetClass(EXCHANGES.find((exchange) => exchange.id === "oanda")!)).toBe(
      "forex",
    );
    expect(primaryAssetClass(EXCHANGES.find((exchange) => exchange.id === "binance")!)).toBe(
      "crypto",
    );
  });
});
