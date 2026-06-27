import type { BotActivityEvent } from "../api/client";
import { formatAppInstant, parseAppInstant, type TimeFormatOptions } from "./formatTime";

export function formatActivityRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const occurredDate = parseAppInstant(iso);
  if (!occurredDate) return "—";
  const occurred = occurredDate.getTime();

  // Use absolute delta so server/client clock skew does not collapse to "just now".
  const deltaMs = Math.abs(now - occurred);
  const totalSeconds = Math.floor(deltaMs / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  if (seconds > 0) return `${seconds}s ago`;
  return "just now";
}

export function formatActivityClock(
  iso: string | null | undefined,
  timeOptions?: TimeFormatOptions,
): string {
  if (!iso) return "—";
  if (timeOptions) {
    return formatAppInstant(iso, timeOptions, "short");
  }
  const occurred = new Date(iso);
  if (Number.isNaN(occurred.getTime())) return "—";
  return occurred.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function activityTimelineLabel(event: BotActivityEvent): string {
  return event.title;
}

export function activityTimelineDetail(event: BotActivityEvent): string | null {
  if (event.detail?.trim()) return event.detail.trim();
  return null;
}
