import type { EmaCrossoverParams } from "./defaults";

export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type CrossoverSignal = {
  time: number;
  type: "bullish" | "bearish";
  price: number;
  confidence: number;
  adx: number;
};

const BASE_PRICE = 1.085;

function pseudoRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

export function generateMockCandles(count = 120): Candle[] {
  const candles: Candle[] = [];
  let price = BASE_PRICE;
  const start = Math.floor(Date.now() / 1000) - count * 900;

  for (let i = 0; i < count; i += 1) {
    const drift = Math.sin(i / 8) * 0.0004 + (pseudoRandom(i) - 0.5) * 0.0012;
    const open = price;
    const close = open + drift;
    const wick = 0.0003 + pseudoRandom(i + 100) * 0.0008;
    const high = Math.max(open, close) + wick;
    const low = Math.min(open, close) - wick;
    candles.push({
      time: start + i * 900,
      open,
      high,
      low,
      close,
    });
    price = close;
  }

  return candles;
}

export function computeEma(candles: Candle[], period: number): { time: number; value: number }[] {
  if (candles.length === 0 || period < 1) return [];
  const k = 2 / (period + 1);
  const result: { time: number; value: number }[] = [];
  let ema = candles[0].close;

  for (let i = 0; i < candles.length; i += 1) {
    ema = i === 0 ? candles[i].close : candles[i].close * k + ema * (1 - k);
    if (i >= period - 1) {
      result.push({ time: candles[i].time, value: ema });
    }
  }

  return result;
}

export function computeAdx(candles: Candle[], period: number): { time: number; value: number }[] {
  if (candles.length < period + 2) return [];

  const result: { time: number; value: number }[] = [];
  let prevHigh = candles[0].high;
  let prevLow = candles[0].low;
  let prevClose = candles[0].close;
  let trSm = 0;
  let plusDmSm = 0;
  let minusDmSm = 0;
  let adxSm = 0;

  for (let i = 1; i < candles.length; i += 1) {
    const high = candles[i].high;
    const low = candles[i].low;
    const close = candles[i].close;
    const upMove = high - prevHigh;
    const downMove = prevLow - low;
    const plusDm = upMove > downMove && upMove > 0 ? upMove : 0;
    const minusDm = downMove > upMove && downMove > 0 ? downMove : 0;
    const tr = Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));

    if (i <= period) {
      trSm += tr;
      plusDmSm += plusDm;
      minusDmSm += minusDm;
    } else {
      trSm = trSm - trSm / period + tr;
      plusDmSm = plusDmSm - plusDmSm / period + plusDm;
      minusDmSm = minusDmSm - minusDmSm / period + minusDm;
    }

    if (i >= period) {
      const plusDi = trSm === 0 ? 0 : (100 * plusDmSm) / trSm;
      const minusDi = trSm === 0 ? 0 : (100 * minusDmSm) / trSm;
      const diSum = plusDi + minusDi;
      const dx = diSum === 0 ? 0 : (100 * Math.abs(plusDi - minusDi)) / diSum;
      adxSm = i === period ? dx : (adxSm * (period - 1) + dx) / period;
      result.push({ time: candles[i].time, value: Math.min(60, adxSm) });
    }

    prevHigh = high;
    prevLow = low;
    prevClose = close;
  }

  return result;
}

export function computeAtr(candles: Candle[], period: number): number {
  if (candles.length < period + 1) return 0.001;
  let sum = 0;
  for (let i = candles.length - period; i < candles.length; i += 1) {
    const prevClose = candles[i - 1].close;
    const tr = Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - prevClose),
      Math.abs(candles[i].low - prevClose),
    );
    sum += tr;
  }
  return sum / period;
}

export function findCrossovers(
  fast: { time: number; value: number }[],
  slow: { time: number; value: number }[],
  adx: { time: number; value: number }[],
): CrossoverSignal[] {
  const slowMap = new Map(slow.map((p) => [p.time, p.value]));
  const adxMap = new Map(adx.map((p) => [p.time, p.value]));
  const signals: CrossoverSignal[] = [];

  for (let i = 1; i < fast.length; i += 1) {
    const prevFast = fast[i - 1].value;
    const currFast = fast[i].value;
    const slowVal = slowMap.get(fast[i].time);
    const prevSlowVal = slowMap.get(fast[i - 1].time);
    if (slowVal === undefined || prevSlowVal === undefined) continue;

    const bullish = prevFast <= prevSlowVal && currFast > slowVal;
    const bearish = prevFast >= prevSlowVal && currFast < slowVal;
    if (!bullish && !bearish) continue;

    const adxVal = adxMap.get(fast[i].time) ?? 20;
    signals.push({
      time: fast[i].time,
      type: bullish ? "bullish" : "bearish",
      price: currFast,
      confidence: Math.min(95, Math.round(50 + adxVal)),
      adx: adxVal,
    });
  }

  return signals;
}

const PIP_SIZE = 0.0001;

function recentSwingLow(candles: Candle[], lookback: number): number {
  const slice = candles.slice(-Math.max(lookback, 2));
  return Math.min(...slice.map((c) => c.low));
}

export function computeSlTpDistances(
  params: EmaCrossoverParams,
  candles: Candle[],
  atr: number,
  entry: number,
): { slDistance: number; tpDistance: number } {
  let slDistance: number;
  switch (params.stopLossType) {
    case "fixed_pips":
      slDistance = params.slFixedPips * PIP_SIZE;
      break;
    case "structure": {
      const swingLow = recentSwingLow(candles, params.slStructureLookback);
      slDistance = Math.max(entry - swingLow, atr * 0.5);
      break;
    }
    default:
      slDistance = atr * params.slAtrMultiplier;
  }

  let tpDistance: number;
  switch (params.takeProfitType) {
    case "fixed_pips":
      tpDistance = params.tpFixedPips * PIP_SIZE;
      break;
    case "atr_based":
      tpDistance = atr * params.tpAtrMultiplier;
      break;
    default:
      tpDistance = slDistance * params.riskRewardRatio;
  }

  return { slDistance, tpDistance };
}

export function mockRiskAmount(riskPercent: number, slDistance: number, entry: number): string {
  const base = 1000 * (riskPercent / 100);
  const pctMove = entry > 0 ? slDistance / entry : 0.01;
  const adjusted = base * (pctMove / 0.01);
  return `$${Math.max(adjusted, 1).toFixed(2)}`;
}
