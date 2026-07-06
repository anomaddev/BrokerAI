import { DISPLAY_SETTINGS_UPDATED } from "./displaySettings";
import { GENERAL_SETTINGS_UPDATED } from "./generalSettings";

export const CONFIG_RESTORED = "brokerai:config-restored";
export const BACKUP_TIMELINE_UPDATED = "brokerai:backup-timeline-updated";

export function notifyConfigRestored(): void {
  window.dispatchEvent(new Event(CONFIG_RESTORED));
  window.dispatchEvent(new Event(DISPLAY_SETTINGS_UPDATED));
  window.dispatchEvent(new Event(GENERAL_SETTINGS_UPDATED));
}

export function notifyBackupTimelineUpdated(): void {
  window.dispatchEvent(new Event(BACKUP_TIMELINE_UPDATED));
}
