import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AssetClass,
  type ExchangeConnectionsResponse,
  type InstrumentExposureRow,
  type OandaAccountSummary,
  type OandaConnection,
} from "../api/client";
import DashboardSkeleton, { DashboardSummarySkeleton } from "./DashboardSkeleton";
import ExchangeEnvironmentBadge from "./ExchangeEnvironmentBadge";
import ExchangeLogo from "./ExchangeLogo";
import {
  EXCHANGES,
  connectedExchangeIds,
  type Exchange,
} from "../lib/exchanges";
import { ASSET_CLASS_LABELS, loadAssetClassStatuses } from "../lib/assetClassStatus";

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

function formatExposurePair(symbol: string): string {
  return symbol.includes("/") ? symbol : symbol.replace("_", "/");
}

function ExposureSummary({
  rows,
  loading,
  error,
}: {
  rows: InstrumentExposureRow[];
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <p className="settings-muted dashboard-card-muted">Loading exposure…</p>;
  }
  if (error) {
    return <p className="settings-error">{error}</p>;
  }
  if (rows.length === 0) {
    return <p className="settings-muted dashboard-card-muted">No open instrument exposure.</p>;
  }

  return (
    <div className="dashboard-exposure">
      <h3 className="dashboard-exposure-title">Open exposure</h3>
      <ul className="dashboard-exposure-list">
        {rows.map((row) => (
          <li key={`${row.symbol}-${row.direction}`} className="dashboard-exposure-row">
            <Link
              to={`/trades?status=open&pair=${encodeURIComponent(formatExposurePair(row.symbol))}`}
              className="dashboard-exposure-link"
            >
              <span className="dashboard-exposure-symbol">{formatExposurePair(row.symbol)}</span>
              <span className="dashboard-exposure-meta">
                {row.direction} · {row.total_qty.toLocaleString()} units
              </span>
              <span className={`dashboard-exposure-pl ${plClass(row.unrealized_pl)}`}>
                {row.unrealized_pl == null ? "—" : formatMoney(row.unrealized_pl)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
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

function ExchangeDashboardCard({
  overview,
  oandaSummary,
  summaryLoading,
  summaryError,
  exposureRows,
  exposureLoading,
  exposureError,
  enterDelayMs = 0,
}: {
  overview: ConnectedExchangeOverview;
  oandaSummary: OandaAccountSummary | null;
  summaryLoading: boolean;
  summaryError: string | null;
  exposureRows: InstrumentExposureRow[];
  exposureLoading: boolean;
  exposureError: string | null;
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
        <>
          <OandaSummary summary={oandaSummary} loading={summaryLoading} error={summaryError} />
          <ExposureSummary rows={exposureRows} loading={exposureLoading} error={exposureError} />
        </>
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
  const [exposureRows, setExposureRows] = useState<InstrumentExposureRow[]>([]);
  const [exposureLoading, setExposureLoading] = useState(false);
  const [exposureError, setExposureError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError(null);
      setSummaryError(null);
      setOandaSummary(null);

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
          setExposureLoading(true);
          try {
            const [summary, exposure] = await Promise.all([
              api.getOandaAccountSummary(),
              api.getInstrumentExposure("oanda"),
            ]);
            if (!cancelled) {
              setOandaSummary(summary);
              setExposureRows(exposure.exposure);
            }
          } catch (err) {
            if (!cancelled) {
              const message = err instanceof Error ? err.message : "Failed to load OANDA data";
              setSummaryError(message);
              setExposureError(message);
            }
          } finally {
            if (!cancelled) {
              setSummaryLoading(false);
              setExposureLoading(false);
            }
          }
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

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1 className="dashboard-title">Dashboard</h1>
        <p className="dashboard-lead">Connected exchanges and live account summaries.</p>
      </header>

      {loading && <DashboardSkeleton cards={2} />}

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
        <div className="dashboard-grid">
          {exchanges.map((overview, index) => (
            <ExchangeDashboardCard
              key={overview.exchange.id}
              overview={overview}
              oandaSummary={overview.exchange.id === "oanda" ? oandaSummary : null}
              summaryLoading={overview.exchange.id === "oanda" ? summaryLoading : false}
              summaryError={overview.exchange.id === "oanda" ? summaryError : null}
              exposureRows={overview.exchange.id === "oanda" ? exposureRows : []}
              exposureLoading={overview.exchange.id === "oanda" ? exposureLoading : false}
              exposureError={overview.exchange.id === "oanda" ? exposureError : null}
              enterDelayMs={index * 70}
            />
          ))}
        </div>
      )}
    </div>
  );
}
