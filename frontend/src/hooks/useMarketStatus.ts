import { useEffect, useSyncExternalStore } from "react";
import { api, type MarketStatusResponse } from "../api/client";

/** Single shared poll for Massive market status (matches backend cache TTL). */
export const MARKET_STATUS_POLL_INTERVAL_MS = 60_000;

const UNAVAILABLE: MarketStatusResponse = {
  enabled: true,
  available: false,
  sessions: [],
};

let cachedStatus: MarketStatusResponse | null = null;
let loadPromise: Promise<MarketStatusResponse> | null = null;
let pollTimer: ReturnType<typeof setInterval> | undefined;
let subscriberCount = 0;
const listeners = new Set<() => void>();

function emitChange() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): MarketStatusResponse | null {
  return cachedStatus;
}

async function refreshMarketStatus(): Promise<MarketStatusResponse> {
  if (loadPromise) {
    return loadPromise;
  }

  loadPromise = api
    .getMarketStatus()
    .then((data) => {
      cachedStatus = data;
      emitChange();
      return data;
    })
    .catch(() => {
      cachedStatus = UNAVAILABLE;
      emitChange();
      return UNAVAILABLE;
    })
    .finally(() => {
      loadPromise = null;
    });

  return loadPromise;
}

function startPolling() {
  if (pollTimer !== undefined) {
    return;
  }
  void refreshMarketStatus();
  pollTimer = setInterval(() => {
    void refreshMarketStatus();
  }, MARKET_STATUS_POLL_INTERVAL_MS);
}

function stopPolling() {
  if (subscriberCount > 0 || pollTimer === undefined) {
    return;
  }
  clearInterval(pollTimer);
  pollTimer = undefined;
}

/** Shared market-status snapshot; at most one API request per minute app-wide. */
export function useMarketStatus(): MarketStatusResponse | null {
  const status = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useEffect(() => {
    subscriberCount += 1;
    startPolling();
    return () => {
      subscriberCount -= 1;
      stopPolling();
    };
  }, []);

  return status;
}
