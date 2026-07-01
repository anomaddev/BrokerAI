import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  api,
  type BotActivityEvent,
  type ResearchSettings,
} from "../api/client";
import {
  activityTimelineLabel,
  formatActivityRelative,
} from "../lib/botActivity";
import {
  computeOverallStatus,
  overallStatusLabel,
  overallStatusTone,
  resolveOverallStatusTooltip,
  sortBots,
  type BotStatusItem,
  type OverallBotStatus,
} from "../lib/bots";
import {
  DEFAULT_MARKET_INDICATORS,
  DISPLAY_SETTINGS_UPDATED,
  normalizeMarketIndicators,
  type MarketIndicators,
} from "../lib/displaySettings";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { useMarketStatus } from "../hooks/useMarketStatus";
import { anyEnabledMarketOpen } from "../lib/marketSessions";
import {
  computeNextAction,
  computeProgress,
  formatCountdown,
  formatNextActionDisplay,
  formatNextActionTargetUtc,
  resolveOverallStatusExplainer,
  type NextActionState,
} from "../lib/nextAction";

const POLL_INTERVAL_MS = 15_000;
const COUNTDOWN_REFRESH_MS = 1_000;
const TIMELINE_LIMIT = 8;

type TooltipCoords = {
  top: number;
  left: number;
};

