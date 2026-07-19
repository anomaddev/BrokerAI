import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AssetClass,
  type ExchangeConnectionsResponse,
  type OandaAccountSummary,
  type OandaConnection,
  type Trade,
} from "../api/client";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  directionClassName,
  directionLabel,
  formatPnl,
  formatPrice,
  pnlClassName,
  tradeLastModifiedAt,
  tradeRealizedPl,
  tradeStatusClassName,
  tradeStatusKey,
  tradeStatusLabel,
} from "../lib/trades";
import DashboardSkeleton, { DashboardSummarySkeleton } from "./DashboardSkeleton";
import ExchangeEnvironmentBadge from "./ExchangeEnvironmentBadge";
import ExchangeLogo from "./ExchangeLogo";
import {
  EXCHANGES,
  connectedExchangeIds,
  type Exchange,
} from "../lib/exchanges";
import { loadAssetClassStatuses } from "../lib/assetClassStatus";
import TradeDetailOverlay from "./trades/TradeDetailOverlay";

const RECENT_TRADE_LIMIT = 10;

const ASSET_CLASS_SETTINGS: Record<AssetClass, string> = {
  forex: "/settings/broker/forex",
  metals: "/settings/broker/metals",
  stocks: "/settings/broker/stocks",
  crypto: "/settings/broker/crypto",
  futures: "/settings/broker/futures",
  options: "/settings/broker/options",
};

type AssetUsage = {
  assetClass: AssetClass;
  label: string;
  enabled: boolean;
};

type ConnectedExchangeOverview = {
  exchange: Exchange;
  connection: OandaConnection | null;
  enabledAssetClasses: AssetUsage[];
};

function parseAmount(value: string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

function formatMoney(value: string | null | undefined, currency: string | null | undefined): string {
  const amount = parseAmount(value);
  if (amount == null) return "—";
  const code = currency ?? "USD";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: code,
    maximumFractionDigits: 2,
  }).format(amount);
}

function plClass(value: string | null | undefined): string {
  const amount = parseAmount(value);
  if (amount == null || amount === 0) return "";
  return amount > 0 ? "dashboard-stat-value--positive" : "dashboard-stat-value--negative";
}

async function loadAssetUsages(): Promise<AssetUsage[]> {
  const rows = await loadAssetClassStatuses();
  return rows.map((row) => ({
    assetClass: row.assetClass,
    label: row.label,
    enabled: row.enabled,
  }));
}

async function loadPrimaryExchanges(): Promise<Partial<Record<AssetClass, string | null>>> {
  const [forex, metals, stocks, crypto, futures, options] = await Promise.all([
    api.getForexPairs(),
    api.getAssetSettings("metals"),
    api.getAssetSettings("stocks"),
    api.getAssetSettings("crypto"),
    api.getAssetSettings("futures"),
    api.getAssetSettings("options"),
  ]);

  return {
    forex: forex.primary_exchange ?? null,
    metals: metals.primary_exchange ?? null,
    stocks: stocks.primary_exchange ?? null,
    crypto: crypto.primary_exchange ?? null,
    futures: futures.primary_exchange ?? null,
    options: options.primary_exchange ?? null,
  };
}

function buildConnectedExchanges(
  connections: ExchangeConnectionsResponse,
  assetUsages: AssetUsage[],
  primaryExchanges: Partial<Record<AssetClass, string | null>>,
): ConnectedExchangeOverview[] {
  const connectedIds = connectedExchangeIds(connections);

  return EXCHANGES.filter((exchange) => connectedIds.includes(exchange.id)).map((exchange) => {
    const enabledAssetClasses = assetUsages.filter((usage) => {
      if (!usage.enabled) return false;
      return primaryExchanges[usage.assetClass] === exchange.id;
    });

    return {
      exchange,
      connection: exchange.id === "oanda" ? connections.oanda : null,
      enabledAssetClasses,
    };
  });
}

function tradeDisplayPnl(trade: Trade): unknown {
  const status = tradeStatusKey(trade);
  if (status === "open") return trade.unrealized_pl;
  return tradeRealizedPl(trade);
}

