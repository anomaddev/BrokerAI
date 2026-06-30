import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type CandleBar } from "../api/client";
import type { ChartOverlayItem } from "../lib/chart/chartOverlayState";
import ExploreCandleChart from "../components/explore/ExploreCandleChart";
import ExploreChartControls from "../components/explore/ExploreChartControls";
import ExploreSidebar from "../components/explore/ExploreSidebar";
import PairSearchAutocomplete from "../components/explore/PairSearchAutocomplete";
import RecentPairCards from "../components/explore/RecentPairCards";
import { useCandleCloseRefresh } from "../hooks/useCandleCloseRefresh";
import { useCandleRevisionStream } from "../hooks/useCandleRevisionStream";
import {
  DEFAULT_HISTORY_DURATION,
  DEFAULT_TIMEFRAME,
  barsForHistoryDuration,
  parseExploreTimeframe,
  parseHistoryDuration,
  type HistoryDuration,
} from "../lib/exploreChartPresets";
import { mergeCandleDelta } from "../lib/mergeCandleDelta";
import {
  loadRecentPairs,
  recordRecentPair,
  type RecentPair,
} from "../lib/exploreRecentPairs";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";

export default function Explore() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialPair = searchParams.get("pair");
  const initialTimeframe = parseExploreTimeframe(searchParams.get("timeframe"));
  const initialHistory = parseHistoryDuration(searchParams.get("history"));

  const [selectedPair, setSelectedPair] = useState<string | null>(initialPair);
  const [timeframe, setTimeframe] = useState<Timeframe>(initialTimeframe);
  const [historyDuration, setHistoryDuration] = useState<HistoryDuration>(initialHistory);
  const [recentPairs, setRecentPairs] = useState<RecentPair[]>(() => loadRecentPairs());
  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chartOverlayItems, setChartOverlayItems] = useState<ChartOverlayItem[]>([]);

  const barCount = useMemo(
    () => barsForHistoryDuration(timeframe, historyDuration),
    [timeframe, historyDuration],
  );

  const syncSearchParams = useCallback(
    (pair: string | null, nextTimeframe: Timeframe, nextHistory: HistoryDuration) => {
      const params = new URLSearchParams();
      if (pair) params.set("pair", pair);
      if (nextTimeframe !== DEFAULT_TIMEFRAME) params.set("timeframe", nextTimeframe);
      if (nextHistory !== DEFAULT_HISTORY_DURATION) params.set("history", nextHistory);
      setSearchParams(params, { replace: true });
    },
    [setSearchParams],
  );

  useEffect(() => {
    if (!initialPair) return;
    setRecentPairs(recordRecentPair(initialPair));
  }, [initialPair]);

  const selectPair = useCallback(
    (symbol: string) => {
      setSelectedPair(symbol);
      setRecentPairs(recordRecentPair(symbol));
      syncSearchParams(symbol, timeframe, historyDuration);
    },
    [syncSearchParams, timeframe, historyDuration],
  );

  const fetchCandles = useCallback(
    async (options: { silent?: boolean } = {}) => {
      if (!selectedPair) return;

      if (!options.silent) {
        setLoading(true);
        setError(null);
      }

      try {
        const data = await api.getCandles({
          symbol: selectedPair,
          timeframe,
          limit: barCount,
        });
        setCandles(data.candles);
        if (!options.silent) setError(null);
      } catch (err) {
        if (!options.silent) {
          setCandles([]);
          setError(err instanceof Error ? err.message : "Failed to load candles");
        }
      } finally {
        if (!options.silent) setLoading(false);
      }
    },
    [selectedPair, timeframe, barCount],
  );

  useEffect(() => {
    if (!selectedPair) {
      setCandles([]);
      setError(null);
      setLoading(false);
      return;
    }

    void fetchCandles();
  }, [selectedPair, timeframe, barCount, fetchCandles]);

  const lastCandleTime = candles[candles.length - 1]?.time ?? null;

  const handleCandleDelta = useCallback(
    (delta: CandleBar[]) => {
      setCandles((current) => mergeCandleDelta(current, delta, barCount));
    },
    [barCount],
  );

  const { connected: streamConnected } = useCandleRevisionStream({
    enabled: Boolean(selectedPair),
    symbol: selectedPair,
    timeframe,
    barCount,
    after: lastCandleTime,
    onDelta: handleCandleDelta,
  });

  useCandleCloseRefresh({
    enabled: Boolean(selectedPair) && !streamConnected,
    timeframe,
    onRefresh: () => fetchCandles({ silent: true }),
  });

  const handleTimeframeChange = useCallback(
    (nextTimeframe: Timeframe) => {
      setTimeframe(nextTimeframe);
      syncSearchParams(selectedPair, nextTimeframe, historyDuration);
    },
    [selectedPair, historyDuration, syncSearchParams],
  );

  const handleHistoryChange = useCallback(
    (nextHistory: HistoryDuration) => {
      setHistoryDuration(nextHistory);
      syncSearchParams(selectedPair, timeframe, nextHistory);
    },
    [selectedPair, timeframe, syncSearchParams],
  );

  return (
    <div className="explore-page">
      <div className="explore-toolbar">
        <div className="explore-toolbar-primary">
          <PairSearchAutocomplete selectedSymbol={selectedPair} onSelect={selectPair} />
          <RecentPairCards
            items={recentPairs}
            selectedSymbol={selectedPair}
            onSelect={selectPair}
          />
        </div>

        {selectedPair ? (
          <div className="explore-toolbar-secondary">
            <div className="explore-symbol-meta">
              <span className="explore-symbol">{selectedPair}</span>
              <span className="explore-symbol-detail">
                {TIMEFRAME_LABELS[timeframe]} · {historyDuration} · {barCount.toLocaleString()} bars
              </span>
            </div>
            <ExploreChartControls
              timeframe={timeframe}
              historyDuration={historyDuration}
              onTimeframeChange={handleTimeframeChange}
              onHistoryChange={handleHistoryChange}
            />
          </div>
        ) : (
          <p className="explore-hint">Search a forex pair to explore candle data.</p>
        )}
      </div>

      <div className="explore-body">
        <div className="explore-chart-area">
          <ExploreCandleChart
            symbol={selectedPair}
            timeframe={timeframe}
            candles={candles}
            loading={loading}
            error={error}
            overlayItems={chartOverlayItems}
          />
        </div>
        <ExploreSidebar
          symbol={selectedPair}
          chartTimeframe={timeframe}
          overlayItems={chartOverlayItems}
          onOverlayItemsChange={setChartOverlayItems}
        />
      </div>
    </div>
  );
}
