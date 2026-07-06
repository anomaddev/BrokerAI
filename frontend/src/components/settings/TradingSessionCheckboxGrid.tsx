import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import type { SessionDef } from "../../lib/marketSessionDefs";
import { ASIA_SESSION_INFO } from "../../lib/marketSessionDefs";

type TradingSessionCheckboxGridProps = {
  sessions: SessionDef[];
  values: Record<string, boolean>;
  onChange: (sessionId: string, enabled: boolean) => void;
  disabled?: boolean;
  formatSessionHours: (session: SessionDef) => string;
};

type TooltipCoords = {
  top: number;
  left: number;
};

function AsiaSessionInfoButton() {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [hovered, setHovered] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);

  useEffect(() => {
    if (!hovered) {
      setCoords(null);
      return;
    }

    function updatePosition() {
      const node = buttonRef.current;
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
            id="asia-session-info-tip"
            className="trading-session-info-tooltip"
            role="tooltip"
            style={{ top: coords.top, left: coords.left }}
          >
            <p className="trading-session-info-tooltip-title">{ASIA_SESSION_INFO.title}</p>
            <p className="trading-session-info-tooltip-body">{ASIA_SESSION_INFO.body}</p>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="trading-session-info-btn"
        aria-label="About the Asia session"
        aria-describedby={hovered ? "asia-session-info-tip" : undefined}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <Info size={14} aria-hidden="true" />
      </button>
      {tooltipNode}
    </>
  );
}

export default function TradingSessionCheckboxGrid({
  sessions,
  values,
  onChange,
  disabled = false,
  formatSessionHours,
}: TradingSessionCheckboxGridProps) {
  return (
    <div className="trading-session-grid">
      {sessions.map((session) => {
        const checked = values[session.id] ?? true;
        const hoursLabel = formatSessionHours(session);
        return (
          <label
            key={session.id}
            className={`forex-pair-checkbox trading-session-card${checked ? " forex-pair-checkbox--checked" : ""}`}
            title={hoursLabel}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled}
              onChange={(e) => onChange(session.id, e.target.checked)}
            />
            <span className="trading-session-card-body">
              <span className="trading-session-card-name-row">
                <span className="trading-session-card-name">{session.name}</span>
                {session.id === "asia" ? <AsiaSessionInfoButton /> : null}
              </span>
              <span className="trading-session-card-hours">{hoursLabel}</span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
