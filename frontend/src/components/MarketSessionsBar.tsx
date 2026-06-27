import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type MarketSessionStatus, type MarketStatusResponse } from "../api/client";
import {
  DEFAULT_MARKET_INDICATORS,
  DISPLAY_SETTINGS_UPDATED,
  isMarketIndicatorEnabled,
  normalizeMarketIndicators,
  type MarketIndicators,
} from "../lib/displaySettings";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { resolveSessionTooltip } from "../lib/marketSessions";
import type { TimeFormatOptions } from "../lib/formatTime";

const POLL_INTERVAL_MINUTES = 5;
const POLL_MARK_SECOND = 1;

function msUntilNextPoll(from = new Date()): number {
  const next = new Date(from);
  const blockStartMinute = Math.floor(from.getMinutes() / POLL_INTERVAL_MINUTES) * POLL_INTERVAL_MINUTES;
  next.setMinutes(blockStartMinute, POLL_MARK_SECOND, 0);

  if (next.getTime() <= from.getTime()) {
    next.setMinutes(blockStartMinute + POLL_INTERVAL_MINUTES, POLL_MARK_SECOND, 0);
  }

  return next.getTime() - from.getTime();
}

function sessionLabel(session: MarketSessionStatus): string {
  if (session.status === "open") {
    if (session.exchange_status === "extended-hours") return "Extended";
    return "Open";
  }
  return "Closed";
}

function sessionTone(session: MarketSessionStatus): "open" | "extended" | "closed" {
  if (session.status !== "open") return "closed";
  if (session.exchange_status === "extended-hours") return "extended";
  return "open";
}

type SessionPillProps = {
  session: MarketSessionStatus;
  serverTime?: string;
  timeOptions: TimeFormatOptions;
};

type TooltipCoords = {
  top: number;
  left: number;
};

function SessionPill({ session, serverTime, timeOptions }: SessionPillProps) {
  const pillRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);
  const tone = sessionTone(session);
  const tooltip = resolveSessionTooltip(session, serverTime, timeOptions);

  useEffect(() => {
    if (!hovered) {
      setCoords(null);
      return;
    }

    function updatePosition() {
      const node = pillRef.current;
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

  const tooltipNode =
    hovered && coords
      ? createPortal(
          <div
            id={`market-session-tip-${session.id}`}
            className="market-session-tooltip"
            role="tooltip"
            style={{ top: coords.top, left: coords.left }}
          >
            <p className="market-session-tooltip-title">{tooltip.name}</p>
            <p className="market-session-tooltip-hours">{tooltip.hours}</p>
            {tooltip.timingLabel ? (
              <p className="market-session-tooltip-timing">{tooltip.timingLabel}</p>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div
        className="market-session-item"
        ref={pillRef}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
      >
        <div
          className={`market-session-pill market-session-pill--${tone}`}
          tabIndex={0}
          aria-describedby={hovered ? `market-session-tip-${session.id}` : undefined}
        >
          <span className="market-session-dot" aria-hidden="true" />
          <span className="market-session-name">{session.name}</span>
          <span className="market-session-state">{sessionLabel(session)}</span>
        </div>
      </div>
      {tooltipNode}
    </>
  );
}

export default function MarketSessionsBar() {
  const { timeOptions } = useGeneralSettings();
  const [status, setStatus] = useState<MarketStatusResponse | null>(null);
  const [indicators, setIndicators] = useState<MarketIndicators>(DEFAULT_MARKET_INDICATORS);

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
        const data = await api.getMarketStatus();
        if (!cancelled) setStatus(data);
      } catch {
        if (!cancelled) {
          setStatus({ enabled: true, available: false, sessions: [] });
        }
      }
    }

    function scheduleNext() {
      timer = window.setTimeout(() => {
        void load().finally(() => {
          if (!cancelled) scheduleNext();
        });
      }, msUntilNextPoll());
    }

    void load();
    scheduleNext();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  const visibleSessions = (status?.sessions ?? []).filter((session) =>
    isMarketIndicatorEnabled(indicators, session.id),
  );
  const hasEnabledIndicators = Object.values(indicators).some(Boolean);

  if (!status || !status.enabled || !hasEnabledIndicators) {
    return null;
  }

  if (status.available === false) {
    return (
      <div
        className="market-sessions-bar market-sessions-bar--unavailable"
        title={status.error ?? "Market status unavailable"}
      >
        <span className="market-sessions-unavailable">Market status unavailable</span>
      </div>
    );
  }

  if (visibleSessions.length === 0) {
    return null;
  }

  return (
    <div className="market-sessions-bar" aria-label="Trading session status">
      {visibleSessions.map((session) => (
        <SessionPill key={session.id} session={session} serverTime={status.server_time} timeOptions={timeOptions} />
      ))}
    </div>
  );
}
