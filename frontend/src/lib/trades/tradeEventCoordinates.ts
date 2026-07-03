import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import type { ChartCandle } from "../chart/candleBars";

export type CandleTimeBracket = {
  leftTime: number;
  rightTime: number;
};

/** Locate the half-open candle bracket ``[leftTime, rightTime)`` containing *unixSeconds*. */
export function findCandleTimeBracket(
  candles: ChartCandle[],
  unixSeconds: number,
): CandleTimeBracket | null {
  if (candles.length === 0) return null;

  const first = candles[0].time;
  const last = candles[candles.length - 1].time;
  if (unixSeconds < first) return null;

  for (let index = 0; index < candles.length - 1; index += 1) {
    const leftTime = candles[index].time;
    const rightTime = candles[index + 1].time;
    if (unixSeconds >= leftTime && unixSeconds < rightTime) {
      return { leftTime, rightTime };
    }
  }

  if (unixSeconds >= last) {
    return { leftTime: last, rightTime: last };
  }

  return null;
}

export function interpolateBarCoordinate(
  unixSeconds: number,
  bracket: CandleTimeBracket,
  xLeft: number,
  xRight: number,
): number {
  const { leftTime, rightTime } = bracket;
  if (rightTime <= leftTime) return xLeft;
  const ratio = (unixSeconds - leftTime) / (rightTime - leftTime);
  return xLeft + ratio * (xRight - xLeft);
}

/**
 * Map a fill instant to an x pixel within the candle bar that contains it.
 *
 * ``timeToCoordinate`` alone can snap to the wrong bar open when the instant
 * falls mid-bar; bracket interpolation keeps entry/exit aligned with the bar
 * that actually contains the fill.
 */
export function resolveTradeEventTimeCoordinate(
  chart: IChartApi,
  candles: ChartCandle[],
  unixSeconds: number,
): number | null {
  if (candles.length === 0) return null;

  const exactBar = candles.find((candle) => candle.time === unixSeconds);
  if (exactBar) {
    return chart.timeScale().timeToCoordinate(exactBar.time as UTCTimestamp);
  }

  const bracket = findCandleTimeBracket(candles, unixSeconds);
  if (!bracket) return null;

  const xLeft = chart.timeScale().timeToCoordinate(bracket.leftTime as UTCTimestamp);
  if (xLeft === null) return null;

  if (bracket.rightTime === bracket.leftTime) {
    return xLeft;
  }

  const xRight = chart.timeScale().timeToCoordinate(bracket.rightTime as UTCTimestamp);
  if (xRight === null) return null;

  return interpolateBarCoordinate(unixSeconds, bracket, xLeft, xRight);
}

export function resolveTradeEventPriceCoordinate(
  series: ISeriesApi<"Candlestick">,
  price: number,
): number | null {
  if (!Number.isFinite(price)) return null;
  return series.priceToCoordinate(price);
}
