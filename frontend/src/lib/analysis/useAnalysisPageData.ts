import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Strategy, type StrategyAnalysisRun, type Trade } from "../../api/client";
import {
  findLatestBatchEvent,
  isPipelineBatchPending,
  shouldRefreshForBatchEvent,
} from "./batchRefresh";

const MAX_FETCH_LIMIT = 200;
const ACTIVITY_POLL_MS = 5_000;
const EXIT_POLL_MS = 15_000;

type UseAnalysisPageDataOptions = {
  strategyFilter: string;
  pairQuery: string;
};

export function useAnalysisPageData({
  strategyFilter,
  pairQuery,
}: UseAnalysisPageDataOptions) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [entryRuns, setEntryRuns] = useState<StrategyAnalysisRun[]>([]);
  const [exitRuns, setExitRuns] = useState<StrategyAnalysisRun[]>([]);
  const [openTrades, setOpenTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isBatchPending, setIsBatchPending] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  const acknowledgedBatchIdRef = useRef<string | null>(null);

  const buildRunParams = useCallback(() => {
    const params: {
      limit: number;
      strategy_id?: string;
      pair?: string;
    } = {
      limit: MAX_FETCH_LIMIT,
    };
    if (strategyFilter !== "all") {
      params.strategy_id = strategyFilter;
    }
    const trimmedPair = pairQuery.trim();
    if (trimmedPair) {
      params.pair = trimmedPair;
    }
    return params;
  }, [strategyFilter, pairQuery]);

  const fetchEntryRuns = useCallback(async () => {
    const data = await api.listStrategyAnalysisRuns({
      ...buildRunParams(),
      analysis_purpose: "entry",
    });
    setEntryRuns(data.runs);
  }, [buildRunParams]);

  const fetchExitRuns = useCallback(async () => {
    const data = await api.listStrategyAnalysisRuns({
      ...buildRunParams(),
      analysis_purpose: "exit",
    });
    setExitRuns(data.runs);
  }, [buildRunParams]);

  const fetchOpenTrades = useCallback(async () => {
    const data = await api.listTrades({ status: "open", limit: MAX_FETCH_LIMIT });
    setOpenTrades(data.trades);
  }, []);

  const reloadAll = useCallback(async () => {
    await Promise.all([fetchEntryRuns(), fetchExitRuns(), fetchOpenTrades()]);
  }, [fetchEntryRuns, fetchExitRuns, fetchOpenTrades]);

  const triggerReload = useCallback(() => {
    setReloadNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadStrategies() {
      try {
        const data = await api.listStrategies();
        if (!cancelled) {
          setStrategies(data.strategies);
        }
      } catch {
        if (!cancelled) {
          setStrategies([]);
        }
      }
    }

    void loadStrategies();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        await reloadAll();
        if (!cancelled) {
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load analysis runs");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [buildRunParams, reloadAll]);

  useEffect(() => {
    if (reloadNonce === 0) {
      return;
    }
    void reloadAll().catch(() => undefined);
  }, [reloadNonce, reloadAll]);

  useEffect(() => {
    let cancelled = false;

    async function pollActivity() {
      try {
        const data = await api.getBotActivity(50);
        if (cancelled) {
          return;
        }

        const latestBatch = findLatestBatchEvent(data.events);
        setIsBatchPending(
          isPipelineBatchPending(data.events, acknowledgedBatchIdRef.current),
        );

        if (shouldRefreshForBatchEvent(latestBatch, acknowledgedBatchIdRef.current)) {
          acknowledgedBatchIdRef.current = latestBatch!.id;
          setIsBatchPending(false);
          await Promise.all([fetchEntryRuns(), fetchExitRuns(), fetchOpenTrades()]);
        }
      } catch {
        // Activity polling is best-effort.
      }
    }

    void pollActivity();
    const interval = window.setInterval(() => {
      void pollActivity();
    }, ACTIVITY_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [fetchEntryRuns, fetchExitRuns, fetchOpenTrades]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void fetchExitRuns().catch(() => undefined);
      void fetchOpenTrades().catch(() => undefined);
    }, EXIT_POLL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [fetchExitRuns, fetchOpenTrades]);

  return {
    strategies,
    entryRuns,
    setEntryRuns,
    exitRuns,
    setExitRuns,
    openTrades,
    loading,
    error,
    isBatchPending,
    reloadAll,
    triggerReload,
  };
}
