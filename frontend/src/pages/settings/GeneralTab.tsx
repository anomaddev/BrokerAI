import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/client";
import SettingsPanelHeader from "../../components/SettingsPanelHeader";
import ToggleSwitch from "../../components/ToggleSwitch";
import useAutoSave from "../../hooks/useAutoSave";
import {
  DEFAULT_GENERAL_SETTINGS,
  getBrowserTimezone,
  groupTimezoneOptions,
  listTimezoneOptions,
  normalizeGeneralSettings,
  notifyGeneralSettingsUpdated,
  timezoneOptionLabel,
  type GeneralSettings,
} from "../../lib/generalSettings";

export default function GeneralTab() {
  const [settings, setSettings] = useState<GeneralSettings>(DEFAULT_GENERAL_SETTINGS);
  const [loading, setLoading] = useState(true);
  const settingsRef = useRef(settings);
  const browserTimezone = useMemo(() => getBrowserTimezone(), []);

  settingsRef.current = settings;

  const timezoneOptions = useMemo(() => listTimezoneOptions(), []);
  const groupedTimezones = useMemo(() => groupTimezoneOptions(timezoneOptions), [timezoneOptions]);

  const { saving, saveStatus, error, scheduleSave, markReady, markNotReady } = useAutoSave({
    onSave: async () => {
      const saved = await api.updateGeneralSettings(settingsRef.current);
      const normalized = normalizeGeneralSettings(saved);
      setSettings(normalized);
      notifyGeneralSettingsUpdated();
    },
  });

  useEffect(() => {
    let cancelled = false;

    api
      .getGeneralSettings()
      .then((data) => {
        if (cancelled) return;
        setSettings(normalizeGeneralSettings(data));
        markReady();
      })
      .catch(() => {
        if (!cancelled) {
          setSettings(DEFAULT_GENERAL_SETTINGS);
          markReady();
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      markNotReady();
    };
  }, [markNotReady, markReady]);

  function updateSettings(next: GeneralSettings) {
    settingsRef.current = next;
    setSettings(next);
    scheduleSave();
  }

  function setTimezoneAuto(timezoneAuto: boolean) {
    updateSettings({
      ...settingsRef.current,
      timezone_auto: timezoneAuto,
      timezone: timezoneAuto
        ? browserTimezone
        : settingsRef.current.timezone ?? browserTimezone,
    });
  }

  function setManualTimezone(timezone: string) {
    if (settingsRef.current.timezone_auto) return;
    updateSettings({
      ...settingsRef.current,
      timezone_auto: false,
      timezone,
    });
  }

  function setShowUtcTimes(showUtcTimes: boolean) {
    updateSettings({
      ...settingsRef.current,
      show_utc_times: showUtcTimes,
    });
  }

  function setTimeFormat(timeFormat: GeneralSettings["time_format"]) {
    updateSettings({
      ...settingsRef.current,
      time_format: timeFormat,
    });
  }

  const displayedTimezone = settings.timezone_auto
    ? browserTimezone
    : settings.timezone ?? browserTimezone;

  return (
    <div className="settings-panel">
      <SettingsPanelHeader title="General" />
      <div className="settings-panel-body settings-panel-body--stack">
        {loading ? (
          <p className="settings-muted">Loading general settings…</p>
        ) : (
          <section className="account-section-card">
            <div className="settings-section-intro">
              <div className="settings-section-intro-row">
                <div>
                  <h3 className="settings-subsection-title">Timezone &amp; time display</h3>
                  <p className="settings-panel-desc">
                    Choose how market and trade times are shown. When UTC display is off, times
                    convert using your automatic or selected timezone. Use 12-hour or 24-hour clock
                    format across the dashboard.
                  </p>
                </div>
                {saveStatus === "saving" ? (
                  <span className="settings-save-status">Saving…</span>
                ) : saveStatus === "saved" ? (
                  <span className="settings-save-status settings-save-status--saved">Saved</span>
                ) : null}
              </div>
            </div>

            {error ? <p className="settings-error">{error}</p> : null}

            <div className="general-settings-stack">
              <div className="general-settings-group">
                <h4 className="general-settings-group-title">Time display</h4>
                <div className="research-source-row">
                  <span className="research-source-name">Always Show UTC times for Charts &amp; Trades</span>
                  <ToggleSwitch
                    label="Always Show UTC times for Charts and Trades"
                    checked={settings.show_utc_times}
                    disabled={saving}
                    onChange={setShowUtcTimes}
                  />
                </div>
                <div className="research-source-row">
                  <span className="research-source-name">Time format</span>
                  <div className="settings-segmented" role="tablist" aria-label="Time format">
                    {(
                      [
                        { value: "12h", label: "12-hour" },
                        { value: "24h", label: "24-hour" },
                      ] as const
                    ).map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        role="tab"
                        aria-selected={settings.time_format === option.value}
                        className={`settings-segmented-btn${settings.time_format === option.value ? " settings-segmented-btn--active" : ""}`}
                        disabled={saving}
                        onClick={() => setTimeFormat(option.value)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="general-settings-group">
                <h4 className="general-settings-group-title">Timezone</h4>
                <div className="research-source-row">
                  <span className="research-source-name">Use automatic timezone</span>
                  <ToggleSwitch
                    label="Use automatic timezone"
                    checked={settings.timezone_auto}
                    disabled={saving}
                    onChange={setTimezoneAuto}
                  />
                </div>

                <label className="general-settings-field">
                  <span className="general-settings-field-label">Timezone</span>
                  <div className="settings-select-wrap">
                    <select
                      className="settings-select"
                      value={displayedTimezone}
                      disabled={saving || settings.timezone_auto}
                      onChange={(event) => setManualTimezone(event.target.value)}
                    >
                      {Array.from(groupedTimezones.entries())
                        .sort(([a], [b]) => a.localeCompare(b))
                        .map(([region, options]) => (
                          <optgroup key={region} label={region}>
                            {options.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                    </select>
                  </div>
                  {settings.timezone_auto ? (
                    <span className="settings-field-hint">
                      Automatically set from your device ({timezoneOptionLabel(browserTimezone)}).
                    </span>
                  ) : null}
                </label>
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