function OandaSummary({
  summary,
  loading,
  error,
}: {
  summary: OandaAccountSummary | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <DashboardSummarySkeleton />;
  }

  if (error) {
    return <p className="settings-error">{error}</p>;
  }

  if (!summary) return null;

  const currency = summary.currency;
  const activityParts = [
    summary.open_trade_count != null ? `${summary.open_trade_count} trades` : null,
    summary.open_position_count != null ? `${summary.open_position_count} positions` : null,
    summary.pending_order_count != null ? `${summary.pending_order_count} orders` : null,
  ].filter(Boolean);

  return (
    <div className="dashboard-summary">
      <div className="dashboard-stats">
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">Balance</span>
          <span className="dashboard-stat-value">{formatMoney(summary.balance, currency)}</span>
        </div>
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">NAV</span>
          <span className="dashboard-stat-value">{formatMoney(summary.nav, currency)}</span>
        </div>
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">Unrealized P/L</span>
          <span className={`dashboard-stat-value ${plClass(summary.unrealized_pl)}`}>
            {formatMoney(summary.unrealized_pl, currency)}
          </span>
        </div>
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">Realized P/L</span>
          <span className={`dashboard-stat-value ${plClass(summary.realized_pl)}`}>
            {formatMoney(summary.realized_pl, currency)}
          </span>
        </div>
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">Margin available</span>
          <span className="dashboard-stat-value">
            {formatMoney(summary.margin_available, currency)}
          </span>
        </div>
        <div className="dashboard-stat">
          <span className="dashboard-stat-label">Margin used</span>
          <span className="dashboard-stat-value">{formatMoney(summary.margin_used, currency)}</span>
        </div>
      </div>
      {activityParts.length > 0 && (
        <p className="settings-muted dashboard-card-muted">{activityParts.join(" · ")}</p>
      )}
    </div>
  );
}

