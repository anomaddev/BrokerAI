import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  botStateLabel,
  botStateTone,
  formatBotName,
  sortBots,
  type BotStatusItem,
} from "../lib/bots";

const POLL_INTERVAL_MS = 15_000;

type BotPillProps = {
  bot: BotStatusItem;
};

function BotPill({ bot }: BotPillProps) {
  const tone = botStateTone(bot.state);

  return (
    <div className="market-session-item">
      <div
        className={`market-session-pill market-session-pill--${tone}`}
        aria-label={`${formatBotName(bot.name)}: ${botStateLabel(bot.state)}`}
      >
        <span className="market-session-dot" aria-hidden="true" />
        <span className="market-session-name">{formatBotName(bot.name)}</span>
      </div>
    </div>
  );
}

type BotStatusBarProps = {
  orchestratorRunning?: boolean | null;
};

export default function BotStatusBar({ orchestratorRunning: orchestratorRunningProp }: BotStatusBarProps) {
  const [orchestratorRunningInternal, setOrchestratorRunningInternal] = useState<boolean | null>(
    orchestratorRunningProp ?? null,
  );
  const [bots, setBots] = useState<BotStatusItem[]>([]);
  const orchestratorRunning =
    orchestratorRunningProp !== undefined ? orchestratorRunningProp : orchestratorRunningInternal;

  useEffect(() => {
    if (orchestratorRunningProp !== undefined) return undefined;

    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        const [health, botData] = await Promise.all([api.health(), api.bots()]);
        if (cancelled) return;
        setOrchestratorRunningInternal(Boolean(health.orchestrator_running));
        setBots(sortBots(botData.bots));
      } catch {
        if (!cancelled) {
          setOrchestratorRunningInternal(false);
          setBots([]);
        }
      }
    }

    function scheduleNext() {
      timer = window.setTimeout(() => {
        void load().finally(() => {
          if (!cancelled) scheduleNext();
        });
      }, POLL_INTERVAL_MS);
    }

    void load();
    scheduleNext();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [orchestratorRunningProp]);

  useEffect(() => {
    if (orchestratorRunningProp === undefined) return undefined;

    let cancelled = false;
    let timer: number | undefined;

    async function loadBots() {
      try {
        const botData = await api.bots();
        if (!cancelled) setBots(sortBots(botData.bots));
      } catch {
        if (!cancelled) setBots([]);
      }
    }

    function scheduleNext() {
      timer = window.setTimeout(() => {
        void loadBots().finally(() => {
          if (!cancelled) scheduleNext();
        });
      }, POLL_INTERVAL_MS);
    }

    if (orchestratorRunningProp === null) return undefined;

    void loadBots();
    scheduleNext();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [orchestratorRunningProp]);

  if (orchestratorRunning === null) {
    return null;
  }

  if (!orchestratorRunning) {
    return (
      <div className="bot-status-bar" aria-label="Bot status">
        <div className="market-session-item">
          <div
            className="market-session-pill market-session-pill--offline"
            aria-label="Orchestrator: Offline"
          >
            <span className="market-session-dot" aria-hidden="true" />
            <span className="market-session-name">Orchestrator</span>
          </div>
        </div>
      </div>
    );
  }

  if (bots.length === 0) {
    return null;
  }

  return (
    <div className="bot-status-bar" aria-label="Bot status">
      {bots.map((bot) => (
        <BotPill key={bot.name} bot={bot} />
      ))}
    </div>
  );
}
