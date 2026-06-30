import { useEffect, useRef } from "react";
import { nextCandleCloseAtMs } from "../lib/candleSchedule";
import type { Timeframe } from "../lib/strategyParams";

/** Extra delay after the candle-close boundary so the Data Manager can sync first. */
const BOT_SYNC_GRACE_MS = 4_000;

type UseCandleCloseRefreshOptions = {
  enabled: boolean;
  timeframe: Timeframe;
  onRefresh: () => void | Promise<void>;
};

export function msUntilNextCandleRefresh(timeframe: Timeframe, nowMs = Date.now()): number {
  return Math.max(0, nextCandleCloseAtMs(nowMs, timeframe) - nowMs + BOT_SYNC_GRACE_MS);
}

export function useCandleCloseRefresh({
  enabled,
  timeframe,
  onRefresh,
}: UseCandleCloseRefreshOptions) {
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  useEffect(() => {
    if (!enabled) return;

    let timeoutId: number | null = null;
    let cancelled = false;

    const schedule = () => {
      if (cancelled) return;
      const delay = msUntilNextCandleRefresh(timeframe);
      timeoutId = window.setTimeout(async () => {
        if (cancelled) return;
        if (document.visibilityState === "hidden") {
          schedule();
          return;
        }
        try {
          await onRefreshRef.current();
        } finally {
          schedule();
        }
      }, delay);
    };

    schedule();

    const handleVisibility = () => {
      if (document.visibilityState !== "visible" || cancelled) return;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
      void onRefreshRef.current().finally(schedule);
    };

    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [enabled, timeframe]);
}
