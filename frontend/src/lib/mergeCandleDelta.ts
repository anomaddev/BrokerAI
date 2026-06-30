import type { CandleBar } from "../api/client";

export function mergeCandleDelta(
  existing: CandleBar[],
  delta: CandleBar[],
  maxBars: number,
): CandleBar[] {
  if (delta.length === 0) return existing;

  let next = [...existing];
  for (const bar of delta) {
    const last = next[next.length - 1];
    if (last && last.time === bar.time) {
      next[next.length - 1] = bar;
    } else if (!last || bar.time > last.time) {
      next.push(bar);
    }
  }

  if (next.length > maxBars) {
    return next.slice(next.length - maxBars);
  }

  return next;
}

export function isTailOnlyCandleChange(previous: CandleBar[], next: CandleBar[]): boolean {
  if (previous.length === 0 || next.length === 0) return false;
  if (next.length < previous.length) return false;
  if (next.length > previous.length + 1) return false;

  const sharedLength = Math.min(previous.length, next.length - 1);
  for (let index = 0; index < sharedLength; index += 1) {
    const prev = previous[index];
    const curr = next[index];
    if (
      prev.time !== curr.time ||
      prev.open !== curr.open ||
      prev.high !== curr.high ||
      prev.low !== curr.low ||
      prev.close !== curr.close
    ) {
      return false;
    }
  }

  return true;
}

export function tailCandleUpdates(previous: CandleBar[], next: CandleBar[]): CandleBar[] {
  if (!isTailOnlyCandleChange(previous, next)) return next;

  if (next.length === previous.length) {
    return [next[next.length - 1]];
  }

  return next.slice(previous.length);
}
