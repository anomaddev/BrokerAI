import { useEffect, useRef, useState } from "react";
import { api, type CandleBar } from "../api/client";
import type { Timeframe } from "../lib/strategyParams";

type CandleUpdatedEvent = {
  type: "candle_updated";
  symbol: string;
  timeframe: string;
  latest_time: string;
};

type UseCandleRevisionStreamOptions = {
  enabled: boolean;
  symbol: string | null;
  timeframe: Timeframe;
  barCount: number;
  after: string | null;
  onDelta: (candles: CandleBar[]) => void;
};

const MAX_RECONNECT_DELAY_MS = 30_000;

export function useCandleRevisionStream({
  enabled,
  symbol,
  timeframe,
  barCount,
  after,
  onDelta,
}: UseCandleRevisionStreamOptions) {
  const [connected, setConnected] = useState(false);
  const afterRef = useRef(after);
  const onDeltaRef = useRef(onDelta);
  afterRef.current = after;
  onDeltaRef.current = onDelta;

  const hasAfter = Boolean(after);

  useEffect(() => {
    if (!enabled || !symbol || !hasAfter) {
      setConnected(false);
      return undefined;
    }

    let cancelled = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let reconnectDelay = 1_000;

    const fetchDelta = async () => {
      const currentAfter = afterRef.current;
      if (!currentAfter) return;

      try {
        const data = await api.getCandleDelta({
          symbol,
          timeframe,
          after: currentAfter,
        });
        if (data.candles.length > 0) {
          onDeltaRef.current(data.candles);
        }
      } catch {
        // Ignore transient delta failures; SSE will retry on next revision.
      }
    };

    const connect = () => {
      if (cancelled) return;

      const params = new URLSearchParams({
        symbol,
        timeframe,
        bar_count: String(barCount),
      });
      source = new EventSource(`/api/market-data/stream?${params.toString()}`);

      source.onopen = () => {
        reconnectDelay = 1_000;
        setConnected(true);
      };

      source.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as CandleUpdatedEvent;
          if (payload.type !== "candle_updated") return;
          void fetchDelta();
        } catch {
          // Ignore malformed SSE payloads.
        }
      };

      source.onerror = () => {
        setConnected(false);
        source?.close();
        source = null;
        if (cancelled) return;

        reconnectTimer = window.setTimeout(() => {
          reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
          connect();
        }, reconnectDelay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      setConnected(false);
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      source?.close();
    };
  }, [enabled, symbol, timeframe, barCount, hasAfter]);

  return { connected };
}
