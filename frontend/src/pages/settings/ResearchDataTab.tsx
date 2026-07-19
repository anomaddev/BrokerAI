import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AiModel,
  type ModelConnection,
  type NewsApiConnection,
  type ResearchDataSources,
  type ResearchSettings,
  type RssFeedCategory,
} from "../../api/client";
import ToggleSwitch from "../../components/ToggleSwitch";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import useAutoSave from "../../hooks/useAutoSave";
import { getProvider, providerLabel } from "./modelProviders";

const DEFAULT_DATA_SOURCES: ResearchDataSources = {
  newsapi: true,
  rss_enabled: false,
  rss_categories: {},
  web_search_enabled: false,
  web_search_model_id: null,
  x_search_enabled: false,
  x_search_model_id: null,
};

function normalizeDataSources(raw?: Partial<ResearchDataSources> | null): ResearchDataSources {
  return {
    ...DEFAULT_DATA_SOURCES,
    ...(raw ?? {}),
    rss_categories: { ...(raw?.rss_categories ?? {}) },
  };
}

type DataSnapshot = {
  researchSettings: ResearchSettings | null;
  models: AiModel[];
  modelConnections: ModelConnection[];
  dataSources: ResearchDataSources;
  newsApiAvailable: boolean;
  rssCategories: RssFeedCategory[];
};

function capabilitiesFor(model: AiModel, connections: ModelConnection[]) {
  const connection = connections.find((item) => item.model_id === model.id);
  if (connection && connection.available_capabilities.length > 0) {
    return connection.available_capabilities.map((cap) => ({
      id: cap,
      label: connection.capability_labels[cap] ?? cap,
    }));
  }
  return getProvider(model.type)?.connectionCapabilities ?? [];
}

function modelsWithCapability(
  models: AiModel[],
  connections: ModelConnection[],
  capability: string,
): AiModel[] {
  return models
    .filter((m) => m.enabled)
    .filter((model) => {
      const connection = connections.find((c) => c.model_id === model.id);
      if (!connection || !connection.available_capabilities.includes(capability)) return false;
      return Boolean(connection.capabilities[capability]);
    });
}

