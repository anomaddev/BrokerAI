import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import {
  api,
  type BackupScheduleSettings,
  type BackupScheduleSettingsInput,
} from "../../../api/client";
import ToggleSwitch from "../../ToggleSwitch";
import useAutoSave from "../../../hooks/useAutoSave";
import {
  BACKUP_INTERVAL_HOUR_OPTIONS,
  backupScheduleNextRunCallout,
  CHANGE_BACKUP_RETENTION,
  DEFAULT_DAILY_TIME,
  FULL_BACKUP_RETENTION,
  normalizeChangeRetention,
  normalizeDailyTime,
  normalizeFullRetention,
  normalizeIntervalHours,
} from "../../../lib/backupSchedule";
import {
  DEFAULT_DAILY_REPORT_MARKET_ID,
  DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS,
  findScheduleMarket,
  formatScheduleMarketOptionLabel,
  MARKET_OFFSET_OPTIONS,
  offsetLabel,
} from "../../../pages/settings/researchMarkets";
import { useGeneralSettings } from "../../../hooks/useGeneralSettings";
import { notifyBackupTimelineUpdated } from "../../../lib/configBackup";
import RetentionStepper from "./RetentionStepper";

type Props = {
  onError: (message: string | null) => void;
};

const SCHEDULE_EXPANDED_STORAGE_KEY = "brokerai:backup-schedule-expanded";

