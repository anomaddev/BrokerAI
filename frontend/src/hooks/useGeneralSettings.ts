import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { api } from "../api/client";
import {
  DEFAULT_GENERAL_SETTINGS,
  GENERAL_SETTINGS_UPDATED,
  normalizeGeneralSettings,
  resolveEffectiveTimezone,
  type GeneralSettings,
} from "../lib/generalSettings";
import {
  formatAppInstant,
  formatAppTimeOfDay,
  formatSessionHours,
  type AppInstantStyle,
  type TimeFormatOptions,
} from "../lib/formatTime";

let cachedSettings: GeneralSettings = { ...DEFAULT_GENERAL_SETTINGS };
let loadPromise: Promise<GeneralSettings> | null = null;
let listeners = new Set<() => void>();

function emitChange() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): GeneralSettings {
  return cachedSettings;
}

export function setGeneralSettingsCache(settings: GeneralSettings): void {
  cachedSettings = normalizeGeneralSettings(settings);
  emitChange();
}

export async function loadGeneralSettings(force = false): Promise<GeneralSettings> {
  if (!force && loadPromise) return loadPromise;

  loadPromise = api
    .getGeneralSettings()
    .then((data) => {
      const normalized = normalizeGeneralSettings(data);
      cachedSettings = normalized;
      emitChange();
      return normalized;
    })
    .catch(() => {
      cachedSettings = { ...DEFAULT_GENERAL_SETTINGS };
      emitChange();
      return cachedSettings;
    })
    .finally(() => {
      loadPromise = null;
    });

  return loadPromise;
}

export function useGeneralSettings() {
  const settings = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const [loaded, setLoaded] = useState(loadPromise != null || settings !== DEFAULT_GENERAL_SETTINGS);

  useEffect(() => {
    let cancelled = false;
    void loadGeneralSettings().then(() => {
      if (!cancelled) setLoaded(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleUpdate() {
      void loadGeneralSettings(true);
    }
    window.addEventListener(GENERAL_SETTINGS_UPDATED, handleUpdate);
    return () => window.removeEventListener(GENERAL_SETTINGS_UPDATED, handleUpdate);
  }, []);

  const effectiveTimezone = resolveEffectiveTimezone(settings);
  const showUtc = settings.show_utc_times;
  const timeFormat = settings.time_format;

  const timeOptions: TimeFormatOptions = useMemo(
    () => ({
      showUtc,
      timeZone: effectiveTimezone,
      timeFormat,
    }),
    [showUtc, effectiveTimezone, timeFormat],
  );

  /** Settings/history tables: honor timezone + 12/24h, not the charts-only UTC toggle. */
  const settingsTimeOptions: TimeFormatOptions = useMemo(
    () => ({
      showUtc: false,
      timeZone: effectiveTimezone,
      timeFormat,
    }),
    [effectiveTimezone, timeFormat],
  );

  const formatInstant = useCallback(
    (value: string | number | Date | null | undefined, style: AppInstantStyle = "full") =>
      formatAppInstant(value, timeOptions, style),
    [timeOptions],
  );

  const formatTimeOfDay = useCallback(
    (value: string | number | Date, includeWeekday = false) =>
      formatAppTimeOfDay(value, timeOptions, includeWeekday),
    [timeOptions],
  );

  const formatSessionHoursLabel = useCallback(
    (
      def: Parameters<typeof formatSessionHours>[0],
      reference?: Date,
    ) => formatSessionHours(def, timeOptions, reference),
    [timeOptions],
  );

  return {
    settings,
    loaded,
    effectiveTimezone,
    showUtc,
    timeFormat,
    timeOptions,
    settingsTimeOptions,
    formatInstant,
    formatTimeOfDay,
    formatSessionHours: formatSessionHoursLabel,
  };
}
