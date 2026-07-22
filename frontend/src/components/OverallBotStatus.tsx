import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  api,
  type BotActivityEvent,
  type NextCandlePreviewResponse,
  type ResearchSettings,
} from "../api/client";
import {
  ASSET_CLASS_STATUSES_UPDATED,
  loadAssetClassStatuses,
  type AssetClassStatus,
} from "../lib/assetClassStatus";
import {
  formatActivityRelative,
  normalizeActivityTimeline,
} from "../lib/botActivity";
import {
  computeOverallStatus,
  overallStatusLabel,
  overallStatusTone,
  sortBots,
  type BotStatusItem,
  type OverallBotStatus,
} from "../lib/bots";
import {
  DEFAULT_FOREX_TRADING_SESSIONS,
  FOREX_TRADING_SESSIONS_UPDATED,
  normalizeForexTradingSessions,
  type ForexTradingSessions,
} from "../lib/forexTradingSessions";
import { CONFIG_RESTORED } from "../lib/configBackup";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { useMarketStatus } from "../hooks/useMarketStatus";
import {
  computeNextAction,
  computeProgress,
  formatCountdown,
  formatNextActionDisplay,
  formatNextActionTargetUtc,
  resolveMarketStatusBadge,
  resolveNextActionTooltipExplainer,
  resolveOverallStatusExplainer,
  type NextActionState,
} from "../lib/nextAction";
import { TIMEFRAME_LABELS } from "../lib/strategyParams/types";
import type { Timeframe } from "../lib/strategyParams/types";

const POLL_INTERVAL_MS = 15_000;
const COUNTDOWN_REFRESH_MS = 1_000;
const TIMELINE_LIMIT = 5;

type TooltipCoords = {
  top: number;
  left: number;
};