function readScheduleExpandedPreference(): boolean {
  try {
    return localStorage.getItem(SCHEDULE_EXPANDED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function writeScheduleExpandedPreference(expanded: boolean): void {
  try {
    localStorage.setItem(SCHEDULE_EXPANDED_STORAGE_KEY, expanded ? "true" : "false");
  } catch {
    // Ignore storage failures in private browsing.
  }
}

function schedulePayload(snapshot: BackupScheduleSettings): BackupScheduleSettingsInput {
  return {
    enabled: snapshot.enabled,
    mode: snapshot.mode,
    daily_market_id: snapshot.daily_market_id,
    daily_offset_hours: snapshot.daily_offset_hours,
    daily_time: snapshot.daily_time,
    interval_hours: snapshot.interval_hours,
    full_retention: snapshot.full_retention,
    change_retention: snapshot.change_retention,
  };
}

export default function BackupScheduleCard({ onError }: Props) {
  const { timeOptions, effectiveTimezone } = useGeneralSettings();
  const [settings, setSettings] = useState<BackupScheduleSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(readScheduleExpandedPreference);
  const snapshotRef = useRef<BackupScheduleSettings>({});
  const saveGenerationRef = useRef(0);

  const persistSchedule = useCallback(async () => {
    const generationAtStart = saveGenerationRef.current;
    const saved = await api.saveBackupSchedule(schedulePayload(snapshotRef.current));
    if (generationAtStart === saveGenerationRef.current) {
      snapshotRef.current = saved;
      setSettings(saved);
    }
    notifyBackupTimelineUpdated();
  }, []);

  const { saving, saveStatus, saveNow, markReady, markNotReady, error: saveError } =
    useAutoSave({
      onSave: persistSchedule,
      canSave: () => !loading && settings !== null,
    });

  useEffect(() => {
    if (saveError) onError(saveError);
  }, [onError, saveError]);

  useEffect(() => {
    writeScheduleExpandedPreference(expanded);
  }, [expanded]);

  useEffect(() => {
    markNotReady();
    (async () => {
      setLoading(true);
      onError(null);
      try {
        const data = await api.getBackupSchedule();
        snapshotRef.current = data;
        setSettings(data);
        markReady();
      } catch (err) {
        onError(err instanceof Error ? err.message : "Failed to load backup schedule");
      } finally {
        setLoading(false);
      }
    })();
  }, [markNotReady, markReady, onError]);

  function patchLocal(updates: Partial<BackupScheduleSettings>) {
    saveGenerationRef.current += 1;
    setSettings((previous) => {
      if (!previous) return previous;
      const next = { ...previous, ...updates };
      snapshotRef.current = next;
      return next;
    });
    saveNow();
  }

  const markets = settings?.schedule_markets ?? [];
  const dailyMarket = useMemo(
    () =>
      findScheduleMarket(
        markets,
        settings?.daily_market_id ?? DEFAULT_DAILY_REPORT_MARKET_ID,
      ),
    [markets, settings?.daily_market_id],
  );
  const dailyOffset = settings?.daily_offset_hours ?? DEFAULT_DAILY_REPORT_MARKET_OFFSET_HOURS;
  const enabled = Boolean(settings?.enabled);
  const scheduleTimezone = settings?.schedule_timezone ?? effectiveTimezone;
  const dailyTime = normalizeDailyTime(settings?.daily_time ?? DEFAULT_DAILY_TIME);
  const mode = settings?.mode ?? "daily";
  const intervalHours = normalizeIntervalHours(settings?.interval_hours);

  const nextRunCallout = useMemo(() => {
    if (!enabled || !settings) return null;
    return backupScheduleNextRunCallout(settings, {
      dailyMarket,
      scheduleTimezone,
      timeOptions,
    });
  }, [enabled, settings, dailyMarket, scheduleTimezone, timeOptions]);

  if (loading || !settings) {
    return <p className="settings-muted">Loading backup schedule…</p>;
  }

  const saveStatusLabel =
    saveStatus === "saving" ? "Saving…" : saveStatus === "saved" ? "Saved" : null;

  return (
    <section
      className={`settings-card research-card research-schedule-card backup-schedule-card${
        expanded ? " backup-schedule-card--expanded" : " backup-schedule-card--collapsed"
      }`}
    >
      <div className="research-schedule-header backup-schedule-header">
        <button
          type="button"
          className="backup-schedule-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          <ChevronDown className="backup-schedule-chevron" aria-hidden="true" size={16} />
          <span className="backup-schedule-toggle-text">
            <span className="research-card-title">Automatic backups</span>
            <span className="settings-muted backup-schedule-toggle-desc">
              Schedule full configuration snapshots.
            </span>
          </span>
        </button>
        <div
          className="research-schedule-enable backup-schedule-enable"
          onClick={(event) => event.stopPropagation()}
        >
          <span
            className={`settings-save-status backup-schedule-save-status${
              saveStatus === "saved" ? " settings-save-status--saved" : ""
            }${saveStatusLabel ? "" : " backup-schedule-save-status--empty"}`}
            aria-hidden={!saveStatusLabel}
          >
            {saveStatusLabel ?? "Saved"}
          </span>
          <span className="research-schedule-enable-label">Enable</span>
          <ToggleSwitch
            label="Enable scheduled backups"
            checked={enabled}
            onChange={(next) => patchLocal({ enabled: next })}
          />
        </div>
      </div>

      <div className="backup-schedule-panel-shell" hidden={!expanded}>
      <div className={`research-schedule-panel${enabled ? "" : " research-schedule-panel--disabled"}`}>
        <div className="research-schedule-panel-layout">
          <div className="research-schedule-fields backup-schedule-fields">
            <div
              className={`backup-schedule-row${
                nextRunCallout ? " backup-schedule-row--with-callout" : ""
              }`}
            >
              <div className="backup-schedule-inputs">
                <div className="research-field research-schedule-field backup-schedule-field">
                  <label className="research-field-label" htmlFor="backup-schedule-mode">
                    Schedule mode
                  </label>
                  <div className="research-select-wrap">
                    <select
                      id="backup-schedule-mode"
                      className="research-select"
                      value={mode}
                      disabled={!enabled}
                      onChange={(event) =>
                        patchLocal({ mode: event.target.value as BackupScheduleSettings["mode"] })
                      }
                    >
                      <option value="daily">Daily at market time</option>
                      <option value="daily_time">Daily at specific time</option>
                      <option value="interval">Fixed interval</option>
                    </select>
                  </div>
                </div>

                {mode === "daily" ? (
                  <>
                    <div className="research-field research-schedule-field backup-schedule-field">
                      <label className="research-field-label" htmlFor="backup-schedule-market">
                        Market
                      </label>
                      <div className="research-select-wrap">
                        <select
                          id="backup-schedule-market"
                          className="research-select"
                          value={settings.daily_market_id ?? DEFAULT_DAILY_REPORT_MARKET_ID}
                          disabled={!enabled}
                          onChange={(event) => patchLocal({ daily_market_id: event.target.value })}
                        >
                          {markets.map((market) => (
                            <option key={market.id} value={market.id}>
                              {formatScheduleMarketOptionLabel(market, timeOptions)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="research-field research-schedule-field backup-schedule-field">
                      <label className="research-field-label" htmlFor="backup-schedule-offset">
                        Run time
                      </label>
                      <div className="research-select-wrap">
                        <select
                          id="backup-schedule-offset"
                          className="research-select"
                          value={dailyOffset}
                          disabled={!enabled}
                          onChange={(event) =>
                            patchLocal({ daily_offset_hours: Number(event.target.value) })
                          }
                        >
                          {MARKET_OFFSET_OPTIONS.map((hours) => (
                            <option key={hours} value={hours}>
                              {offsetLabel(hours)}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </>
                ) : null}

                {mode === "daily_time" ? (
                  <div className="research-field research-schedule-field backup-schedule-field">
                    <label className="research-field-label" htmlFor="backup-schedule-time">
                      Run time
                    </label>
                    <div className="research-select-wrap research-select-wrap--plain">
                      <input
                        id="backup-schedule-time"
                        className="research-select"
                        type="time"
                        value={dailyTime}
                        disabled={!enabled}
                        title={`Uses your General settings timezone (${scheduleTimezone})`}
                        onChange={(event) =>
                          patchLocal({ daily_time: normalizeDailyTime(event.target.value) })
                        }
                      />
                    </div>
                  </div>
                ) : null}

                {mode === "interval" ? (
                  <div className="research-field research-schedule-field backup-schedule-field">
                    <label className="research-field-label" htmlFor="backup-interval-hours">
                      Interval
                    </label>
                    <div className="research-select-wrap">
                      <select
                        id="backup-interval-hours"
                        className="research-select"
                        value={intervalHours}
                        disabled={!enabled}
                        onChange={(event) =>
                          patchLocal({ interval_hours: Number(event.target.value) })
                        }
                      >
                        {BACKUP_INTERVAL_HOUR_OPTIONS.map((hours) => (
                          <option key={hours} value={hours}>
                            Every {hours} hour{hours === 1 ? "" : "s"}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                ) : null}
              </div>

              {nextRunCallout ? (
                <div className="backup-schedule-next-run" title={nextRunCallout.title}>
                  <span className="backup-schedule-next-run-label">Next run</span>
                  <span className="backup-schedule-next-run-value">{nextRunCallout.text}</span>
                </div>
              ) : null}
            </div>

            <div className="backup-retention-row">
              <RetentionStepper
                id="backup-full-retention"
                label="Keep full backups"
                value={normalizeFullRetention(settings.full_retention)}
                min={FULL_BACKUP_RETENTION.min}
                max={FULL_BACKUP_RETENTION.max}
                step={FULL_BACKUP_RETENTION.step}
                disabled={!enabled}
                onChange={(value) => patchLocal({ full_retention: value })}
              />
              <RetentionStepper
                id="backup-change-retention"
                label="Keep change history"
                value={normalizeChangeRetention(settings.change_retention)}
                min={CHANGE_BACKUP_RETENTION.min}
                max={CHANGE_BACKUP_RETENTION.max}
                step={CHANGE_BACKUP_RETENTION.step}
                disabled={!enabled}
                onChange={(value) => patchLocal({ change_retention: value })}
              />
            </div>
          </div>
        </div>
      </div>
      </div>
    </section>
  );
}
