import { useCallback, useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import {
  api,
  type CandleBar,
  type Strategy,
  type Trade,
  type TradeReconciliation,
} from "../../api/client";
import ToggleSwitch from "../ToggleSwitch";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import { formatAppInstant, type AppInstantStyle } from "../../lib/formatTime";
import { decomposeStrategyToIndicatorLayers } from "../../lib/chart/chartOverlayState";
import { TIMEFRAME_LABELS } from "../../lib/strategyParams";
import {
  directionClassName,
  directionLabel,
  tradeLastModifiedAt,
  tradeStatusClassName,
  tradeStatusKey,
  tradeStatusLabel,
} from "../../lib/trades";
import {
  buildTradeCandleWindow,
  tradeChartTimeframe,
} from "../../lib/trades/tradeCandleWindow";
import TradeCandleChart from "./TradeCandleChart";
import TradeDetailPanel from "./TradeDetailPanel";

const TITLE_ID = "trade-detail-title";

type TradeDetailOverlayProps = {
  trade: Trade;
  reconciliation: TradeReconciliation | null;
  onClose: () => void;
};

export default function TradeDetailOverlay({
  trade: initialTrade,
  reconciliation,
  onClose,
}: TradeDetailOverlayProps) {
  const { showUtc: globalShowUtc, effectiveTimezone } = useGeneralSettings();
  const [viewUtc, setViewUtc] = useState(globalShowUtc);
  const [trade, setTrade] = useState(initialTrade);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [candleWindowBounds, setCandleWindowBounds] = useState<{
    since: string;
    until: string;
    displaySince: string;
    displayUntil: string;
  } | null>(null);
  const [candlesLoading, setCandlesLoading] = useState(true);
  const [strategyLoading, setStrategyLoading] = useState(false);
  const [candlesError, setCandlesError] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    setTrade(initialTrade);
    setFetchError(null);
  }, [initialTrade]);

  useEffect(() => {
    setViewUtc(globalShowUtc);
  }, [initialTrade.id, globalShowUtc]);

  const tradeTimeOptions = useMemo(
    () => ({
      showUtc: viewUtc,
      timeZone: effectiveTimezone,
    }),
    [viewUtc, effectiveTimezone],
  );

  const formatTradeInstant = useCallback(
    (value: string | number | Date | null | undefined, style: AppInstantStyle = "full") =>
      formatAppInstant(value, tradeTimeOptions, style),
    [tradeTimeOptions],
  );

  useEffect(() => {
    let cancelled = false;
    void api
      .getTrade(initialTrade.id)
      .then((fresh) => {
        if (!cancelled) {
          setTrade(fresh);
          setFetchError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : "Failed to refresh trade");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [initialTrade.id]);

  useEffect(() => {
    if (!trade.strategy_id) {
      setStrategy(null);
      setStrategyLoading(false);
      return;
    }

    let cancelled = false;
    setStrategyLoading(true);
    void api
      .getStrategy(trade.strategy_id)
      .then((loaded) => {
        if (!cancelled) setStrategy(loaded);
      })
      .catch(() => {
        if (!cancelled) setStrategy(null);
      })
      .finally(() => {
        if (!cancelled) setStrategyLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [trade.strategy_id]);

  const timeframe = useMemo(
    () =>
      tradeChartTimeframe(
        trade.timeframe ?? strategy?.params?.timeframe ?? strategy?.timeframe,
      ),
    [trade.timeframe, strategy],
  );

  const overlayItems = useMemo(
    () => (strategy ? decomposeStrategyToIndicatorLayers(strategy) : []),
    [strategy],
  );

  const candleWindow = useMemo(
    () =>
      buildTradeCandleWindow(trade, {
        since: candleWindowBounds?.since,
        until: candleWindowBounds?.until,
        displaySince: candleWindowBounds?.displaySince,
        displayUntil: candleWindowBounds?.displayUntil,
      }),
    [trade, candleWindowBounds],
  );

  const chartLoading = candlesLoading || (Boolean(trade.strategy_id) && strategyLoading);

  useEffect(() => {
    let cancelled = false;
    setCandlesLoading(true);
    setCandlesError(null);
    setCandleWindowBounds(null);

    void api
      .getTradeCandles(trade.id)
      .then((response) => {
        if (cancelled) return;
        setCandles(response.candles);
        setCandleWindowBounds({
          since: response.since,
          until: response.until,
          displaySince: response.display_since,
          displayUntil: response.display_until,
        });
        if (response.candles.length === 0) {
          setCandlesError("No candle data for this trade window.");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setCandles([]);
          setCandlesError(err instanceof Error ? err.message : "Failed to load chart data");
        }
      })
      .finally(() => {
        if (!cancelled) setCandlesLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [trade.id]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const status = tradeStatusKey(trade);
  const lastModified = tradeLastModifiedAt(trade);

  return (
    <div
      className="trades-detail-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby={TITLE_ID}
      onClick={onClose}
    >
      <div className="trades-detail-shell" onClick={(event) => event.stopPropagation()}>
        <header className="trade-detail-header">
          <div className="trade-detail-header-main">
            <h2 className="trade-detail-title" id={TITLE_ID}>
              {trade.pair}
            </h2>
            <span className={directionClassName(trade.direction)}>
              {directionLabel(trade.direction)}
            </span>
            <span className={tradeStatusClassName(status)}>{tradeStatusLabel(status)}</span>
          </div>
          <div className="trade-detail-header-actions">
            <label className="trade-detail-utc-toggle">
              <span className="trade-detail-utc-toggle-label">View UTC</span>
              <ToggleSwitch
                label="View UTC"
                checked={viewUtc}
                onChange={setViewUtc}
              />
            </label>
            <button
              type="button"
              className="trade-detail-close-btn"
              onClick={onClose}
              aria-label="Close trade details"
            >
              <X size={18} strokeWidth={1.75} />
            </button>
          </div>
        </header>

        <p className="trade-detail-subtitle settings-muted">
          {trade.strategy_name}
          {` · ${TIMEFRAME_LABELS[timeframe]}`}
          {lastModified ? ` · Last modified ${formatTradeInstant(lastModified, "compact")}` : ""}
        </p>

        {fetchError && <p className="settings-error trade-detail-fetch-error">{fetchError}</p>}

        <div className="trades-detail-layout">
          <div
            className={`trades-detail-chart-col${
              chartLoading ? " trades-detail-chart-col--loading" : ""
            }`}
          >
            {chartLoading ? (
              <div
                className="trades-detail-chart-loading explore-chart-status explore-chart-status--loading"
                role="status"
                aria-live="polite"
              >
                Loading chart…
              </div>
            ) : null}
            <TradeCandleChart
              trade={trade}
              timeframe={timeframe}
              candles={candles}
              loading={candlesLoading}
              error={candlesError}
              overlayItems={overlayItems}
              candleWindow={candleWindow}
              timeOptions={tradeTimeOptions}
            />
          </div>
          <aside className="trades-detail-panel-col">
            <TradeDetailPanel
              trade={trade}
              reconciliation={reconciliation}
              onClose={onClose}
              formatInstant={formatTradeInstant}
            />
          </aside>
        </div>
      </div>
    </div>
  );
}
