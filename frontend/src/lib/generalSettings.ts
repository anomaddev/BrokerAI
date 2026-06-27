export type GeneralSettings = {
  timezone_auto: boolean;
  timezone: string | null;
  show_utc_times: boolean;
};

export const DEFAULT_GENERAL_SETTINGS: GeneralSettings = {
  timezone_auto: true,
  timezone: null,
  show_utc_times: false,
};

export const GENERAL_SETTINGS_UPDATED = "brokerai:general-settings-updated";

export function notifyGeneralSettingsUpdated(): void {
  window.dispatchEvent(new Event(GENERAL_SETTINGS_UPDATED));
}

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function normalizeGeneralSettings(raw: Partial<GeneralSettings> | null | undefined): GeneralSettings {
  if (!raw) return { ...DEFAULT_GENERAL_SETTINGS };

  const timezoneAuto = raw.timezone_auto ?? DEFAULT_GENERAL_SETTINGS.timezone_auto;
  const showUtcTimes = raw.show_utc_times ?? DEFAULT_GENERAL_SETTINGS.show_utc_times;
  const timezone =
    typeof raw.timezone === "string" && raw.timezone.trim() ? raw.timezone.trim() : null;

  if (timezoneAuto) {
    return {
      timezone_auto: true,
      timezone,
      show_utc_times: showUtcTimes,
    };
  }

  return {
    timezone_auto: false,
    timezone: timezone && isValidTimezone(timezone) ? timezone : "UTC",
    show_utc_times: showUtcTimes,
  };
}

export function resolveEffectiveTimezone(settings: GeneralSettings): string {
  if (settings.timezone_auto) {
    return getBrowserTimezone();
  }
  return settings.timezone && isValidTimezone(settings.timezone) ? settings.timezone : "UTC";
}

export function isValidTimezone(value: string): boolean {
  try {
    Intl.DateTimeFormat(undefined, { timeZone: value });
    return true;
  } catch {
    return false;
  }
}

export type TimezoneOption = {
  value: string;
  label: string;
  region: string;
};

const timezoneLabelCache = new Map<string, string>();

export function timezoneOptionLabel(timeZone: string): string {
  const cached = timezoneLabelCache.get(timeZone);
  if (cached) return cached;

  let label = timeZone;
  try {
    const parts = new Intl.DateTimeFormat(undefined, {
      timeZone,
      timeZoneName: "shortOffset",
    }).formatToParts(new Date());
    const offset = parts.find((part) => part.type === "timeZoneName")?.value;
    label = offset ? `${timeZone} (${offset})` : timeZone;
  } catch {
    label = timeZone;
  }

  timezoneLabelCache.set(timeZone, label);
  return label;
}

export function listTimezoneOptions(): TimezoneOption[] {
  const supported =
    typeof Intl.supportedValuesOf === "function"
      ? Intl.supportedValuesOf("timeZone")
      : [
          "UTC",
          "America/New_York",
          "America/Chicago",
          "America/Denver",
          "America/Los_Angeles",
          "Europe/London",
          "Europe/Paris",
          "Asia/Tokyo",
          "Asia/Singapore",
          "Australia/Sydney",
        ];

  return supported
    .map((value) => ({
      value,
      label: timezoneOptionLabel(value),
      region: value.includes("/") ? value.split("/")[0] : "Other",
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function groupTimezoneOptions(options: TimezoneOption[]): Map<string, TimezoneOption[]> {
  const grouped = new Map<string, TimezoneOption[]>();
  for (const option of options) {
    const list = grouped.get(option.region) ?? [];
    list.push(option);
    grouped.set(option.region, list);
  }
  return grouped;
}
