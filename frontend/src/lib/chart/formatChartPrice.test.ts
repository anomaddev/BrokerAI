import { describe, expect, it } from "vitest";
import { chartPriceFormat, chartPricePrecision, formatChartPrice } from "./formatChartPrice";

describe("chartPricePrecision", () => {
  it("uses forex-friendly decimals for majors", () => {
    expect(chartPricePrecision(1.08452)).toBe(5);
    expect(formatChartPrice(1.08452)).toBe("1.08452");
  });

  it("uses fewer decimals for larger instruments", () => {
    expect(chartPricePrecision(149.123)).toBe(3);
    expect(chartPricePrecision(2345.67)).toBe(2);
  });
});

describe("chartPriceFormat", () => {
  it("sets precision and minMove for the price scale", () => {
    expect(chartPriceFormat(1.08)).toEqual({
      type: "price",
      precision: 5,
      minMove: 0.00001,
    });
  });
});