export default function OverallBotStatus() {
  const { timeOptions } = useGeneralSettings();
  const panelRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [orchestratorRunning, setOrchestratorRunning] = useState<boolean | null>(null);
  const [bots, setBots] = useState<BotStatusItem[]>([]);
  const marketStatus = useMarketStatus();
  const [researchSettings, setResearchSettings] = useState<ResearchSettings | null>(null);
  const [activityEvents, setActivityEvents] = useState<BotActivityEvent[]>([]);
  const [indicators, setIndicators] = useState<MarketIndicators>(DEFAULT_MARKET_INDICATORS);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;

    api
      .getDisplaySettings()
      .then((data) => {
        if (!cancelled) {
          setIndicators(normalizeMarketIndicators(data.market_indicators));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setIndicators(DEFAULT_MARKET_INDICATORS);
        }
      });

    function handleSettingsUpdated() {
      api
        .getDisplaySettings()
        .then((data) => setIndicators(normalizeMarketIndicators(data.market_indicators)))
        .catch(() => setIndicators(DEFAULT_MARKET_INDICATORS));
    }

    window.addEventListener(DISPLAY_SETTINGS_UPDATED, handleSettingsUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener(DISPLAY_SETTINGS_UPDATED, handleSettingsUpdated);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        const [health, botData, researchData, activityData] = await Promise.all([
          api.health(),
          api.bots(),
          api.getResearchSettings().catch(() => null),
          api.getBotActivity(TIMELINE_LIMIT).catch(() => ({ events: [], latest: null })),
        ]);
        if (cancelled) return;
        setOrchestratorRunning(Boolean(health.orchestrator_running));
        setBots(sortBots(botData.bots));
        setResearchSettings(researchData);
        setActivityEvents(activityData.events);
        setLoaded(true);
      } catch {
        if (!cancelled) {
          setOrchestratorRunning(false);
          setBots([]);
          setResearchSettings(null);
          setActivityEvents([]);
          setLoaded(true);
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
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, COUNTDOWN_REFRESH_MS);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!hovered) {
      setCoords(null);
      return;
    }

    function updatePosition() {
      const node = panelRef.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      setCoords({
        top: rect.bottom + 8,
        left: rect.left + rect.width / 2,
      });
    }

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [hovered]);

  if (!loaded || orchestratorRunning === null) {
    return null;
  }

  const marketSessions = marketStatus?.sessions ?? [];
  const marketAvailable = marketStatus?.available !== false;
  const marketsOpen = anyEnabledMarketOpen(marketSessions, indicators, {
    marketAvailable,
    serverTime: marketStatus?.server_time,
  });

  const status: OverallBotStatus = computeOverallStatus({
    orchestratorRunning,
    bots,
    marketSessions,
    marketIndicators: indicators,
    marketAvailable,
    marketServerTime: marketStatus?.server_time,
  });

  const tone = overallStatusTone(status);
  const label = overallStatusLabel(status);
  const tooltip = resolveOverallStatusTooltip({ status, bots });

  const showNextAction = status === "running" || status === "sleeping";
  const dataManager = bots.find((bot) => bot.name === "data_manager");
  let nextAction: NextActionState | null = null;

  if (showNextAction) {
    nextAction = computeNextAction({
      marketsOpen,
      orchestratorRunning,
      researchSettings,
      marketSessions,
      marketIndicators: indicators,
      marketAvailable,
      marketServerTime: marketStatus?.server_time,
      now: new Date(now),
      nextCandleFetches: dataManager?.next_candle_fetches,
    });
  }

  const countdownLabel = nextAction ? formatCountdown(nextAction.remainingMs) : null;
  const remainingPercent = nextAction
    ? computeProgress(now, nextAction.windowStartAt, nextAction.targetAt)
    : 0;
  const explainer = resolveOverallStatusExplainer(status, nextAction);
  const nextActionLabel =
    showNextAction && nextAction && nextAction.kind !== "none"
      ? formatNextActionDisplay(nextAction)
      : null;
  const nextActionUtcLabel =
    nextAction && nextAction.kind !== "none"
      ? formatNextActionTargetUtc(nextAction.targetAt, now, timeOptions)
      : null;

  const latestActivity = activityEvents[0] ?? null;
  const lastActionLabel = latestActivity ? activityTimelineLabel(latestActivity) : null;

  const tooltipNode =
    hovered && coords
      ? createPortal(
          <div
            id="overall-bot-status-tip"
            className="overall-bot-status-tooltip"
            role="tooltip"
            style={{ top: coords.top, left: coords.left }}
          >
            <p className="overall-bot-status-tooltip__title">{tooltip.title}</p>
            <p className="overall-bot-status-tooltip__summary">{explainer}</p>
            {lastActionLabel && latestActivity ? (
              <p className="overall-bot-status-tooltip__line">
                Last: {lastActionLabel} · {formatActivityRelative(latestActivity.occurred_at, now)}
              </p>
            ) : null}
            {nextAction ? (
              <p className="overall-bot-status-tooltip__line">
                Next: {formatNextActionDisplay(nextAction)} at{" "}
                {formatNextActionTargetUtc(nextAction.targetAt, now, timeOptions)} in{" "}
                {formatCountdown(nextAction.remainingMs)}
              </p>
            ) : null}
            {tooltip.lines.length > 0 ? (
              <ul className="overall-bot-status-tooltip__modules">
                {tooltip.lines.map((line, index) => (
                  <li key={`${index}-${line}`}>{line}</li>
                ))}
              </ul>
            ) : null}
            {activityEvents.length > 0 ? (
              <ol className="overall-bot-status-tooltip__timeline">
                {activityEvents.map((event) => (
                  <li key={event.id}>
                    <span>{activityTimelineLabel(event)}</span>
                    <span>{formatActivityRelative(event.occurred_at, now)}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div
        ref={panelRef}
        className="overall-bot-status-wrap"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        tabIndex={0}
        aria-describedby={hovered ? "overall-bot-status-tip" : undefined}
      >
        <div
          className={`overall-bot-status overall-bot-status--${tone}`}
          aria-label="Overall bot status"
        >
          <div className="overall-bot-status__status">
            <span className="overall-bot-status__dot" aria-hidden="true" />
            <span className="overall-bot-status__label">{label}</span>
          </div>

          {!nextActionLabel ? (
            <span className="overall-bot-status__meta">{explainer}</span>
          ) : null}

          {showNextAction && nextAction ? (
            <>
              <div
                className="overall-bot-status__track"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(remainingPercent)}
                aria-label={`Time remaining until ${nextActionLabel ?? nextAction.label}`}
              >
                <div
                  className={`overall-bot-status__fill overall-bot-status__fill--${tone}`}
                  style={{ width: `${remainingPercent}%` }}
                />
              </div>
              {countdownLabel ? (
                <span
                  className="overall-bot-status__countdown"
                  aria-label={`${nextActionLabel ?? nextAction.label} in ${countdownLabel}`}
                >
                  {countdownLabel}
                </span>
              ) : null}
            </>
          ) : null}
        </div>

        {nextActionLabel ? (
          <span className="overall-bot-status__next">
            Next: {nextActionLabel}
            {nextActionUtcLabel ? (
              <span className="overall-bot-status__next-utc"> · {nextActionUtcLabel}</span>
            ) : null}
          </span>
        ) : null}
      </div>
      {tooltipNode}
    </>
  );
}
