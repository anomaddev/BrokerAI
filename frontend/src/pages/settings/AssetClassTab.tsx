import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type AssetClass } from "../../api/client";
import ForexPairPriorityList from "../../components/ForexPairPriorityList";
import ToggleSwitch from "../../components/ToggleSwitch";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import useAutoSave from "../../hooks/useAutoSave";
import {
  deselectAllPairs,
  normalizePairOrder,
  selectAllPairs,
} from "../../lib/forexPairOrder";
import {
  DEFAULT_FOREX_TRADING_SESSIONS,
  normalizeForexTradingSessions,
  notifyForexTradingSessionsUpdated,
  type ForexTradingSessions,
} from "../../lib/forexTradingSessions";
import { formatSessionHours } from "../../lib/formatTime";
import { MARKET_SESSION_DEFS } from "../../lib/marketSessionDefs";
import TradingSessionCheckboxGrid from "../../components/settings/TradingSessionCheckboxGrid";
import { useGeneralSettings } from "../../hooks/useGeneralSettings";
import {
  connectedExchangesForAssetClass,
  type Exchange,
  type ExchangeId,
} from "./exchanges";

type AssetClassTabProps = {
  assetClass: AssetClass;
  label: string;
};

function PrimaryExchangeField({
  assetClass,
  label,
  value,
  enabled,
  options,
  loading,
  onChange,
}: {
  assetClass: AssetClass;
  label: string;
  value: string;
  enabled: boolean;
  options: Exchange[];
  loading: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="settings-card broker-exchange-card">
      <h3 className="settings-subtitle">Primary exchange</h3>
      {loading ? (
        <p className="settings-muted">Loading connected exchanges…</p>
      ) : options.length === 0 ? (
        <p className="settings-muted broker-exchange-empty">
          No exchange accounts are connected for {label.toLowerCase()}.{" "}
          <Link to="/settings/connections">Connect an exchange</Link> under Settings →
          Connections, then return here to choose a primary exchange.
        </p>
      ) : (
        <>
          <p className="settings-muted broker-exchange-desc">
            Choose the exchange the trading bot uses for {label.toLowerCase()}. Only connected
            exchanges for this asset class are shown.
          </p>
          <div className="settings-form broker-exchange-form">
            <label htmlFor={`primary-exchange-${assetClass}`}>
              Exchange
              <div className="research-select-wrap">
                <select
                  id={`primary-exchange-${assetClass}`}
                  className="research-select"
                  value={value}
                  onChange={(e) => onChange(e.target.value)}
                >
                  <option value="">Not set</option>
                  {options.map((exchange) => (
                    <option key={exchange.id} value={exchange.id}>
                      {exchange.name}
                    </option>
                  ))}
                </select>
              </div>
            </label>
          </div>
          {enabled && !value && (
            <p className="settings-muted broker-exchange-hint">
              Set a primary exchange before enabling live trading for {label.toLowerCase()}.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function forexHeaderAction(
  showForexUtc: boolean,
  onShowForexUtcChange: (next: boolean) => void,
  saveStatus: "idle" | "saving" | "saved" | "error",
): ReactNode {
  const saveStatusLabel =
    saveStatus === "saving" ? "Saving…" : saveStatus === "saved" ? "Saved" : null;

  return (
    <div className="settings-panel-header-actions">
      <div className="settings-panel-header-actions-row settings-panel-header-actions-row--title">
        <div className="settings-header-toggle">
          <span className="settings-header-toggle-label">Show UTC</span>
          <ToggleSwitch label="Show UTC" checked={showForexUtc} onChange={onShowForexUtcChange} />
        </div>
      </div>
      <div className="settings-panel-header-actions-row settings-panel-header-actions-row--desc">
        {saveStatusLabel ? (
          <span
            className={`settings-save-status${saveStatus === "saved" ? " settings-save-status--saved" : ""}`}
          >
            {saveStatusLabel}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default function AssetClassTab({ assetClass, label }: AssetClassTabProps) {
  const { effectiveTimezone, settings } = useGeneralSettings();
  const [showForexUtc, setShowForexUtc] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [primaryExchange, setPrimaryExchange] = useState("");
  const [exchangeConnections, setExchangeConnections] = useState<
    Awaited<ReturnType<typeof api.getExchangeConnections>> | null
  >(null);
  const [catalog, setCatalog] = useState<string[]>([]);
  const [enabledPairs, setEnabledPairs] = useState<string[]>([]);
  const [pairOrder, setPairOrder] = useState<string[]>([]);
  const [enabledSessions, setEnabledSessions] = useState<ForexTradingSessions>(
    DEFAULT_FOREX_TRADING_SESSIONS,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const snapshotRef = useRef({
    enabled,
    primaryExchange,
    enabledPairs,
    pairOrder,
    enabledSessions,
    assetClass,
  });
  snapshotRef.current = { enabled, primaryExchange, enabledPairs, pairOrder, enabledSessions, assetClass };

  const persistAssetSettings = useCallback(async () => {
    const snapshot = snapshotRef.current;
    await api.saveAssetSettings(snapshot.assetClass, {
      enabled: snapshot.enabled,
      enabled_pairs: snapshot.assetClass === "forex" ? snapshot.enabledPairs : undefined,
      pair_order: snapshot.assetClass === "forex" ? snapshot.pairOrder : undefined,
      enabled_sessions: snapshot.assetClass === "forex" ? snapshot.enabledSessions : undefined,
      primary_exchange: snapshot.primaryExchange || null,
    });
    if (snapshot.assetClass === "forex") {
      notifyForexTradingSessionsUpdated();
    }
  }, []);

  const { saveStatus, saveNow, scheduleSave, markReady, markNotReady, error: saveError } =
    useAutoSave({
      onSave: persistAssetSettings,
      canSave: () => !loading,
    });

  const connectedExchangeOptions = useMemo(
    () =>
      exchangeConnections
        ? connectedExchangesForAssetClass(assetClass, exchangeConnections)
        : [],
    [assetClass, exchangeConnections],
  );

  useEffect(() => {
    (async () => {
      markNotReady();
      setLoading(true);
      try {
        const connections = await api.getExchangeConnections();
        setExchangeConnections(connections);
        const connectedIds = new Set(
          connectedExchangesForAssetClass(assetClass, connections).map((exchange) => exchange.id),
        );

        if (assetClass === "forex") {
          const data = await api.getForexPairs();
          const catalogList = [...data.catalog];
          const enabledList = [...data.enabled_pairs];
          setCatalog(catalogList);
          setEnabledPairs(enabledList);
          setPairOrder(
            normalizePairOrder(catalogList, enabledList, data.pair_order),
          );
          setEnabledSessions(normalizeForexTradingSessions(data.enabled_sessions));
          setEnabled(data.enabled);
          const savedExchange = data.primary_exchange ?? "";
          setPrimaryExchange(
            savedExchange && connectedIds.has(savedExchange as ExchangeId) ? savedExchange : "",
          );
        } else {
          const data = await api.getAssetSettings(assetClass);
          setEnabled(data.enabled);
          const savedExchange = data.primary_exchange ?? "";
          setPrimaryExchange(
            savedExchange && connectedIds.has(savedExchange as ExchangeId) ? savedExchange : "",
          );
        }
        markReady();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load settings");
      } finally {
        setLoading(false);
      }
    })();
  }, [assetClass, markNotReady, markReady]);

  function handleEnabledChange(next: boolean) {
    setEnabled(next);
    snapshotRef.current = { ...snapshotRef.current, enabled: next };
    saveNow();
  }

  function handlePrimaryExchangeChange(next: string) {
    setPrimaryExchange(next);
    snapshotRef.current = { ...snapshotRef.current, primaryExchange: next };
    saveNow();
  }

  function handlePairOrderChange(next: string[]) {
    setPairOrder(next);
    snapshotRef.current = { ...snapshotRef.current, pairOrder: next };
  }

  function handleEnabledPairsChange(next: string[]) {
    setEnabledPairs(next);
    snapshotRef.current = { ...snapshotRef.current, enabledPairs: next };
  }

  function schedulePairSave() {
    scheduleSave(400);
  }

  function toggleTradingSession(sessionId: string, next: boolean) {
    setEnabledSessions((current) => {
      const updated = { ...current, [sessionId]: next };
      snapshotRef.current = { ...snapshotRef.current, enabledSessions: updated };
      return updated;
    });
    scheduleSave();
  }

  const allSessionsDisabled =
    assetClass === "forex" && !Object.values(enabledSessions).some(Boolean);

  function selectAllPairsAction() {
    const result = selectAllPairs(catalog, pairOrder, enabledPairs);
    setPairOrder(result.pairOrder);
    setEnabledPairs(result.enabledPairs);
    snapshotRef.current = {
      ...snapshotRef.current,
      pairOrder: result.pairOrder,
      enabledPairs: result.enabledPairs,
    };
    scheduleSave(400);
  }

  function deselectAllPairsAction() {
    const result = deselectAllPairs(pairOrder, enabledPairs);
    setPairOrder(result.pairOrder);
    setEnabledPairs(result.enabledPairs);
    snapshotRef.current = {
      ...snapshotRef.current,
      pairOrder: result.pairOrder,
      enabledPairs: result.enabledPairs,
    };
    scheduleSave(400);
  }

  const allSelected = catalog.length > 0 && enabledPairs.length === catalog.length;
  const noneSelected = enabledPairs.length === 0;
  const headerError = error ?? saveError;
  const showForexUtcToggle = assetClass === "forex" && effectiveTimezone !== "UTC";

  const forexTimeOptions = useMemo(
    () => ({
      showUtc: showForexUtc,
      timeZone: effectiveTimezone,
      timeFormat: settings.time_format,
    }),
    [showForexUtc, effectiveTimezone, settings.time_format],
  );

  const formatForexSessionHours = useCallback(
    (def: Parameters<typeof formatSessionHours>[0], reference?: Date) =>
      formatSessionHours(def, forexTimeOptions, reference),
    [forexTimeOptions],
  );

  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title={label}
        description={`Enable ${label.toLowerCase()} for research and trading bots.`}
        error={headerError}
        saveStatus={showForexUtcToggle ? undefined : saveStatus}
        action={
          showForexUtcToggle
            ? forexHeaderAction(showForexUtc, setShowForexUtc, saveStatus)
            : undefined
        }
      />

      <div className="settings-panel-body">
      <div className="settings-enable-row">
        <span className="settings-enable-label">Enable {label}</span>
        <ToggleSwitch label={`Enable ${label}`} checked={enabled} onChange={handleEnabledChange} />
      </div>
      {loading ? (
        <p className="settings-muted">Loading…</p>
      ) : (
        <>
          <PrimaryExchangeField
            assetClass={assetClass}
            label={label}
            value={primaryExchange}
            enabled={enabled}
            options={connectedExchangeOptions}
            loading={loading}
            onChange={handlePrimaryExchangeChange}
          />
          {assetClass === "forex" ? (
            <>
              <section className="account-section-card">
                <div className="settings-section-intro">
                  <h3 className="settings-subtitle">Trading sessions</h3>
                  <p className="settings-muted forex-pairs-hint">
                    Choose which liquidity sessions the bot may open new trades during (Sydney,
                    Asia, London, NY). Strategy session filters still apply on top of this setting.
                  </p>
                </div>
                <TradingSessionCheckboxGrid
                  sessions={MARKET_SESSION_DEFS}
                  values={enabledSessions}
                  onChange={toggleTradingSession}
                  formatSessionHours={formatForexSessionHours}
                />
                {allSessionsDisabled && (
                  <p className="param-helper param-helper--warn">
                    Select at least one session to allow forex trading.
                  </p>
                )}
              </section>
              <div className="forex-pairs-header">
                <div className="settings-section-intro">
                  <h3 className="settings-subtitle">Pair priority</h3>
                  <p className="settings-muted forex-pairs-count">
                    {enabledPairs.length} of {catalog.length} enabled
                  </p>
                </div>
                <div className="forex-pairs-toolbar">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={selectAllPairsAction}
                    disabled={allSelected}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={deselectAllPairsAction}
                    disabled={noneSelected}
                  >
                    Deselect all
                  </button>
                </div>
              </div>
              {!enabled && (
                <p className="settings-muted forex-pairs-hint">
                  Enable Forex above to activate the selected pairs for analysis and trading.
                </p>
              )}
              <p className="settings-muted forex-pairs-hint">
                Drag to set analysis priority. Higher pairs are processed first when analyzing
                candles. Daily research reports always group pairs by primary currency.
              </p>
              <ForexPairPriorityList
                pairOrder={pairOrder}
                enabledPairs={enabledPairs}
                onPairOrderChange={handlePairOrderChange}
                onEnabledPairsChange={handleEnabledPairsChange}
                onReorder={schedulePairSave}
                onToggle={schedulePairSave}
              />
            </>
          ) : (
            <div className="placeholder">
              Coming soon — {label.toLowerCase()} configuration will be available in a future release.
            </div>
          )}
        </>
      )}
      </div>
    </div>
  );
}
