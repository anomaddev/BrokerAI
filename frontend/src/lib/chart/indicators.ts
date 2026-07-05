import { priceFromSource, type ChartCandle } from "./candleBars";
import type { PriceSource } from "../strategyParams";

export type IndicatorPoint = {
  time: number;
  value: number;
};

export function computeEmaSeries(
  candles: ChartCandle[],
  period: number,
  source: PriceSource = "close",
): IndicatorPoint[] {
  if (candles.length === 0 || period < 1) return [];
  const k = 2 / (period + 1);
  const result: IndicatorPoint[] = [];
  let ema = priceFromSource(candles[0], source);

  for (let i = 0; i < candles.length; i += 1) {
    const price = priceFromSource(candles[i], source);
    ema = i === 0 ? price : price * k + ema * (1 - k);
    if (i >= period - 1) {
      result.push({ time: candles[i].time, value: ema });
    }
  }

  return result;
}

export function computeSmaSeries(
  candles: ChartCandle[],
  period: number,
  source: PriceSource = "close",
): IndicatorPoint[] {
  if (candles.length < period || period < 1) return [];
  const result: IndicatorPoint[] = [];

  for (let i = period - 1; i < candles.length; i += 1) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j += 1) {
      sum += priceFromSource(candles[j], source);
    }
    result.push({ time: candles[i].time, value: sum / period });
  }

  return result;
}

export function computeRsiSeries(
  candles: ChartCandle[],
  period: number,
  source: PriceSource = "close",
): IndicatorPoint[] {
  if (candles.length < period + 1 || period < 1) return [];

  const result: IndicatorPoint[] = [];
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 1; i < candles.length; i += 1) {
    const change = priceFromSource(candles[i], source) - priceFromSource(candles[i - 1], source);
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;

    if (i <= period) {
      avgGain += gain;
      avgLoss += loss;
      if (i === period) {
        avgGain /= period;
        avgLoss /= period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        result.push({ time: candles[i].time, value: 100 - 100 / (1 + rs) });
      }
      continue;
    }

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push({ time: candles[i].time, value: 100 - 100 / (1 + rs) });
  }

  return result;
}

export function computeAdxSeries(candles: ChartCandle[], period: number): IndicatorPoint[] {
  if (candles.length < period + 2) return [];

  const result: IndicatorPoint[] = [];
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
      result.push({ time: candles[i].time, value: adxSm });
    }

    prevHigh = high;
    prevLow = low;
    prevClose = close;
  }

  return result;
}

export type CrossoverSignal = {
  time: number;
  type: "bullish" | "bearish";
  price: number;
  confidence: number;
  adx: number;
};

export function normalizeConfidenceThreshold(minConfidence: number): number {
  if (!Number.isFinite(minConfidence) || minConfidence <= 0) return 0;
  return minConfidence <= 1 ? Math.round(minConfidence * 100) : minConfidence;
}

export function findEmaCrossovers(
  fast: IndicatorPoint[],
  slow: IndicatorPoint[],
  adx: IndicatorPoint[],
  minConfidence = 0,
): CrossoverSignal[] {
  const slowMap = new Map(slow.map((point) => [point.time, point.value]));
  const adxMap = new Map(adx.map((point) => [point.time, point.value]));
  const signals: CrossoverSignal[] = [];
  const minConfidencePct = normalizeConfidenceThreshold(minConfidence);

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
    const confidence = Math.min(95, Math.round(50 + adxVal));
    if (confidence < minConfidencePct) continue;

    signals.push({
      time: fast[i].time,
      type: bullish ? "bullish" : "bearish",
      price: currFast,
      confidence,
      adx: adxVal,
    });
  }

  return signals;
}
