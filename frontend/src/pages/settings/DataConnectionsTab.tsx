import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type MassiveConnection,
  type NewsApiConnection,
  type OandaConnection,
} from "../../api/client";
import ApiKeyDataSourceRow from "../../components/ApiKeyDataSourceRow";
import DataSourceLogo from "../../components/DataSourceLogo";
import ExchangeEnvironmentBadge from "../../components/ExchangeEnvironmentBadge";
import ExchangeLogo from "../../components/ExchangeLogo";
import OandaConnectionOverlay from "../../components/OandaConnectionOverlay";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import { connectedDataSourceIds, DATA_SOURCES, type DataSourceId } from "./dataSources";
import { EXCHANGES, groupExchangesByAssetClass } from "./exchanges";

export default function DataConnectionsTab() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newsapi, setNewsapi] = useState<NewsApiConnection | null>(null);
  const [massive, setMassive] = useState<MassiveConnection | null>(null);
  const [oanda, setOanda] = useState<OandaConnection | null>(null);
  const [visibleSourceIds, setVisibleSourceIds] = useState<DataSourceId[]>([]);
  const [dataSourceChooserOpen, setDataSourceChooserOpen] = useState(false);
  const [exchangeChooserOpen, setExchangeChooserOpen] = useState(false);
  const [oandaOverlayOpen, setOandaOverlayOpen] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [data, exchanges] = await Promise.all([
        api.getDataConnections(),
        api.getExchangeConnections(),
      ]);
      setNewsapi(data.newsapi);
      setMassive(
        data.massive ?? {
          type: "massive",
          enabled: false,
          api_key: null,
          api_key_set: false,
        },
      );
      setOanda(exchanges.oanda);
      const connected = connectedDataSourceIds({
        newsapi: data.newsapi,
        massive: data.massive,
      });
      setVisibleSourceIds(connected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data connections");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const dataSourceConnections = {
    newsapi: newsapi ?? undefined,
    massive: massive ?? undefined,
  };

  const addableSources = DATA_SOURCES.filter(
    (source) => source.available && !visibleSourceIds.includes(source.id),
  );

  function addDataSource(id: DataSourceId) {
    setVisibleSourceIds((current) => (current.includes(id) ? current : [...current, id]));
    setDataSourceChooserOpen(false);
  }

  function removeDataSource(id: DataSourceId) {
    setVisibleSourceIds((current) => current.filter((sourceId) => sourceId !== id));
  }

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Connections"
        description="Manage the external services BrokerAI connects to."
        error={error}
      />

      <div className="settings-panel-body">
        {loading ? (
          <p className="settings-muted">Loading…</p>
        ) : (
          <>
            <section className="settings-section">
              <div className="settings-panel-header">
                <div className="settings-section-intro">
                  <h3 className="settings-subsection-title">Data Sources</h3>
                  <p className="settings-panel-desc">
                    External data APIs used by the Data Manager and Researcher bots.
                  </p>
                </div>
                {addableSources.length > 0 && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setDataSourceChooserOpen(true)}
                  >
                    Add data source
                  </button>
                )}
              </div>
              {visibleSourceIds.length === 0 && (
                <p className="settings-muted">No data sources connected yet.</p>
              )}
              {visibleSourceIds.length > 0 && (
                <ul className="model-list">
                  {visibleSourceIds.map((sourceId) => {
                    const source = DATA_SOURCES.find((item) => item.id === sourceId);
                    const connection = dataSourceConnections[sourceId];
                    if (!source || !connection) return null;

                    if (sourceId === "newsapi") {
                      return (
                        <ApiKeyDataSourceRow
                          key={source.id}
                          source={source}
                          connection={connection}
                          enableLabel="Enable NewsAPI"
                          apiKeyPlaceholder="Enter NewsAPI key"
                          onConnectionChange={(updated) => setNewsapi(updated as NewsApiConnection)}
                          onDisconnected={() => removeDataSource("newsapi")}
                          testConnection={api.testNewsApi}
                          saveConnection={api.saveNewsApi}
                          deleteConnection={api.deleteNewsApi}
                        />
                      );
                    }

                    return (
                      <ApiKeyDataSourceRow
                        key={source.id}
                        source={source}
                        connection={connection}
                        enableLabel="Enable Massive"
                        apiKeyPlaceholder="Enter Massive API key"
                        onConnectionChange={(updated) => setMassive(updated as MassiveConnection)}
                        onDisconnected={() => removeDataSource("massive")}
                        testConnection={api.testMassive}
                        saveConnection={api.saveMassive}
                        deleteConnection={api.deleteMassive}
                      />
                    );
                  })}
                </ul>
              )}
            </section>

            <section className="settings-section">
              <div className="settings-panel-header">
                <div className="settings-section-intro">
                  <h3 className="settings-subsection-title">Exchanges</h3>
                  <p className="settings-panel-desc">
                    Connect broker and exchange accounts for the trading bots to execute against.
                    After connecting an account here, set it as the primary exchange on the matching
                    asset page under{" "}
                    <Link to="/settings/broker/forex">Settings → Broker</Link> (Forex, Crypto,
                    etc.).
                  </p>
                </div>
                <button type="button" className="btn" onClick={() => setExchangeChooserOpen(true)}>
                  Add exchange
                </button>
              </div>
              {!oanda?.connected && (
                <p className="settings-muted">No exchange accounts connected yet.</p>
              )}
              {oanda?.connected && (
                <ul className="model-list">
                  {EXCHANGES.filter((exchange) => exchange.id === "oanda" && oanda?.connected).map(
                    (exchange) => (
                      <li key={exchange.id} className="model-list-item exchange-list-item">
                        <ExchangeLogo exchange={exchange} size={40} />
                        <div className="model-list-main">
                          <strong>{exchange.name}</strong>
                          <span className="settings-muted">
                            {exchange.category} · {oanda?.account_id}
                          </span>
                        </div>
                        <div className="model-list-actions">
                          {oanda && <ExchangeEnvironmentBadge environment={oanda.environment} />}
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => setOandaOverlayOpen(true)}
                          >
                            Manage
                          </button>
                        </div>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </section>
          </>
        )}
      </div>

      {dataSourceChooserOpen && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => setDataSourceChooserOpen(false)}
        >
          <div
            className="model-overlay-dialog model-overlay-dialog--wide"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 className="model-overlay-title">Add data source</h4>
            <p className="model-overlay-desc">Choose an external data API to connect.</p>
            <div className="model-provider-grid">
              {addableSources.map((source) => (
                <button
                  key={source.id}
                  type="button"
                  className="model-provider-card"
                  onClick={() => addDataSource(source.id)}
                >
                  <DataSourceLogo
                    source={source}
                    size={36}
                    className="exchange-logo model-provider-logo"
                  />
                  <span className="model-provider-card-label">{source.name}</span>
                  <span className="model-provider-card-desc">{source.description}</span>
                </button>
              ))}
            </div>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDataSourceChooserOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {exchangeChooserOpen && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => setExchangeChooserOpen(false)}
        >
          <div
            className="model-overlay-dialog model-overlay-dialog--wide"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 className="model-overlay-title">Add exchange</h4>
            <p className="model-overlay-desc">Choose a broker or exchange to connect.</p>
            <div className="exchange-chooser-groups">
              {groupExchangesByAssetClass().map((group) => (
                <section key={group.assetClass} className="exchange-chooser-group">
                  <h5 className="exchange-chooser-group-title">{group.label}</h5>
                  <div className="model-provider-grid">
                    {group.exchanges.map((exchange) => (
                      <button
                        key={exchange.id}
                        type="button"
                        className="model-provider-card"
                        disabled={!exchange.available}
                        onClick={() => {
                          if (exchange.id === "oanda") {
                            setExchangeChooserOpen(false);
                            setOandaOverlayOpen(true);
                          }
                        }}
                      >
                        <ExchangeLogo
                          exchange={exchange}
                          size={36}
                          className="exchange-logo model-provider-logo"
                        />
                        <span className="model-provider-card-label">{exchange.name}</span>
                        <span className="model-provider-card-desc">{exchange.description}</span>
                        {!exchange.available && (
                          <span className="exchange-coming-soon">Coming soon</span>
                        )}
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setExchangeChooserOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {oandaOverlayOpen && oanda && (
        <OandaConnectionOverlay
          connection={oanda}
          onClose={() => setOandaOverlayOpen(false)}
          onSaved={(updated) => {
            setOanda(updated);
            setOandaOverlayOpen(false);
          }}
        />
      )}
    </div>
  );
}