function RecentTradesPanel({
  trades,
  loading,
  error,
  onSelectTrade,
}: {
  trades: Trade[];
  loading: boolean;
  error: string | null;
  onSelectTrade: (trade: Trade) => void;
}) {
  const { formatInstant } = useGeneralSettings();

  return (
    <section className="dashboard-recent-trades dashboard-card--enter">
      <div className="dashboard-recent-trades-head">
        <div className="dashboard-recent-trades-heading">
          <h2 className="dashboard-recent-trades-title">Recent trades</h2>
          <p className="settings-muted dashboard-recent-trades-subtitle">
            Last {RECENT_TRADE_LIMIT} trades
          </p>
        </div>
        <Link to="/trading/forex" className="dashboard-recent-trades-link">
          View all
        </Link>
      </div>

      {loading && (
        <p className="settings-muted dashboard-recent-trades-empty">Loading trades…</p>
      )}

      {!loading && error && <p className="settings-error">{error}</p>}

      {!loading && !error && trades.length === 0 && (
        <p className="settings-muted dashboard-recent-trades-empty">No trades yet.</p>
      )}

      {!loading && !error && trades.length > 0 && (
        <div className="research-table-wrap">
          <table className="research-table trades-table">
            <thead>
              <tr>
                <th scope="col">Status</th>
                <th scope="col">Time</th>
                <th scope="col">Strategy</th>
                <th scope="col">Pair</th>
                <th scope="col">Dir</th>
                <th scope="col">Entry</th>
                <th scope="col">P/L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const status = tradeStatusKey(trade);
                const lastModified = tradeLastModifiedAt(trade);
                const pnl = tradeDisplayPnl(trade);
                return (
                  <tr
                    key={trade.id}
                    className="trades-table-row--clickable"
                    onClick={() => onSelectTrade(trade)}
                  >
                    <td>
                      <span className={tradeStatusClassName(status)}>
                        {tradeStatusLabel(status)}
                      </span>
                    </td>
                    <td className="settings-muted">
                      {lastModified ? formatInstant(lastModified, "compact") : "—"}
                    </td>
                    <td>{trade.strategy_name}</td>
                    <td>{trade.pair}</td>
                    <td>
                      <span className={directionClassName(trade.direction)}>
                        {directionLabel(trade.direction)}
                      </span>
                    </td>
                    <td>{formatPrice(trade.entry_price)}</td>
                    <td className={pnlClassName(pnl)}>{formatPnl(pnl)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ExchangeDashboardCard({
  overview,
  oandaSummary,
  summaryLoading,
  summaryError,
  enterDelayMs = 0,
}: {
  overview: ConnectedExchangeOverview;
  oandaSummary: OandaAccountSummary | null;
  summaryLoading: boolean;
  summaryError: string | null;
  enterDelayMs?: number;
}) {
  const { exchange, connection, enabledAssetClasses } = overview;

  return (
    <article
      className="dashboard-card dashboard-card--enter"
      style={{ "--enter-delay": `${enterDelayMs}ms` } as CSSProperties}
    >
      <div className="dashboard-card-head">
        <ExchangeLogo exchange={exchange} size={40} />
        <div className="dashboard-card-title">
          <h2 className="dashboard-card-name">{exchange.name}</h2>
          <span className="settings-muted">{exchange.category}</span>
        </div>
        {connection?.connected && (
          <ExchangeEnvironmentBadge environment={connection.environment} />
        )}
      </div>

      {connection?.account_id && (
        <p className="settings-muted dashboard-card-muted">
          {oandaSummary?.alias ? `${oandaSummary.alias} · ` : ""}
          Account {connection.account_id}
        </p>
      )}

      {exchange.id === "oanda" && connection?.connected && (
        <OandaSummary summary={oandaSummary} loading={summaryLoading} error={summaryError} />
      )}

      <div className="dashboard-card-footer">
        <span className="dashboard-card-footer-label">Enabled for</span>
        {enabledAssetClasses.length > 0 ? (
          <ul className="dashboard-asset-tags">
            {enabledAssetClasses.map((usage) => (
              <li key={usage.assetClass}>
                <Link
                  to={ASSET_CLASS_SETTINGS[usage.assetClass]}
                  className="dashboard-asset-tag"
                >
                  {usage.label}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="settings-muted dashboard-card-muted">
            Not assigned to an enabled asset class.{" "}
            <Link to="/settings/broker/forex">Configure in Broker settings</Link>.
          </p>
        )}
      </div>
    </article>
  );
}

export default function ExchangeDashboard() {
  const [exchanges, setExchanges] = useState<ConnectedExchangeOverview[]>([]);
  const [oandaSummary, setOandaSummary] = useState<OandaAccountSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [recentTrades, setRecentTrades] = useState<Trade[]>([]);
  const [tradesLoading, setTradesLoading] = useState(false);
  const [tradesError, setTradesError] = useState<string | null>(null);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      setSummaryError(null);
      setTradesError(null);
      setOandaSummary(null);
      setRecentTrades([]);

      try {
        const [connections, assetUsages, primaryExchanges] = await Promise.all([
          api.getExchangeConnections(),
          loadAssetUsages(),
          loadPrimaryExchanges(),
        ]);
        if (cancelled) return;

        const overviews = buildConnectedExchanges(connections, assetUsages, primaryExchanges);
        setExchanges(overviews);
        setLoading(false);

        const oandaConnected = connections.oanda?.connected;
        if (oandaConnected) {
          setSummaryLoading(true);
          setTradesLoading(true);

          const accountPromise = (async () => {
            try {
              const summary = await api.getOandaAccountSummary();
              if (!cancelled) {
                setOandaSummary(summary);
              }
            } catch (err) {
              if (!cancelled) {
                setSummaryError(
                  err instanceof Error ? err.message : "Failed to load OANDA data",
                );
              }
            } finally {
              if (!cancelled) {
                setSummaryLoading(false);
              }
            }
          })();

          const tradesPromise = (async () => {
            try {
              const tradesResponse = await api.listTrades({
                status: "all",
                limit: RECENT_TRADE_LIMIT,
              });
              if (!cancelled) {
                setRecentTrades(tradesResponse.trades);
              }
            } catch (err) {
              if (!cancelled) {
                setTradesError(
                  err instanceof Error ? err.message : "Failed to load recent trades",
                );
              }
            } finally {
              if (!cancelled) {
                setTradesLoading(false);
              }
            }
          })();

          await Promise.all([accountPromise, tradesPromise]);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load dashboard");
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const oandaOverview = exchanges.find((overview) => overview.exchange.id === "oanda") ?? null;
  const otherExchanges = exchanges.filter((overview) => overview.exchange.id !== "oanda");

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">Dashboard</h1>
        <p className="dashboard-lead">Connected exchanges and live account summaries.</p>
      </header>

      {loading && <DashboardSkeleton layout="oanda-row" />}

      {!loading && error && (
        <p className="settings-error dashboard-message dashboard-message--enter">{error}</p>
      )}

      {!loading && !error && exchanges.length === 0 && (
        <p className="settings-muted dashboard-empty dashboard-message dashboard-message--enter">
          No exchanges connected yet.{" "}
          <Link to="/settings/connections">Connect an exchange</Link> under Settings →
          Connections.
        </p>
      )}

      {!loading && !error && exchanges.length > 0 && (
        <>
          {oandaOverview && (
            <div className="dashboard-oanda-row">
              <ExchangeDashboardCard
                overview={oandaOverview}
                oandaSummary={oandaSummary}
                summaryLoading={summaryLoading}
                summaryError={summaryError}
                enterDelayMs={0}
              />
              <RecentTradesPanel
                trades={recentTrades}
                loading={tradesLoading}
                error={tradesError}
                onSelectTrade={setSelectedTrade}
              />
            </div>
          )}

          {otherExchanges.length > 0 && (
            <div className="dashboard-grid">
              {otherExchanges.map((overview, index) => (
                <ExchangeDashboardCard
                  key={overview.exchange.id}
                  overview={overview}
                  oandaSummary={null}
                  summaryLoading={false}
                  summaryError={null}
                  enterDelayMs={(oandaOverview ? 1 : 0) * 70 + index * 70}
                />
              ))}
            </div>
          )}
        </>
      )}

      {selectedTrade && (
        <TradeDetailOverlay
          trade={selectedTrade}
          reconciliation={null}
          onClose={() => setSelectedTrade(null)}
        />
      )}
    </div>
  );
}