export default function ResearchDataTab() {
  const [models, setModels] = useState<AiModel[]>([]);
  const [modelConnections, setModelConnections] = useState<ModelConnection[]>([]);
  const [newsApi, setNewsApi] = useState<NewsApiConnection | null>(null);
  const [dataSources, setDataSources] = useState<ResearchDataSources>(DEFAULT_DATA_SOURCES);
  const [rssCategories, setRssCategories] = useState<RssFeedCategory[]>([]);
  const [enabledFeedCount, setEnabledFeedCount] = useState(0);
  const [totalFeedCount, setTotalFeedCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const newsApiAvailable = Boolean(newsApi?.api_key_set);

  const snapshotRef = useRef<DataSnapshot>({
    researchSettings: null,
    models: [],
    modelConnections: [],
    dataSources: DEFAULT_DATA_SOURCES,
    newsApiAvailable: false,
    rssCategories: [],
  });

  snapshotRef.current = {
    researchSettings: snapshotRef.current.researchSettings,
    models,
    modelConnections,
    dataSources,
    newsApiAvailable,
    rssCategories,
  };

  const capabilityModels = useMemo(
    () =>
      models.filter((model) => {
        if (!model.enabled) return false;
        return capabilitiesFor(model, modelConnections).length > 0;
      }),
    [models, modelConnections],
  );

  const persistDataSettings = useCallback(async () => {
    const snapshot = snapshotRef.current;
    const base = snapshot.researchSettings;
    if (!base) return;

    const modelsWithCaps = snapshot.modelConnections.filter(
      (model) => model.available_capabilities.length > 0,
    );
    await Promise.all(
      modelsWithCaps.map((model) =>
        api.saveModelConnection(model.model_id, { capabilities: model.capabilities }),
      ),
    );

    const webModel = modelsWithCapability(snapshot.models, snapshot.modelConnections, "web_search")[0] ?? null;
    const xModel = modelsWithCapability(snapshot.models, snapshot.modelConnections, "x_search")[0] ?? null;

    const derivedDataSources: ResearchDataSources = {
      newsapi: snapshot.dataSources.newsapi && snapshot.newsApiAvailable,
      rss_enabled: snapshot.dataSources.rss_enabled,
      rss_categories: Object.fromEntries(
        snapshot.rssCategories.map((category) => [category.id, category.enabled]),
      ),
      web_search_enabled: Boolean(webModel),
      web_search_model_id: webModel?.id ?? null,
      x_search_enabled: Boolean(xModel),
      x_search_model_id: xModel?.id ?? null,
    };

    const saved = await api.saveResearchSettings({
      contributor_models: base.contributor_models,
      synthesis_model_id: base.synthesis_model_id,
      synthesis_model_name: base.synthesis_model_name,
      synthesis_reasoning_effort: base.synthesis_reasoning_effort,
      data_sources: derivedDataSources,
      daily_report_enabled: base.daily_report_enabled,
      daily_report_market_id: base.daily_report_market_id,
      daily_report_market_offset_hours: base.daily_report_market_offset_hours,
    });

    snapshotRef.current = {
      ...snapshotRef.current,
      researchSettings: saved,
      dataSources: normalizeDataSources(saved.data_sources),
    };
    setDataSources(normalizeDataSources(saved.data_sources));
  }, []);

  const { saveStatus, saveNow, scheduleSave, markReady, markNotReady, error: saveError } =
    useAutoSave({
      onSave: persistDataSettings,
      canSave: () => !loading && snapshotRef.current.researchSettings !== null,
    });

  useEffect(() => {
    (async () => {
      markNotReady();
      setLoading(true);
      try {
        const [modelsData, connectionsData, settings, rssCatalog] = await Promise.all([
          api.listModels(),
          api.getDataConnections(),
          api.getResearchSettings(),
          api.getRssFeeds(),
        ]);
        setModels(modelsData.models);
        setModelConnections(connectionsData.models ?? []);
        setNewsApi(connectionsData.newsapi ?? null);
        const normalizedSources = normalizeDataSources(settings.data_sources);
        setDataSources(normalizedSources);
        setRssCategories(rssCatalog.categories);
        setEnabledFeedCount(rssCatalog.enabled_feed_count);
        setTotalFeedCount(rssCatalog.total_feeds);
        snapshotRef.current = {
          researchSettings: settings,
          models: modelsData.models,
          modelConnections: connectionsData.models ?? [],
          dataSources: normalizedSources,
          newsApiAvailable: Boolean(connectionsData.newsapi?.api_key_set),
          rssCategories: rssCatalog.categories,
        };
        markReady();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data settings");
      } finally {
        setLoading(false);
      }
    })();
  }, [markNotReady, markReady]);

  function updateRssEnabled(checked: boolean) {
    setDataSources((prev) => {
      const next = { ...prev, rss_enabled: checked };
      snapshotRef.current = { ...snapshotRef.current, dataSources: next };
      return next;
    });
    saveNow();
  }

  function updateRssCategory(categoryId: string, checked: boolean) {
    setRssCategories((prev) => {
      const next = prev.map((category) =>
        category.id === categoryId ? { ...category, enabled: checked } : category,
      );
      const enabledCount = next.filter((category) => category.enabled).reduce(
        (sum, category) => sum + category.feed_count,
        0,
      );
      setEnabledFeedCount(enabledCount);
      snapshotRef.current = { ...snapshotRef.current, rssCategories: next };
      return next;
    });
    scheduleSave(400);
  }

  function updateNewsApi(checked: boolean) {
    setDataSources((prev) => {
      const next = { ...prev, newsapi: checked };
      snapshotRef.current = { ...snapshotRef.current, dataSources: next };
      return next;
    });
    saveNow();
  }

  function updateModelCapability(modelId: string, capability: string, checked: boolean) {
    setModelConnections((prev) => {
      const next = prev.map((model) =>
        model.model_id === modelId
          ? { ...model, capabilities: { ...model.capabilities, [capability]: checked } }
          : model,
      );
      snapshotRef.current = { ...snapshotRef.current, modelConnections: next };
      return next;
    });
    scheduleSave(400);
  }

  const headerError = error ?? saveError;

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Data"
        description={
          <>Configure news, market data, and model search capabilities for research reports.</>
        }
        error={headerError}
        saveStatus={saveStatus}
      />

      <div className="settings-panel-body">
        {loading ? (
          <p className="settings-muted">Loading…</p>
        ) : (
          <div className="research-stack">
            <section className="settings-card research-card">
              <div className="settings-card-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">NewsAPI</h3>
                  <p className="settings-muted">
                    Financial news articles fetched for each research run.
                  </p>
                </div>
              </div>

              <div className="research-source-list">
                <div className="research-source-row">
                  <div className="research-source-main">
                    <span className="research-source-name">NewsAPI.org</span>
                    <span className="settings-muted">
                      {newsApiAvailable ? (
                        "API key configured in Connections"
                      ) : (
                        <>
                          No API key —{" "}
                          <Link to="/settings/connections">add one in Connections</Link>
                        </>
                      )}
                    </span>
                  </div>
                  <ToggleSwitch
                    label="Use NewsAPI"
                    checked={dataSources.newsapi && newsApiAvailable}
                    disabled={!newsApiAvailable}
                    onChange={updateNewsApi}
                  />
                </div>
              </div>
            </section>

            <section className="settings-card research-card">
              <div className="settings-card-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">RSS feeds</h3>
                  <p className="settings-muted">
                    Public financial and geopolitical RSS feeds for research runs. No API key
                    required.{" "}
                    <a href={api.getRssFeedsOpmlUrl()} download="brokerai-rss-feeds.opml">
                      Download OPML
                    </a>
                  </p>
                </div>
              </div>

              <div className="research-source-list">
                <div className="research-source-row">
                  <div className="research-source-main">
                    <span className="research-source-name">RSS aggregation</span>
                    <span className="settings-muted">
                      {enabledFeedCount} of {totalFeedCount} feeds active across enabled
                      categories
                    </span>
                  </div>
                  <ToggleSwitch
                    label="Use RSS feeds"
                    checked={dataSources.rss_enabled}
                    onChange={updateRssEnabled}
                  />
                </div>
              </div>

              {dataSources.rss_enabled && (
                <ul className="research-rss-category-list">
                  {rssCategories.map((category) => (
                    <li key={category.id} className="research-rss-category-item">
                      <label className="research-rss-category-label">
                        <input
                          type="checkbox"
                          checked={category.enabled}
                          onChange={(event) =>
                            updateRssCategory(category.id, event.target.checked)
                          }
                        />
                        <span className="research-rss-category-copy">
                          <span className="research-source-name">{category.label}</span>
                          <span className="settings-muted">
                            {category.description} · {category.feed_count} feeds
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="settings-card research-card">
              <div className="settings-card-header">
                <div className="settings-section-intro">
                  <h3 className="research-card-title">Model capabilities</h3>
                  <p className="settings-muted">
                    Optional live search via enabled models. The first model with each capability
                    enabled is used during research runs.
                  </p>
                </div>
              </div>

              {capabilityModels.length === 0 ? (
                <div className="research-empty-callout">
                  <p className="settings-muted">
                    No enabled sources with search capabilities. Add Grok under{" "}
                    <Link to="/settings/models">Settings → Models</Link>.
                  </p>
                </div>
              ) : (
                <ul className="research-model-checklist">
                  {capabilityModels.map((model) => {
                    const provider = getProvider(model.type);
                    const connection = modelConnections.find((c) => c.model_id === model.id);
                    const capabilities = capabilitiesFor(model, modelConnections);
                    const rowDisabled = !model.enabled || !connection?.api_key_set;

                    return (
                      <li
                        key={model.id}
                        className={`research-model-checklist-item${
                          rowDisabled ? " research-model-checklist-item--disabled" : ""
                        }`}
                      >
                        <div className="research-model-row-head">
                          {provider && (
                            <img
                              src={provider.logo}
                              alt=""
                              className="research-model-checklist-logo"
                              width={32}
                              height={32}
                            />
                          )}
                          <span className="research-model-checklist-meta">
                            <span className="research-model-checklist-title">{model.title}</span>
                            <span className="settings-muted">
                              {providerLabel(model.type)}
                              {connection && !connection.api_key_set ? " · API key missing" : ""}
                            </span>
                          </span>
                        </div>

                        <div className="research-model-capabilities">
                          <span className="research-capabilities-label">Capabilities</span>
                          <div className="research-capabilities-list">
                            {capabilities.map((capability) => {
                              const capChecked = Boolean(connection?.capabilities[capability.id]);
                              return (
                                <label
                                  key={capability.id}
                                  className={`research-capability-checkbox${
                                    capChecked ? " research-capability-checkbox--checked" : ""
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={capChecked}
                                    disabled={rowDisabled}
                                    onChange={(e) =>
                                      updateModelCapability(model.id, capability.id, e.target.checked)
                                    }
                                  />
                                  <span>{capability.label}</span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
