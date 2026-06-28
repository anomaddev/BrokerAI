import type { FilterSpec } from "../types";

export function computeBuilderMinCandles(input: {
  signalType?: string;
  fastEma?: number;
  slowEma?: number;
  adxPeriod?: number;
  atrPeriod?: number;
  adxFilter?: boolean;
  atrFilter?: boolean;
  slStructureLookback?: number;
}): number {
  const periods: number[] = [];
  if (input.signalType === "monthly_high" || input.signalType === "monthly_low") {
    periods.push(31);
  }
  if (input.fastEma) periods.push(input.fastEma);
  if (input.slowEma) periods.push(input.slowEma);
  if (input.adxFilter && input.adxPeriod) periods.push(input.adxPeriod);
  if (input.atrFilter && input.atrPeriod) periods.push(input.atrPeriod);
  if (input.slStructureLookback) periods.push(input.slStructureLookback);

  const warmup = periods.length > 0 ? Math.max(...periods) : 50;
  return Math.min(2000, warmup * 3);
}

export function defaultAdxFilter(): Extract<FilterSpec, { type: "adx" }> {
  return {
    id: "adx",
    type: "adx",
    enabled: true,
    period: 14,
    threshold: 25,
    compare: "gte",
  };
}

export function defaultAtrFilter(): Extract<FilterSpec, { type: "atr" }> {
  return {
    id: "atr",
    type: "atr",
    enabled: true,
    period: 14,
    min_value: 0.0008,
  };
}
