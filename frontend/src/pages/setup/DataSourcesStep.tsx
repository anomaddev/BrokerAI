import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import {
  api,
  type MassiveConnection,
  type NewsApiConnection,
} from "../../api/client";
import ApiKeyDataSourceRow from "../../components/ApiKeyDataSourceRow";
import DataSourceLogo from "../../components/DataSourceLogo";
import {
  DATA_SOURCES,
  getDataSource,
  type DataSource,
  type DataSourceId,
} from "../../lib/dataSources";

type DataSourcesStepProps = {
  onContinue: () => void;
  onSkip: () => void;
  onBack: () => void;
};

const emptyNews: NewsApiConnection = {
  type: "newsapi",
  enabled: false,
  api_key: null,
  api_key_set: false,
};

const emptyMassive: MassiveConnection = {
  type: "massive",
  enabled: false,
  api_key: null,
  api_key_set: false,
};

function groupDataSourcesByCategory(sources: DataSource[]) {
  const order = ["Market data", "News"];
  const buckets = new Map<string, DataSource[]>();
  for (const source of sources) {
    const list = buckets.get(source.category) ?? [];
    list.push(source);
    buckets.set(source.category, list);
  }
  const ranked = [
    ...order.filter((category) => buckets.has(category)),
    ...[...buckets.keys()].filter((category) => !order.includes(category)).sort(),
  ];
  return ranked.map((category) => ({
    category,
    sources: buckets.get(category)!,
  }));
}