function useHoverTooltipCoords<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [hovered, setHovered] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);

  useEffect(() => {
    if (!hovered) {
      setCoords(null);
      return;
    }

    function updatePosition() {
      const node = ref.current;
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

  return { ref, hovered, setHovered, coords };
}

function enabledAssetClassLabels(statuses: AssetClassStatus[]): string {
  return statuses
    .filter((row) => row.enabled)
    .map((row) => row.label)
    .join(", ");
}

export default function OverallBotStatus() {
  const { timeOptions } = useGeneralSettings();
  const {
    ref: pillRef,
    hovered: pillHovered,
    setHovered: setPillHovered,
    coords: pillCoords,
  } = useHoverTooltipCoords<HTMLDivElement>();
  const {
    ref: nextRef,
    hovered: nextHovered,
    setHovered: setNextHovered,
    coords: nextCoords,
  } = useHoverTooltipCoords<HTMLSpanElement>();

  const [loaded, setLoaded] = useState(false);
  const [orchestratorRunning, setOrchestratorRunning] = useState<boolean | null>(null);
  const [bots, setBots] = useState<BotStatusItem[]>([]);
  const marketStatus = useMarketStatus();
  const [researchSettings, setResearchSettings] = useState<ResearchSettings | null>(null);
  const [activityEvents, setActivityEvents] = useState<BotActivityEvent[]>([]);
  const [enabledTradingSessions, setEnabledTradingSessions] = useState<ForexTradingSessions>(
    DEFAULT_FOREX_TRADING_SESSIONS,
  );
  const [assetClassStatuses, setAssetClassStatuses] = useState<AssetClassStatus[]>([]);
  const [candlePreview, setCandlePreview] = useState<NextCandlePreviewResponse | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const marketStatusRef = useRef(marketStatus);
  marketStatusRef.current = marketStatus;

  useEffect(() => {
    let cancelled = false;

    async function loadForexTradingSessions() {
      try {
        const forexSettings = await api.getForexPairs();
        if (!cancelled) {
          setEnabledTradingSessions(normalizeForexTradingSessions(forexSettings.enabled_sessions));
        }
      } catch {
        if (!cancelled) {
          setEnabledTradingSessions(DEFAULT_FOREX_TRADING_SESSIONS);
        }
      }
    }

    function handleForexSessionsUpdated() {
      void loadForexTradingSessions();
    }

    async function loadAssetStatuses() {
      try {
        const assetStatuses = await loadAssetClassStatuses();
        if (!cancelled) {
          setAssetClassStatuses(assetStatuses);
        }
      } catch {
        if (!cancelled) {
          setAssetClassStatuses([]);
        }
      }
    }

    function handleAssetClassStatusesUpdated() {
      void loadAssetStatuses();
    }

    function handleConfigRestored() {
      void (async () => {
        await loadForexTradingSessions();
        await loadAssetStatuses();
        try {
          const researchData = await api.getResearchSettings();
          if (!cancelled) {
            setResearchSettings(researchData);
          }
        } catch {
          if (!cancelled) {
            setResearchSettings(null);
          }
        }
      })();
    }

    window.addEventListener(FOREX_TRADING_SESSIONS_UPDATED, handleForexSessionsUpdated);
    window.addEventListener(ASSET_CLASS_STATUSES_UPDATED, handleAssetClassStatusesUpdated);
    window.addEventListener(CONFIG_RESTORED, handleConfigRestored);
    return () => {
      cancelled = true;
      window.removeEventListener(FOREX_TRADING_SESSIONS_UPDATED, handleForexSessionsUpdated);
      window.removeEventListener(ASSET_CLASS_STATUSES_UPDATED, handleAssetClassStatusesUpdated);
      window.removeEventListener(CONFIG_RESTORED, handleConfigRestored);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    async function load() {
      try {
        const [health, botData, researchData, activityData, forexSettings, assetStatuses] =
          await Promise.all([
            api.health(),
            api.bots(),
            api.getResearchSettings().catch(() => null),
            api.getBotActivity(TIMELINE_LIMIT).catch(() => ({ events: [], latest: null })),
            api.getForexPairs().catch(() => null),
            loadAssetClassStatuses().catch(() => []),
          ]);
        if (cancelled) return;
        setOrchestratorRunning(Boolean(health.orchestrator_running));
        setBots(sortBots(botData.bots));
        setResearchSettings(researchData);
        setActivityEvents(activityData.events);
        setAssetClassStatuses(assetStatuses);
        if (forexSettings) {
          setEnabledTradingSessions(normalizeForexTradingSessions(forexSettings.enabled_sessions));
        }

        const currentMarket = marketStatusRef.current;
        const anyAssetClassEnabled = assetStatuses.some((row) => row.enabled);
        const statusForPreview = computeOverallStatus({
          orchestratorRunning: Boolean(health.orchestrator_running),
          bots: sortBots(botData.bots),
          marketSessions: currentMarket?.sessions ?? [],
          enabledTradingSessions: forexSettings
            ? normalizeForexTradingSessions(forexSettings.enabled_sessions)
            : DEFAULT_FOREX_TRADING_SESSIONS,
          marketAvailable: currentMarket?.available !== false,
          marketServerTime: currentMarket?.server_time,
          anyAssetClassEnabled,
        });
        const previewNext =
          statusForPreview === "running" && Boolean(health.orchestrator_running);
        if (previewNext) {
          try {
            const preview = await api.getNextCandlePreview();
            if (!cancelled) {
              setCandlePreview(preview);
            }
          } catch {
            if (!cancelled) {
              setCandlePreview(null);
            }
          }
        } else if (!cancelled) {
          setCandlePreview(null);
        }

        setLoaded(true);
      } catch {
        if (!cancelled) {
          setOrchestratorRunning(false);
          setBots([]);
          setResearchSettings(null);
          setActivityEvents([]);
          setAssetClassStatuses([]);
          setCandlePreview(null);
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

  if (!loaded || orchestratorRunning === null) {
    return null;
  }

  const marketSessions = marketStatus?.sessions ?? [];
  const marketAvailable = marketStatus?.available !== false;
  const anyAssetClassEnabled = assetClassStatuses.some((row) => row.enabled);

  const status: OverallBotStatus = computeOverallStatus({
    orchestratorRunning,
    bots,
    marketSessions,
    enabledTradingSessions,
    marketAvailable,
    marketServerTime: marketStatus?.server_time,
    anyAssetClassEnabled,
  });

  const tone = overallStatusTone(status);
  const label = overallStatusLabel(status);
  const marketBadge = resolveMarketStatusBadge(status);

  const showNextAction = status === "running" || status === "waiting" || status === "sleeping";
  const secretary = bots.find((bot) => bot.name === "secretary");
  let nextAction: NextActionState | null = null;

  if (showNextAction) {
    nextAction = computeNextAction({
      status,
      orchestratorRunning,
      researchSettings,
      marketSessions,
      enabledTradingSessions,
      marketAvailable,
      marketServerTime: marketStatus?.server_time,
      now: new Date(now),
      nextCandleFetches: secretary?.next_candle_fetches,
      analysisCandleTimeframes: secretary?.analysis_candle_timeframes,
    });
  }

  const countdownLabel = nextAction ? formatCountdown(nextAction.remainingMs) : null;
  const remainingPercent = nextAction
    ? computeProgress(now, nextAction.windowStartAt, nextAction.targetAt)
    : 0;
  const explainer = resolveOverallStatusExplainer(status, nextAction, {
    orchestratorRunning,
    anyAssetClassEnabled,
  });
  const nextActionLabel =
    showNextAction && nextAction && nextAction.kind !== "none"
      ? formatNextActionDisplay(nextAction)
      : null;
  const nextActionUtcLabel =
    nextAction && nextAction.kind !== "none"
      ? formatNextActionTargetUtc(nextAction.targetAt, now, timeOptions)
      : null;

  const timelineEvents = normalizeActivityTimeline(activityEvents, TIMELINE_LIMIT);
  const watchingLabel = enabledAssetClassLabels(assetClassStatuses);

  const mainTooltipNode =
    pillHovered && pillCoords ? (
      createPortal(
        <div
          id="overall-bot-status-tip"
          className="overall-bot-status-tooltip"
          role="tooltip"
          style={{ top: pillCoords.top, left: pillCoords.left }}
        >
          <div className="overall-bot-status-tooltip__title-row">
            <p className="overall-bot-status-tooltip__title">Bot: {label}</p>
            {marketBadge ? (
              <span className="overall-bot-status-tooltip__market-badge">{marketBadge}</span>
            ) : null}
          </div>
          {nextAction && nextAction.kind !== "none" ? (
            <p className="overall-bot-status-tooltip__line">
              {formatNextActionDisplay(nextAction)}
              {nextActionUtcLabel ? ` · ${nextActionUtcLabel}` : null}
            </p>
          ) : null}
          {watchingLabel ? (
            <p className="overall-bot-status-tooltip__watching">Watching: {watchingLabel}</p>
          ) : null}
          {timelineEvents.length > 0 ? (
            <ol className="overall-bot-status-tooltip__timeline">
              {timelineEvents.map((event) => (
                <li key={event.id}>
                  <span>{event.label}</span>
                  <span>{formatActivityRelative(event.occurred_at, now)}</span>
                </li>
              ))}
            </ol>
          ) : null}
        </div>,
        document.body,
      )
    ) : null;

  const nextTooltipContent = (() => {
    if (!nextAction || nextAction.kind === "none") {
      return resolveNextActionTooltipExplainer(
        nextAction ?? {
          kind: "none",
          label: "No upcoming action",
          targetAt: now,
          windowStartAt: now,
          remainingMs: 0,
          progress: 0,
        },
      );
    }

    if (nextAction.kind === "candle_update") {
      const timeframe = nextAction.timeframe;
      const tfLabel = timeframe ? TIMEFRAME_LABELS[timeframe as Timeframe] : null;
      const assetSections =
        candlePreview?.asset_sections?.filter((section) => section.symbols.length > 0) ?? [];
      const hasSymbols =
        assetSections.length > 0 || (candlePreview?.symbols?.length ?? 0) > 0;
      if (!hasSymbols) {
        return "No symbols scheduled for this candle close.";
      }
      const sections =
        assetSections.length > 0
          ? assetSections
          : [{ asset_class: "forex", label: "Forex", symbols: candlePreview?.symbols ?? [] }];
      return (
        <>
          {tfLabel ? (
            <p className="overall-bot-status-tooltip__next-heading">
              Symbols on {tfLabel} close
            </p>
          ) : null}
          <div className="overall-bot-status-tooltip__asset-sections">
            {sections.map((section) => (
              <div
                key={section.asset_class}
                className="overall-bot-status-tooltip__asset-section"
              >
                <p className="overall-bot-status-tooltip__asset-label">{section.label}</p>
                <p className="overall-bot-status-tooltip__symbols">
                  {section.symbols.join(", ")}
                </p>
              </div>
            ))}
          </div>
        </>
      );
    }

    return resolveNextActionTooltipExplainer(nextAction);
  })();

  const nextTooltipNode =
    nextHovered && nextCoords && nextActionLabel ? (
      createPortal(
        <div
          id="overall-bot-status-next-tip"
          className="overall-bot-status-tooltip overall-bot-status-tooltip--next"
          role="tooltip"
          style={{ top: nextCoords.top, left: nextCoords.left }}
        >
          {typeof nextTooltipContent === "string" ? (
            <p className="overall-bot-status-tooltip__summary">{nextTooltipContent}</p>
          ) : (
            nextTooltipContent
          )}
        </div>,
        document.body,
      )
    ) : null;

  return (
    <>
      <div className="overall-bot-status-wrap">
        <div
          ref={pillRef}
          className={`overall-bot-status overall-bot-status--${tone}`}
          aria-label="Overall bot status"
          onMouseEnter={() => setPillHovered(true)}
          onMouseLeave={() => setPillHovered(false)}
          onFocus={() => setPillHovered(true)}
          onBlur={() => setPillHovered(false)}
          tabIndex={0}
          aria-describedby={pillHovered ? "overall-bot-status-tip" : undefined}
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
          <span
            ref={nextRef}
            className="overall-bot-status__next"
            onMouseEnter={(event) => {
              event.stopPropagation();
              setNextHovered(true);
            }}
            onMouseLeave={(event) => {
              event.stopPropagation();
              setNextHovered(false);
            }}
            onFocus={(event) => {
              event.stopPropagation();
              setNextHovered(true);
            }}
            onBlur={(event) => {
              event.stopPropagation();
              setNextHovered(false);
            }}
            tabIndex={0}
            aria-describedby={nextHovered ? "overall-bot-status-next-tip" : undefined}
          >
            Next: {nextActionLabel}
            {nextActionUtcLabel ? (
              <span className="overall-bot-status__next-utc"> · {nextActionUtcLabel}</span>
            ) : null}
          </span>
        ) : null}
      </div>
      {mainTooltipNode}
      {nextTooltipNode}
    </>
  );
}
