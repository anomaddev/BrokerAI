import type { BotActivityEvent } from "../api/client";
import { formatAppInstant, parseAppInstant, type TimeFormatOptions } from "./formatTime";

export type NormalizedActivityEvent = {
  id: string;
  label: string;
  occurred_at: string;
};

/** Broad labels for the bot status tooltip timeline (keyed by action_type). */
export const BROAD_ACTIVITY_LABELS: Record<string, string> = {
  candle_closed: "Candle Closed",
  daily_report_completed: "Daily Report Ran",
  daily_report_failed: "Daily Report Failed",
  weekly_brief_completed: "Weekly Brief Ran",
  weekly_debrief_completed: "Weekly Debrief Ran",
  pipeline_analyze_completed: "Forex Strategies Analyzed",
  market_session_open: "Session Opened",
  market_session_close: "Session Closed",
  orchestrator_started: "Orchestrator Started",
  orchestrator_stopped: "Orchestrator Stopped",
  bot_error: "Bot Error",
  account_summary_updated: "Account Summary Updated",
  pipeline_failed: "Pipeline Failed",
};

const FILTERED_ACTION_TYPES = new Set([
  "pipeline_scheduled",
  "pipeline_fetch_started",
  "pipeline_fetch_completed",
  "pipeline_analyze_started",
  "pipeline_broker_started",
  "pipeline_broker_completed",
  "pipeline_associate_started",
  "pipeline_associate_completed",
  "pipeline_skipped",
]);

function broadActivityLabel(event: BotActivityEvent): string | null {
  const mapped = BROAD_ACTIVITY_LABELS[event.action_type];
  if (mapped) {
    if (
      event.action_type === "market_session_open" ||
      event.action_type === "market_session_close"
    ) {
      const sessionName = event.metadata?.session_name;
      if (typeof sessionName === "string" && sessionName.trim()) {
        return event.action_type === "market_session_open"
          ? `${sessionName} Opened`
          : `${sessionName} Closed`;
      }
    }
    return mapped;
  }
  return null;
}

function minuteBucket(iso: string): string | null {
  const date = parseAppInstant(iso);
  if (!date) return null;
  return `${date.getUTCFullYear()}-${date.getUTCMonth()}-${date.getUTCDate()}-${date.getUTCHours()}-${date.getUTCMinutes()}`;
}

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

/**
 * Collapse granular pipeline activity into broad timeline rows for the status tooltip.
 *
 * Filters granular pipeline steps, dedupes consecutive analyze completions within the
 * same UTC minute, and returns at most ``limit`` entries (newest first).
 */
export function normalizeActivityTimeline(
  events: BotActivityEvent[],
  limit = 5,
): NormalizedActivityEvent[] {
  const normalized: NormalizedActivityEvent[] = [];

  for (const event of events) {
    if (FILTERED_ACTION_TYPES.has(event.action_type)) {
      continue;
    }

    const label = broadActivityLabel(event);
    if (!label) {
      continue;
    }

    const previous = normalized[normalized.length - 1];
    if (
      event.action_type === "pipeline_analyze_completed" &&
      previous?.label === "Forex Strategies Analyzed" &&
      minuteBucket(previous.occurred_at) === minuteBucket(event.occurred_at)
    ) {
      continue;
    }

    normalized.push({
      id: event.id,
      label,
      occurred_at: event.occurred_at,
    });

    if (normalized.length >= limit) {
      break;
    }
  }

  return normalized;
}
