import type { MarketSessionStatus } from "../api/client";
import type { MarketIndicators } from "./displaySettings";
import { formatAppInstant, type TimeFormatOptions } from "./formatTime";
import { anyEnabledMarketOpen } from "./marketSessions";

export const SUB_BOT_ORDER = [
  "brokers",
  "researcher",
  "data_manager",
  "data_analyzer",
  "executor",
] as const;

export type BotStatusItem = {
  name: string;
  state: string;
  started_at?: string | null;
  last_error?: string | null;
};

export function formatBotName(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function botStateTone(state: string): "running" | "stopped" | "error" | "offline" {
  if (state === "running") return "running";
  if (state === "error") return "error";
  if (state === "stopped") return "stopped";
  return "offline";
}

export function botStateLabel(state: string): string {
  if (state === "running") return "Running";
  if (state === "stopped") return "Stopped";
  if (state === "error") return "Error";
  return "Unknown";
}

export function sortBots<T extends { name: string }>(bots: T[]): T[] {
  const order = new Map(SUB_BOT_ORDER.map((name, index) => [name, index]));
  return [...bots].sort(
    (a, b) => (order.get(a.name) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.name) ?? Number.MAX_SAFE_INTEGER),
  );
}

export function resolveBotTooltip(
  bot: BotStatusItem,
  timeOptions?: TimeFormatOptions,
): {
  title: string;
  state: string;
  detail: string | null;
} {
  const title = formatBotName(bot.name);
  const state = botStateLabel(bot.state);

  if (bot.state === "error" && bot.last_error?.trim()) {
    return { title, state, detail: bot.last_error.trim() };
  }

  if (bot.state === "running" && bot.started_at) {
    const started = new Date(bot.started_at);
    if (!Number.isNaN(started.getTime())) {
      const formatted = timeOptions
        ? formatAppInstant(started, timeOptions, "short")
        : started.toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          });
      return {
        title,
        state,
        detail: `Started ${formatted}`,
      };
    }
  }

  return { title, state, detail: null };
}

export type OverallBotStatus = "running" | "sleeping" | "stopped" | "error";

export function computeOverallStatus(input: {
  orchestratorRunning: boolean;
  bots: BotStatusItem[];
  marketSessions: MarketSessionStatus[];
  marketIndicators: MarketIndicators;
  marketAvailable: boolean;
  marketServerTime?: string;
}): OverallBotStatus {
  if (!input.orchestratorRunning) return "stopped";
  if (input.bots.some((bot) => bot.state === "error")) return "error";

  const marketsOpen = anyEnabledMarketOpen(input.marketSessions, input.marketIndicators, {
    marketAvailable: input.marketAvailable,
    serverTime: input.marketServerTime,
  });

  return marketsOpen ? "running" : "sleeping";
}

export function overallStatusLabel(status: OverallBotStatus): string {
  if (status === "running") return "Running";
  if (status === "sleeping") return "Sleeping";
  if (status === "stopped") return "Stopped";
  return "Error";
}

export function overallStatusTone(status: OverallBotStatus): OverallBotStatus {
  return status;
}

export function resolveOverallStatusTooltip(input: {
  status: OverallBotStatus;
  bots: BotStatusItem[];
}): { title: string; lines: string[] } {
  const title = `Bot: ${overallStatusLabel(input.status)}`;
  const lines: string[] = [];

  if (input.status === "sleeping") {
    lines.push("All tracked markets are closed.");
  } else if (input.status === "running") {
    lines.push("At least one tracked market is open.");
  } else if (input.status === "stopped") {
    lines.push("Orchestrator is offline.");
  }

  const sortedBots = sortBots(input.bots);
  if (sortedBots.length > 0) {
    lines.push(
      ...sortedBots.map((bot) => `${formatBotName(bot.name)}: ${botStateLabel(bot.state)}`),
    );
  }

  const errorBot = sortedBots.find((bot) => bot.state === "error" && bot.last_error?.trim());
  if (errorBot?.last_error?.trim()) {
    lines.push(errorBot.last_error.trim());
  }

  return { title, lines };
}