export default function DataSourcesStep({ onContinue, onSkip, onBack }: DataSourcesStepProps) {
  const groups = useMemo(() => groupDataSourcesByCategory(DATA_SOURCES), []);
  const [addedIds, setAddedIds] = useState<DataSourceId[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [connectingId, setConnectingId] = useState<DataSourceId | null>(null);
  const [newsapi, setNewsapi] = useState<NewsApiConnection>(emptyNews);
  const [massive, setMassive] = useState<MassiveConnection>(emptyMassive);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const connections = await api.getDataConnections();
        if (cancelled) return;
        setNewsapi(connections.newsapi ?? emptyNews);
        setMassive(connections.massive ?? emptyMassive);
        const next: DataSourceId[] = [];
        if (connections.newsapi?.api_key_set) next.push("newsapi");
        if (connections.massive?.api_key_set) next.push("massive");
        setAddedIds(next);
      } catch {
        // Preview / offline: keep empty tray.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const addedSources = addedIds
    .map((id) => getDataSource(id))
    .filter((source): source is DataSource => Boolean(source));
  const hasSource = addedSources.length > 0;
  const addedSet = new Set(addedIds);

  function openConnect(sourceId: DataSourceId) {
    const source = getDataSource(sourceId);
    if (!source?.available) return;
    setError("");
    setPickerOpen(false);
    setConnectingId(sourceId);
  }

  async function removeSource(sourceId: DataSourceId) {
    setError("");
    setBusy(true);
    try {
      if (sourceId === "newsapi") {
        setNewsapi(await api.deleteNewsApi());
      } else if (sourceId === "massive") {
        setMassive(await api.deleteMassive());
      }
      setAddedIds((current) => current.filter((id) => id !== sourceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove data source");
    } finally {
      setBusy(false);
    }
  }

  function markAdded(sourceId: DataSourceId) {
    setAddedIds((current) => (current.includes(sourceId) ? current : [...current, sourceId]));
  }

  function handlePrimary() {
    if (hasSource) onContinue();
    else onSkip();
  }

  const connectingSource = connectingId ? getDataSource(connectingId) : undefined;

  return (
    <div className="onboarding-welcome onboarding-welcome--exchange">
      <div className="onboarding-welcome-main">
        <div className="onboarding-welcome-copy">
          <h1>Connect data sources</h1>
          <p>Optional — add market data or news APIs now, or skip and configure later in Settings.</p>
        </div>

        {error && <div className="error">{error}</div>}

        <div className="onboarding-exchange-tray">
          {loading ? (
            <p className="onboarding-exchange-tray-empty">Loading…</p>
          ) : addedSources.length === 0 ? (
            <p className="onboarding-exchange-tray-empty">No data sources added yet</p>
          ) : (
            <ul className="onboarding-exchange-tray-list">
              {addedSources.map((source) => (
                <li key={source.id} className="onboarding-exchange-tray-item">
                  <DataSourceLogo source={source} size={32} />
                  <div className="onboarding-exchange-tray-item-text">
                    <strong>{source.name}</strong>
                    <span>{source.category}</span>
                  </div>
                  <button
                    type="button"
                    className="onboarding-exchange-tray-remove"
                    aria-label={`Remove ${source.name}`}
                    disabled={busy}
                    onClick={() => void removeSource(source.id)}
                  >
                    <X size={16} strokeWidth={2} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            className="onboarding-exchange-add"
            onClick={() => setPickerOpen(true)}
            disabled={busy || loading}
            aria-label="Add data source"
          >
            <Plus size={22} strokeWidth={2.25} />
            <span>Add data source</span>
          </button>
        </div>
      </div>

      <div className="onboarding-welcome-actions">
        <button
          type="button"
          className="btn btn-secondary onboarding-welcome-cta"
          onClick={onBack}
          disabled={busy || loading}
        >
          Back
        </button>
        <button
          type="button"
          className="btn onboarding-welcome-cta"
          onClick={handlePrimary}
          disabled={busy || loading}
        >
          {hasSource ? "Continue" : "Skip for now"}
        </button>
      </div>

      {pickerOpen && (
        <div
          className="onboarding-nested-overlay"
          role="presentation"
          onClick={() => setPickerOpen(false)}
        >
          <div
            className="onboarding-nested-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="onboarding-data-source-picker-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-welcome-copy">
              <h1 id="onboarding-data-source-picker-title">Add a data source</h1>
              <p>Choose a market data or news API to power research and charts.</p>
            </div>

            <div className="onboarding-exchange-groups">
              {groups.map((group) => (
                <section key={group.category} className="onboarding-exchange-group">
                  <h3 className="onboarding-exchange-group-title">{group.category}</h3>
                  <div className="onboarding-exchange-grid">
                    {group.sources.map((source) => {
                      const alreadyAdded = addedSet.has(source.id);
                      const disabled = !source.available || alreadyAdded || busy;
                      return (
                        <button
                          key={source.id}
                          type="button"
                          className={`onboarding-exchange-card${
                            disabled ? " is-disabled" : ""
                          }`}
                          disabled={disabled}
                          onClick={() => openConnect(source.id)}
                        >
                          <DataSourceLogo source={source} size={36} />
                          <div className="onboarding-exchange-card-text">
                            <strong>{source.name}</strong>
                            <span>{source.category}</span>
                            {alreadyAdded ? <em>Added</em> : null}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>

            <div className="onboarding-welcome-actions">
              <button
                type="button"
                className="btn btn-secondary onboarding-welcome-cta"
                onClick={() => setPickerOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {connectingSource && connectingId === "newsapi" && (
        <div
          className="onboarding-nested-overlay"
          role="presentation"
          onClick={() => setConnectingId(null)}
        >
          <div
            className="onboarding-nested-dialog onboarding-nested-dialog--wide"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-welcome-copy">
              <h1>Connect NewsAPI</h1>
              <p>Paste your API key, then test to save the connection.</p>
            </div>
            <ul className="onboarding-data-source-connect">
              <ApiKeyDataSourceRow
                source={connectingSource}
                connection={newsapi}
                enableLabel="Enable NewsAPI"
                apiKeyPlaceholder="Enter NewsAPI key"
                autoEnableOnConnect={false}
                onConnectionChange={(updated) => {
                  const next = updated as NewsApiConnection;
                  setNewsapi(next);
                  if (next.api_key_set) {
                    markAdded("newsapi");
                    setConnectingId(null);
                  }
                }}
                testConnection={api.testNewsApi}
                saveConnection={api.saveNewsApi}
                deleteConnection={api.deleteNewsApi}
              />
            </ul>
            <div className="onboarding-welcome-actions">
              <button
                type="button"
                className="btn btn-secondary onboarding-welcome-cta"
                onClick={() => setConnectingId(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {connectingSource && connectingId === "massive" && (
        <div
          className="onboarding-nested-overlay"
          role="presentation"
          onClick={() => setConnectingId(null)}
        >
          <div
            className="onboarding-nested-dialog onboarding-nested-dialog--wide"
            role="dialog"
            aria-modal="true"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="onboarding-welcome-copy">
              <h1>Connect Massive</h1>
              <p>Paste your API key, then test to save the connection.</p>
            </div>
            <ul className="onboarding-data-source-connect">
              <ApiKeyDataSourceRow
                source={connectingSource}
                connection={massive}
                enableLabel="Enable Massive"
                apiKeyPlaceholder="Enter Massive API key"
                autoEnableOnConnect={false}
                onConnectionChange={(updated) => {
                  const next = updated as MassiveConnection;
                  setMassive(next);
                  if (next.api_key_set) {
                    markAdded("massive");
                    setConnectingId(null);
                  }
                }}
                testConnection={api.testMassive}
                saveConnection={api.saveMassive}
                deleteConnection={api.deleteMassive}
              />
            </ul>
            <div className="onboarding-welcome-actions">
              <button
                type="button"
                className="btn btn-secondary onboarding-welcome-cta"
                onClick={() => setConnectingId(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
