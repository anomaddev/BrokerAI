import type { PriceFormat } from "lightweight-charts";

/** Decimal places for axis / legend labels based on price magnitude. */
export function chartPricePrecision(value: number): number {
  const abs = Math.abs(value);
  if (abs >= 1000) return 2;
  if (abs >= 100) return 3;
  if (abs >= 10) return 4;
  if (abs >= 1) return 5;
  return 6;
}

export function formatChartPrice(value: number): string {
  return value.toFixed(chartPricePrecision(value));
}

/**
 * lightweight-charts price scale format for a representative market price.
 * Forex majors (~1.08) get 5 decimals; JPY crosses (~150) get 3; metals (~2000) get 2.
 */
export function chartPriceFormat(samplePrice: number): PriceFormat {
  const precision = chartPricePrecision(samplePrice);
  return {
    type: "price",
    precision,
    minMove: 10 ** -precision,
  };
}
