import type { AutoscaleInfoProvider, ISeriesApi } from "lightweight-charts";
import type { Trade } from "../../api/client";
import { tradeExitPrice, tradeIsOpen } from "../trades";

function tradeFillPrices(trade: Trade): number[] {
  const prices: number[] = [];
  if (Number.isFinite(trade.entry_price)) {
    prices.push(trade.entry_price);
  }
  if (!tradeIsOpen(trade)) {
    const exitPrice = tradeExitPrice(trade);
    if (exitPrice != null && Number.isFinite(exitPrice)) {
      prices.push(exitPrice);
    }
  }
  return prices;
}

/** Keep broker fill prices inside the candlestick autoscale range. */
export function createTradeFillAutoscaleProvider(trade: Trade): AutoscaleInfoProvider {
  const fillPrices = tradeFillPrices(trade);

  return (original) => {
    const base = original();
    if (!base || fillPrices.length === 0 || !base.priceRange) {
      return base;
    }

    return {
      ...base,
      priceRange: {
        minValue: Math.min(base.priceRange.minValue, ...fillPrices),
        maxValue: Math.max(base.priceRange.maxValue, ...fillPrices),
      },
    };
  };
}

export function applyTradeFillAutoscale(
  series: ISeriesApi<"Candlestick">,
  trade: Trade,
): void {
  series.applyOptions({
    autoscaleInfoProvider: createTradeFillAutoscaleProvider(trade),
  });
}

export function clearTradeFillAutoscale(series: ISeriesApi<"Candlestick">): void {
  series.applyOptions({
    autoscaleInfoProvider: undefined,
  });
}
