import { useCallback, useEffect, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import { Link } from "react-router-dom";
import {
  api,
  type Strategy,
  type Trade,
  type TradeReconciliation,
} from "../api/client";
import TradesSuggestedPlaceholder from "../components/trades/TradesSuggestedPlaceholder";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  closeReasonLabel,
  directionClassName,
  directionLabel,
  exploreHrefForTrade,
  formatPrice,
  formatPnl,
  formatUnits,
  pnlClassName,
  reconciliationBadgeClassName,
  reconciliationBadgeLabel,
  reconciliationBannerClassName,
  reconciliationBannerText,
  tradeDuration,
  tradeStatusClassName,
  tradeStatusLabel,
} from "../lib/trades";

const POLL_INTERVAL_MS = 15_000;
const TRADE_LIMIT = 200;

type TradesTab = "trades" | "suggested";

const TABS: { id: TradesTab; label: string }[] = [
  { id: "trades", label: "Trades" },
  { id: "suggested", label: "Suggested" },
];

export default function Trades() {
  const { formatInstant } = useGeneralSettings();
  const [activeTab, setActiveTab] = useState<TradesTab>("trades");
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reconciliation, setReconciliation] = useState<TradeReconciliation | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [pairQuery, setPairQuery] = useState("");
  const [closingTradeId, setClosingTradeId] = useState<string | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);

  const loadTrades = useCallback(async () => {
    if (activeTab === "suggested") return;
    const params: {
      status: "all";
      limit: number;
      strategy_id?: string;
      pair?: string;
    } = {
      status: "all",
      limit: TRADE_LIMIT,
    };
    if (strategyFilter !== "all") params.strategy_id = strategyFilter;
    const trimmedPair = pairQuery.trim();
    if (trimmedPair) params.pair = trimmedPair;
    const data = await api.listTrades(params);
    setTrades(data.trades);
  }, [activeTab, strategyFilter, pairQuery]);

  const loadReconciliation = useCallback(async () => {
    const data = await api.getTradeReconciliation();
    setReconciliation(data);
  }, []);

  const handleCloseTrade = useCallback(
    async (trade: Trade) => {
      if (
        !window.confirm(
          `Close ${trade.direction} ${trade.pair} at market? This will close the broker position when OANDA is connected.`,
        )
      ) {
        return;
      }
      setClosingTradeId(trade.id);
      setCloseError(null);
      try {
        await api.closeTrade(trade.id);
        await Promise.all([loadTrades(), loadReconciliation()]);
      } catch (err) {
        setCloseError(err instanceof Error ? err.message : "Failed to close trade");
      } finally {
        setClosingTradeId(null);
      }
    },
    [loadTrades, loadReconciliation],
  );

  useEffect(() => {
    api
      .listStrategies()
      .then((data) => setStrategies(data.strategies))
      .catch(() => setStrategies([]));
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (activeTab === "suggested") {
        setLoading(false);
        return;
      }
      try {
        await Promise.all([loadTrades(), loadReconciliation()]);
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load trades");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    load();

    if (activeTab !== "trades") {
      return () => {
        cancelled = true;
      };
    }

    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeTab, loadTrades, loadReconciliation]);

  const showFilters = activeTab === "trades";

  return (
    <div>
      <h1 className="page-title">Trades</h1>
      <p className="settings-muted" style={{ marginBottom: "1rem" }}>
        Open and closed trades from the BrokerAI ledger, with broker reconciliation.
      </p>

      {reconciliation && activeTab === "trades" && (
        <div className={reconciliationBannerClassName(reconciliation.status)}>
          <p>{reconciliationBannerText(reconciliation)}</p>
          {!reconciliation.configured && (
            <Link to="/settings/connections" className="trades-reconcile-link">
              Connect OANDA
            </Link>
          )}
        </div>
      )}

      <div className="trades-toolbar">
        <div className="trades-tabs" role="tablist" aria-label="Trades sections">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`trades-tab${activeTab === tab.id ? " trades-tab--active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {showFilters && (
          <div className="trades-toolbar-filters">
            <div className="research-select-wrap">
              <select
                className="research-select"
                value={strategyFilter}
                onChange={(event) => setStrategyFilter(event.target.value)}
                aria-label="Filter by strategy"
              >
                <option value="all">All strategies</option>
                {strategies.map((strategy) => (
                  <option key={strategy.id} value={strategy.id}>
                    {strategy.name}
                  </option>
                ))}
              </select>
            </div>
            <input
              type="search"
              className="research-search"
              placeholder="Filter by pair…"
              value={pairQuery}
              onChange={(event) => setPairQuery(event.target.value)}
              aria-label="Filter by pair"
            />
          </div>
        )}
      </div>

      {activeTab === "suggested" ? (
        <TradesSuggestedPlaceholder />
      ) : (
        <div className="settings-panel">
          {loading && <p className="settings-muted">Loading trades…</p>}
          {error && !loading && <p className="settings-error">{error}</p>}
          {closeError && !loading && <p className="settings-error">{closeError}</p>}
          {!loading && !error && trades.length === 0 && (
            <p className="settings-muted">No trades yet.</p>
          )}

          {!loading && !error && trades.length > 0 && (
            <div className="research-table-wrap">
              <table className="research-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Opened</th>
                    <th>Closed</th>
                    <th>Strategy</th>
                    <th>Pair</th>
                    <th>Direction</th>
                    <th>Entry</th>
                    <th>Price</th>
                    <th>P/L</th>
                    <th>SL</th>
                    <th>TP</th>
                    <th>Units</th>
                    <th>Close reason</th>
                    <th>Duration</th>
                    <th>Sync</th>
                    <th className="research-actions-col" aria-hidden="true" />
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade, index) => {
                    const isOpen = trade.status === "open";
                    const prevTrade = index > 0 ? trades[index - 1] : null;
                    const isFirstClosed =
                      !isOpen && (prevTrade == null || prevTrade.status === "open");
                    const badge =
                      isOpen && reconciliation
                        ? reconciliation.ledger_badges[trade.id]
                        : undefined;
                    const market =
                      isOpen && reconciliation
                        ? reconciliation.ledger_market[trade.id]
                        : undefined;
                    return (
                      <tr
                        key={trade.id}
                        className={isFirstClosed ? "trades-row--section-start" : undefined}
                      >
                        <td>
                          <span className={tradeStatusClassName(trade.status)}>
                            {tradeStatusLabel(trade.status)}
                          </span>
                        </td>
                        <td className="settings-muted">
                          {trade.opened_at ? formatInstant(trade.opened_at) : "—"}
                        </td>
                        <td className="settings-muted">
                          {trade.closed_at ? formatInstant(trade.closed_at) : "—"}
                        </td>
                        <td>{trade.strategy_name}</td>
                        <td>{trade.pair}</td>
                        <td>
                          <span className={directionClassName(trade.direction)}>
                            {directionLabel(trade.direction)}
                          </span>
                        </td>
                        <td>{formatPrice(trade.entry_price)}</td>
                        <td>{isOpen ? formatPrice(market?.current_price) : "—"}</td>
                        <td className={isOpen ? pnlClassName(market?.unrealized_pl) : undefined}>
                          {isOpen ? formatPnl(market?.unrealized_pl) : "—"}
                        </td>
                        <td>{formatPrice(trade.stop_loss)}</td>
                        <td>{formatPrice(trade.take_profit)}</td>
                        <td>{formatUnits(trade.units)}</td>
                        <td>{isOpen ? "—" : closeReasonLabel(trade.close_reason)}</td>
                        <td>
                          {isOpen
                            ? "—"
                            : tradeDuration(trade.opened_at, trade.closed_at ?? null)}
                        </td>
                        <td>
                          {badge ? (
                            <span className={reconciliationBadgeClassName(badge)}>
                              {reconciliationBadgeLabel(badge)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="research-actions-cell">
                          <div className="research-row-actions">
                            <Link
                              to={exploreHrefForTrade(trade)}
                              className="research-action-btn"
                              title="Explore pair"
                              aria-label={`Explore ${trade.pair}`}
                            >
                              <ExternalLink size={15} strokeWidth={1.75} />
                            </Link>
                            {isOpen ? (
                              <button
                                type="button"
                                className="research-action-btn research-action-btn--danger"
                                title="Close trade"
                                aria-label={`Close ${trade.pair} trade`}
                                disabled={closingTradeId === trade.id}
                                onClick={() => void handleCloseTrade(trade)}
                              >
                                <X size={15} strokeWidth={1.75} />
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
